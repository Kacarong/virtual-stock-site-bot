"""토스증권 Open API 시세 소스.

- 인증: POST /oauth2/token (OAuth2 Client Credentials Grant), access token 캐싱
- 현재가: GET /api/v1/prices?symbols=005930,AAPL  (배치, 최대 200)
- 캔들:  GET /api/v1/candles?symbol=&interval=1m|1d&count=
- 환율:  GET /api/v1/exchange-rate?baseCurrency=USD&quoteCurrency=KRW

심볼: KRX 6자리 코드(005930), US 티커(AAPL) — 앱의 code 필드와 동일하므로
      market 구분 없이 그대로 전달한다.

TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 미설정 시 모든 호출은 graceful None/[] 반환.
현재가 응답에는 전일종가(prev_close)가 없어, 일봉 캔들에서 뽑아 KST 날짜 단위로 캐싱한다.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

from ...config import settings

_KST = ZoneInfo("Asia/Seoul")


def _base() -> str:
    return (settings.TOSS_API_BASE or "https://openapi.tossinvest.com").rstrip("/")


def _configured() -> bool:
    return bool(settings.TOSS_CLIENT_ID and settings.TOSS_CLIENT_SECRET)


def _unwrap(data):
    """Toss 응답은 {"result": ...} 래핑."""
    if isinstance(data, dict) and "result" in data:
        return data["result"]
    return data


# --- 토큰 캐시 -------------------------------------------------------

_token_cache: dict = {"token": None, "exp": 0.0}
_token_lock = asyncio.Lock()


async def get_access_token() -> str | None:
    if not _configured():
        return None
    async with _token_lock:
        now = time.time()
        if _token_cache["token"] and _token_cache["exp"] > now + 60:
            return _token_cache["token"]
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    f"{_base()}/oauth2/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": settings.TOSS_CLIENT_ID,
                        "client_secret": settings.TOSS_CLIENT_SECRET,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                r.raise_for_status()
                data = r.json()
                _token_cache["token"] = data["access_token"]
                _token_cache["exp"] = now + int(data.get("expires_in", 3600))
                return _token_cache["token"]
        except Exception as e:
            logger.warning("Toss token issue failed: {}", e)
            return None


async def _auth_headers() -> dict | None:
    t = await get_access_token()
    if not t:
        return None
    return {"Authorization": f"Bearer {t}"}


# --- 현재가 ---------------------------------------------------------

async def _fetch_last_prices(codes: list[str]) -> dict[str, Decimal]:
    """/api/v1/prices 배치 호출. {code: lastPrice}."""
    if not codes:
        return {}
    headers = await _auth_headers()
    if not headers:
        return {}
    out: dict[str, Decimal] = {}
    for i in range(0, len(codes), 200):  # 최대 200개/콜
        chunk = codes[i : i + 200]
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{_base()}/api/v1/prices",
                    params={"symbols": ",".join(chunk)},
                    headers=headers,
                )
                r.raise_for_status()
                rows = _unwrap(r.json()) or []
            for row in rows:
                sym = row.get("symbol")
                lp = row.get("lastPrice")
                if sym and lp is not None:
                    try:
                        out[sym] = Decimal(str(lp))
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Toss prices failed {}: {}", chunk[:3], e)
    return out


# code → (KST 날짜, prev_close). 전일종가는 하루 한 번만 조회.
_prev_close_cache: dict[str, tuple[str, Decimal]] = {}


def _today_kst() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%d")


async def _prev_close(code: str) -> Decimal | None:
    day = _today_kst()
    cached = _prev_close_cache.get(code)
    if cached and cached[0] == day:
        return cached[1]
    candles = await fetch_candles(code, interval="1d", count=2)
    pc: Decimal | None = None
    if len(candles) >= 2:
        pc = Decimal(str(candles[-2]["close"]))  # 직전 세션 종가
    elif len(candles) == 1:
        pc = Decimal(str(candles[-1]["close"]))
    if pc is not None:
        _prev_close_cache[code] = (day, pc)
    return pc


async def fetch_prices(codes: list[str]) -> dict[str, dict]:
    """다수 종목 현재가. 반환 key=code, value={price, prev_close}."""
    if not _configured() or not codes:
        return {}
    last = await _fetch_last_prices(codes)
    if not last:
        return {}
    sem = asyncio.Semaphore(8)

    async def _pc(code: str) -> tuple[str, Decimal | None]:
        async with sem:
            return code, await _prev_close(code)

    pcs = dict(await asyncio.gather(*(_pc(c) for c in last.keys())))
    out: dict[str, dict] = {}
    for code, price in last.items():
        prev = pcs.get(code)
        out[code] = {"price": price, "prev_close": prev if prev is not None else price}
    return out


async def fetch_price(code: str) -> dict | None:
    """단일 종목 현재가. code='005930' 또는 'AAPL'."""
    m = await fetch_prices([code])
    return m.get(code)


# --- 캔들 -----------------------------------------------------------

def _parse_candles(res) -> list[dict]:
    """캔들 응답 → [{time(epoch s), open, high, low, close, volume}] 오름차순."""
    rows = res.get("candles", []) if isinstance(res, dict) else []
    out: list[dict] = []
    for row in rows:
        ts_iso = row.get("timestamp")
        if not ts_iso:
            continue
        try:
            t = int(datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp())
            out.append(
                {
                    "time": t,
                    "open": float(row["openPrice"]),
                    "high": float(row["highPrice"]),
                    "low": float(row["lowPrice"]),
                    "close": float(row["closePrice"]),
                    "volume": float(row.get("volume") or 0),
                }
            )
        except Exception:
            continue
    out.sort(key=lambda x: x["time"])
    return out


async def fetch_candles(code: str, interval: str = "1d", count: int = 100) -> list[dict]:
    """캔들 차트. interval='1m'|'1d', 최대 200개.

    반환: [{time(epoch s), open, high, low, close, volume}] 시간 오름차순.
    """
    if not _configured():
        return []
    headers = await _auth_headers()
    if not headers:
        return []
    count = max(1, min(count, 200))
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{_base()}/api/v1/candles",
                params={
                    "symbol": code,
                    "interval": interval,
                    "count": count,
                    "adjusted": "true",
                },
                headers=headers,
            )
            r.raise_for_status()
            res = _unwrap(r.json()) or {}
        return _parse_candles(res)
    except Exception as e:
        logger.debug("Toss candles failed {} {}: {}", code, interval, e)
        return []


# --- 시장 지표 (지수: 코스피/코스닥 등) -----------------------------

async def fetch_index_prices(symbols: list[str]) -> dict[str, Decimal]:
    """시장 지표 현재가. GET /api/v1/market-indicators/prices. {symbol: lastPrice}."""
    if not _configured() or not symbols:
        return {}
    headers = await _auth_headers()
    if not headers:
        return {}
    out: dict[str, Decimal] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{_base()}/api/v1/market-indicators/prices",
                params={"symbols": ",".join(symbols)},
                headers=headers,
            )
            r.raise_for_status()
            rows = _unwrap(r.json()) or []
        for row in rows:
            s = row.get("symbol")
            lp = row.get("lastPrice")
            if s and lp is not None:
                try:
                    out[s] = Decimal(str(lp))
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Toss index prices failed: {}", e)
    return out


async def fetch_index_candles(
    symbol: str, interval: str = "1d", count: int = 30
) -> list[dict]:
    """시장 지표 캔들. GET /api/v1/market-indicators/{symbol}/candles."""
    if not _configured():
        return []
    headers = await _auth_headers()
    if not headers:
        return []
    count = max(1, min(count, 200))
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{_base()}/api/v1/market-indicators/{symbol}/candles",
                params={"interval": interval, "count": count},
                headers=headers,
            )
            r.raise_for_status()
            res = _unwrap(r.json()) or {}
        return _parse_candles(res)
    except Exception as e:
        logger.debug("Toss index candles failed {}: {}", symbol, e)
        return []


# --- 랭킹 (인기종목) ------------------------------------------------

# 앱 sort → Toss 랭킹 type. market_cap 은 Toss 미지원(→ 폴백 경로에서 처리).
_RANKING_TYPE = {
    "value": "MARKET_TRADING_AMOUNT",
    "volume": "MARKET_TRADING_VOLUME",
    "change": "TOP_GAINERS",
    "decline": "TOP_LOSERS",
}


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


async def fetch_rankings(
    market_country: str, sort: str, count: int = 30
) -> list[dict]:
    """랭킹(인기종목). market_country='KR'|'US'.

    반환: [{code, price, prev_close, change_pct(%), volume, value}] (순위 순).
    market_cap 정렬은 Toss 미지원 → [] 반환하여 호출측 폴백을 타게 한다.
    """
    if not _configured():
        return []
    tp = _RANKING_TYPE.get(sort)
    if not tp:
        return []
    headers = await _auth_headers()
    if not headers:
        return []
    count = max(1, min(count, 100))
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{_base()}/api/v1/rankings",
                params={
                    "type": tp,
                    "marketCountry": market_country,
                    "duration": "1d",
                    "count": count,
                },
                headers=headers,
            )
            r.raise_for_status()
            res = _unwrap(r.json()) or {}
        rows = res.get("rankings", []) if isinstance(res, dict) else []
        out: list[dict] = []
        for row in rows:
            code = row.get("symbol")
            price = row.get("price") or {}
            if not code or price.get("lastPrice") is None:
                continue
            cr = price.get("changeRate")
            change_pct = _f(cr) * 100 if cr not in (None, "") else 0.0
            out.append(
                {
                    "code": code,
                    "price": _f(price.get("lastPrice")),
                    "prev_close": _f(price.get("basePrice")),
                    "change_pct": change_pct,
                    "volume": _f(row.get("tradingVolume")),
                    "value": _f(row.get("tradingAmount")),
                }
            )
        return out
    except Exception as e:
        logger.debug("Toss rankings failed {} {}: {}", market_country, sort, e)
        return []


# --- 종목 정보 (이름/시장 조회) -------------------------------------

# Toss market 세그먼트 → 앱 market
_MARKET_MAP = {
    "KOSPI": "KRX",
    "KOSDAQ": "KRX",
    "KR_ETC": "KRX",
    "NYSE": "NYSE",
    "NASDAQ": "NASDAQ",
    "AMEX": "AMEX",
    "US_ETC": "NASDAQ",
}


def _asset_type(security_type: str | None) -> str:
    s = (security_type or "").upper()
    if "ETF" in s:
        return "ETF"
    if s == "ETN":
        return "ETN"
    return "STOCK"


async def fetch_stock_info(codes: list[str]) -> dict[str, dict]:
    """종목 기본정보(이름/시장/통화). GET /api/v1/stocks?symbols= (최대 200).

    반환: {code: {name, english_name, market, currency, asset_type, status}}.
    pykrx 전종목 목록에 없는 ETN/레버리지 등의 이름을 on-demand로 해결하는 용도.
    """
    if not _configured() or not codes:
        return {}
    headers = await _auth_headers()
    if not headers:
        return {}
    out: dict[str, dict] = {}
    for i in range(0, len(codes), 200):
        chunk = codes[i : i + 200]
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    f"{_base()}/api/v1/stocks",
                    params={"symbols": ",".join(chunk)},
                    headers=headers,
                )
                r.raise_for_status()
                rows = _unwrap(r.json()) or []
            for row in rows:
                code = row.get("symbol")
                name = row.get("name") or row.get("englishName")
                if not code or not name:
                    continue
                out[code] = {
                    "name": name,
                    "english_name": row.get("englishName"),
                    "market": _MARKET_MAP.get(row.get("market") or "", "KRX"),
                    "currency": row.get("currency") or "KRW",
                    "asset_type": _asset_type(row.get("securityType")),
                    "status": row.get("status"),
                }
        except Exception as e:
            logger.debug("Toss stocks failed {}: {}", chunk[:3], e)
    return out


# --- 환율 -----------------------------------------------------------

async def fetch_usdkrw() -> Decimal | None:
    """USD→KRW 환율."""
    if not _configured():
        return None
    headers = await _auth_headers()
    if not headers:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{_base()}/api/v1/exchange-rate",
                params={"baseCurrency": "USD", "quoteCurrency": "KRW"},
                headers=headers,
            )
            r.raise_for_status()
            res = _unwrap(r.json()) or {}
        rate = res.get("rate") or res.get("midRate")
        return Decimal(str(rate)) if rate else None
    except Exception as e:
        logger.debug("Toss exchange-rate failed: {}", e)
        return None
