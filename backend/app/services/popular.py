"""인기종목 — 시장별 거래량/거래대금/등락률 랭킹.

캐시 정책:
- UPBIT: 10초 (공개 API 무료/속도빠름)
- KRX:   60초 (pykrx는 무겁다)
- US:    60초 (yfinance + 시드 목록)
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Literal

from loguru import logger
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Symbol
from .sources import kis as _kis
from .sources import stooq as _stooq
from .sources import upbit
from .sources.kr_seeds import KR_SEEDS
from .sources.us_seeds import US_SEEDS

Sort = Literal["value", "volume", "change"]
Market = Literal["KRX", "US", "UPBIT"]

_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_TTL = {"UPBIT": 10.0, "KRX": 60.0, "US": 60.0}

# 동시 호출 시 중복 fetch 방지용 in-flight 락 (느린 KRX/US용)
_inflight: dict[str, asyncio.Lock] = {}


def _lock_for(market: str) -> asyncio.Lock:
    lk = _inflight.get(market)
    if lk is None:
        lk = asyncio.Lock()
        _inflight[market] = lk
    return lk


# popular US용 인기 ~120개 (시드 396개 중 시총/거래량 상위)
US_POPULAR_CODES = [
    # 메가캡 테크
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "ORCL",
    "CRM", "AMD", "NFLX", "ADBE", "INTC", "QCOM", "CSCO", "PLTR", "UBER", "SHOP",
    "ABNB", "ASML", "TSM", "SMCI", "ARM", "MU", "AMAT", "LRCX", "KLAC", "MRVL",
    "CRWD", "PANW", "NOW", "INTU", "SNOW", "DDOG", "ZS", "NET", "MDB", "TEAM",
    "DELL", "HPQ", "IBM", "TXN", "ADI", "NXPI", "ON", "MCHP", "WDC", "STX",
    # 금융
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BRK-B", "BLK", "C",
    "COIN", "HOOD", "SQ", "PYPL", "SOFI", "AXP", "SCHW",
    # 소비재/유통
    "WMT", "COST", "HD", "TGT", "LOW", "NKE", "SBUX", "MCD", "DIS", "KO",
    "PEP", "MDLZ", "PG", "CL",
    # 헬스
    "LLY", "UNH", "JNJ", "ABBV", "PFE", "MRK", "TMO", "ABT", "DHR", "CVS",
    "NVO",
    # 에너지/소재
    "XOM", "CVX", "COP", "SLB", "OXY",
    # 통신/미디어
    "T", "VZ", "TMUS", "CMCSA", "WBD", "NFLX",
    # 중국 ADR
    "BABA", "PDD", "JD", "BIDU", "NIO", "XPEV", "LI",
    # 크립토/관련
    "MSTR", "MARA", "RIOT", "CLSK",
    # 밈
    "GME", "AMC", "RDDT", "DJT",
    # 항공/여행
    "DAL", "UAL", "AAL", "CCL", "RCL", "BKNG",
    # ETF (대표)
    "SPY", "QQQ", "VOO", "IWM", "DIA", "IBIT", "FBTC",
    "SOXX", "SMH", "ARKK", "ARKG", "TQQQ", "SQQQ", "SOXL", "SOXS",
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLC", "XLU", "XLB",
    "VTI", "VT", "VEA", "VWO", "BND", "TLT", "GLD", "SLV",
]


def _cached(key: tuple[str, str]) -> list[dict] | None:
    hit = _cache.get(key)
    if not hit:
        return None
    ts, data = hit
    market = key[0]
    if time.time() - ts > _TTL.get(market, 30.0):
        return None
    return data


def _store(key: tuple[str, str], data: list[dict]) -> None:
    _cache[key] = (time.time(), data)


# ------------------------------------------------------------------ UPBIT

async def popular_upbit(sort: Sort, limit: int = 30) -> list[dict]:
    key = ("UPBIT", sort)
    if (c := _cached(key)) is not None:
        return c[:limit]

    # 마켓 목록
    db = SessionLocal()
    try:
        codes = [s.code for s in db.query(Symbol).filter(Symbol.market == "UPBIT", Symbol.is_active).all()]
        name_by = {s.code: s.name for s in db.query(Symbol).filter(Symbol.market == "UPBIT").all()}
    finally:
        db.close()

    if not codes:
        # 시드라도 없으면 hardcode
        codes = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-DOGE"]
        name_by = {c: c for c in codes}

    rows = await upbit.fetch_tickers_full(codes)
    out = []
    for r in rows:
        price = float(r.get("trade_price", 0))
        prev = float(r.get("prev_closing_price", 0)) or price
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        out.append(
            {
                "market": "UPBIT",
                "code": r["market"],
                "name": name_by.get(r["market"], r["market"]),
                "price": price,
                "change_pct": change_pct,
                "volume": float(r.get("acc_trade_volume_24h", 0)),
                "value": float(r.get("acc_trade_price_24h", 0)),
            }
        )
    if sort == "value":
        out.sort(key=lambda x: x["value"], reverse=True)
    elif sort == "volume":
        out.sort(key=lambda x: x["volume"], reverse=True)
    else:  # change
        out.sort(key=lambda x: x["change_pct"], reverse=True)

    _store(key, out)
    return out[:limit]


# ------------------------------------------------------------------ KRX

async def popular_krx(sort: Sort, limit: int = 30) -> list[dict]:
    key = ("KRX", sort)
    if (c := _cached(key)) is not None:
        return c[:limit]

    lock = _lock_for("KRX")
    if lock.locked():
        for s in ("value", "volume", "change"):
            stale = _cache.get(("KRX", s))
            if stale:
                return _sort_rows(list(stale[1]), sort)[:limit]
        return []

    async with lock:
        if (c := _cached(("KRX", sort))) is not None:
            return c[:limit]

        def _fetch() -> list[dict]:
            try:
                from datetime import datetime, timedelta
                from pykrx import stock  # type: ignore

                today = datetime.now()
                df = None
                for d in range(0, 7):
                    date = (today - timedelta(days=d)).strftime("%Y%m%d")
                    try:
                        df = stock.get_market_ohlcv_by_ticker(date=date, market="ALL")
                        if df is not None and len(df) > 0:
                            logger.info("KRX popular: pykrx date={} rows={}", date, len(df))
                            break
                    except Exception as e:
                        logger.debug("pykrx ohlcv try {} fail: {}", date, e)
                        continue
                if df is None or len(df) == 0:
                    logger.warning("KRX popular: pykrx returned empty")
                    return []
                df = df.reset_index().rename(
                    columns={
                        "티커": "code",
                        "종가": "price",
                        "거래량": "volume",
                        "거래대금": "value",
                        "등락률": "change_pct",
                    }
                )
                return df[["code", "price", "volume", "value", "change_pct"]].to_dict("records")
            except Exception as e:
                logger.warning("KRX popular fetch failed: {}", e)
                return []

        try:
            rows = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=25.0)
        except asyncio.TimeoutError:
            logger.warning("KRX popular fetch timeout")
            rows = []

        # pykrx 실패 시: KIS API로 시드 전체 quote 받아서 채움 (KIS도 volume/value 제공)
        if not rows:
            logger.info("KRX popular fallback: using seeds + KIS quote")
            seed_codes = [c for c, _, asset_type, _ in KR_SEEDS if asset_type == "STOCK"]
            quotes = await _kis.fetch_prices(seed_codes)
            rows = []
            for code in seed_codes:
                q = quotes.get(code)
                if not q:
                    continue
                price = float(q["price"])
                prev = float(q.get("prev_close") or price) or price
                volume = float(q.get("volume") or 0)
                value = float(q.get("value") or 0)
                change_pct = ((price - prev) / prev * 100) if prev else 0.0
                rows.append(
                    {
                        "code": code,
                        "price": price,
                        "volume": volume,
                        "value": value,
                        "change_pct": change_pct,
                    }
                )

    # 이름 붙이기 (Symbol DB 우선, 없으면 KR_SEEDS, 마지막엔 code 그대로)
    db = SessionLocal()
    try:
        name_by = {s.code: s.name for s in db.query(Symbol).filter(Symbol.market == "KRX").all()}
    finally:
        db.close()
    seed_name = {code: name for code, name, _, _ in KR_SEEDS}

    out = []
    for r in rows:
        code = str(r["code"])
        name = name_by.get(code) or seed_name.get(code)
        if not name:
            continue
        # 매핑용으로 임시 추가 (다음 줄에서 사용)
        name_by[code] = name
        out.append(
            {
                "market": "KRX",
                "code": code,
                "name": name_by[code],
                "price": float(r["price"]),
                "change_pct": float(r["change_pct"]),
                "volume": float(r["volume"]),
                "value": float(r["value"]),
            }
        )

    if sort == "value":
        out.sort(key=lambda x: x["value"], reverse=True)
    elif sort == "volume":
        out.sort(key=lambda x: x["volume"], reverse=True)
    else:
        out.sort(key=lambda x: x["change_pct"], reverse=True)

    _store(key, out)
    return out[:limit]


# ------------------------------------------------------------------ US

def _sort_rows(rows: list[dict], sort: Sort) -> list[dict]:
    # secondary key=code 로 안정 정렬 (값 동률 시 같은 순서 유지 → 화면 튐 방지)
    if sort == "value":
        rows.sort(key=lambda x: (-x.get("value", 0), x.get("code", "")))
    elif sort == "volume":
        rows.sort(key=lambda x: (-x.get("volume", 0), x.get("code", "")))
    else:
        rows.sort(key=lambda x: (-x.get("change_pct", 0), x.get("code", "")))
    return rows


async def popular_us(sort: Sort, limit: int = 30) -> list[dict]:
    # 캐시 적중 시 즉시 반환
    for s in ("value", "volume", "change"):
        if (c := _cached(("US", s))) is not None and s == sort:
            return c[:limit]

    lock = _lock_for("US")
    # 락이 잠겨 있으면 기존 캐시(만료라도) 반환 — 무한 로딩 방지
    if lock.locked():
        for s in ("value", "volume", "change"):
            stale = _cache.get(("US", s))
            if stale:
                return _sort_rows(list(stale[1]), sort)[:limit]
        return []

    async with lock:
        # 락 진입 후 한 번 더 확인 (다른 호출이 방금 채웠을 수 있음)
        if (c := _cached(("US", sort))) is not None:
            return c[:limit]

        codes = US_POPULAR_CODES
        name_by = {c: n for c, n, _, _ in US_SEEDS}
        market_by = {c: m for c, _, m, _ in US_SEEDS}

        by_code: dict[str, dict] = {}

        def _add(code: str, price: float, prev: float, volume: float, value: float | None = None):
            if price <= 0:
                return
            change_pct = ((price - prev) / prev * 100) if prev else 0.0
            by_code[code] = {
                "market": market_by.get(code, "NASDAQ"),
                "code": code,
                "name": name_by.get(code, code),
                "price": price,
                "change_pct": change_pct,
                "volume": volume,
                "value": value if value is not None else price * volume,
            }

        # 0순위: KIS 해외주식 (real 키 + 해외 권한 필요)
        if _kis._configured():
            try:
                kis_quotes = await asyncio.wait_for(
                    _kis.fetch_overseas_prices(
                        [(c, market_by.get(c, "NASDAQ")) for c in codes]
                    ),
                    timeout=25.0,
                )
            except asyncio.TimeoutError:
                logger.warning("US popular: KIS overseas timeout")
                kis_quotes = {}
            for code, q in kis_quotes.items():
                if not q:
                    continue
                price = float(q["price"])
                prev = float(q.get("prev_close") or price) or price
                volume = float(q.get("volume") or 0)
                value = float(q.get("value") or 0) or price * volume
                _add(code, price, prev, volume, value)

        # 1순위: Stooq — KIS에서 못 받은 코드 보충
        missing = [c for c in codes if c not in by_code]
        if missing:
            quotes = await _stooq.fetch_quotes(missing)
            for code, q in quotes.items():
                if not q:
                    continue
                price = float(q["price"])
                prev = float(q.get("prev_close") or price) or price
                volume = float(q.get("volume") or 0)
                _add(code, price, prev, volume)

        # 2순위: yfinance — 여전히 누락된 코드만 채움
        missing = [c for c in codes if c not in by_code]
        if missing:
            logger.info("US popular: yfinance fallback for {} missing", len(missing))

            def _yf_fetch(targets: list[str]) -> list[dict]:
                try:
                    import concurrent.futures

                    import yfinance as yf  # type: ignore

                    def one(code: str) -> dict | None:
                        try:
                            t = yf.Ticker(code)
                            hist = t.history(period="5d", auto_adjust=False)
                            if hist.empty:
                                return None
                            last = hist.iloc[-1]
                            prev = hist.iloc[-2] if len(hist) >= 2 else last
                            price = float(last["Close"])
                            prev_close = float(prev["Close"]) or price
                            volume = float(last["Volume"])
                            return {
                                "code": code,
                                "price": price,
                                "prev_close": prev_close,
                                "volume": volume,
                            }
                        except Exception:
                            return None

                    res: list[dict] = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
                        for r in ex.map(one, targets, timeout=25):
                            if r:
                                res.append(r)
                    return res
                except Exception as e:
                    logger.warning("yfinance fallback failed: {}", e)
                    return []

            try:
                yf_rows = await asyncio.wait_for(
                    asyncio.to_thread(_yf_fetch, missing), timeout=28.0
                )
            except asyncio.TimeoutError:
                logger.warning("yfinance fallback timeout")
                yf_rows = []
            for r in yf_rows:
                _add(r["code"], r["price"], r["prev_close"], r["volume"])

        out = list(by_code.values())

        # 모든 소스 실패 시: 가격 0인 placeholder는 표시하지 않음
        # (사용자가 클릭해도 의미 없는 항목이 떠 있는 게 더 혼란스러움)
        if not out:
            logger.warning("US popular all-failed, returning empty")

        _store(("US", sort), _sort_rows(list(out), sort))
        for s in ("value", "volume", "change"):
            if s != sort:
                _store(("US", s), _sort_rows(list(out), s))  # type: ignore
        return _sort_rows(out, sort)[:limit]


# ------------------------------------------------------------------ dispatcher

async def popular(market: Market, sort: Sort = "value", limit: int = 30) -> list[dict]:
    if market == "UPBIT":
        return await popular_upbit(sort, limit)
    if market == "KRX":
        return await popular_krx(sort, limit)
    if market == "US":
        return await popular_us(sort, limit)
    return []
