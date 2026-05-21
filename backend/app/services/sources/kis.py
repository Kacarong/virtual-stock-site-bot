"""한국투자증권 Open API.

- 접근토큰: POST /oauth2/tokenP (24시간 유효, 캐싱)
- 현재가:   GET /uapi/domestic-stock/v1/quotations/inquire-price
  tr_id = FHKST01010100, params: FID_COND_MRKT_DIV_CODE=J, FID_INPUT_ISCD=종목코드

ENV:
  KIS_ENV = "vts"(모의) | "real"(실전)
  KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO

키가 없으면 모든 호출은 graceful None 반환.
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import httpx
from loguru import logger

from ...config import settings

BASE_REAL = "https://openapi.koreainvestment.com:9443"
BASE_VTS = "https://openapivts.koreainvestment.com:29443"


def _base() -> str:
    return BASE_VTS if settings.KIS_ENV == "vts" else BASE_REAL


def _configured() -> bool:
    return bool(settings.KIS_APP_KEY and settings.KIS_APP_SECRET)


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
                    f"{_base()}/oauth2/tokenP",
                    json={
                        "grant_type": "client_credentials",
                        "appkey": settings.KIS_APP_KEY,
                        "appsecret": settings.KIS_APP_SECRET,
                    },
                )
                r.raise_for_status()
                data = r.json()
                _token_cache["token"] = data["access_token"]
                _token_cache["exp"] = now + int(data.get("expires_in", 86400))
                return _token_cache["token"]
        except Exception as e:
            logger.warning("KIS token issue failed: {}", e)
            return None


async def fetch_price(code: str) -> dict | None:
    """국내주식 현재가. code='005930' 형식."""
    if not _configured():
        return None
    token = await get_access_token()
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{_base()}/uapi/domestic-stock/v1/quotations/inquire-price",
                params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": settings.KIS_APP_KEY,
                    "appsecret": settings.KIS_APP_SECRET,
                    "tr_id": "FHKST01010100",
                },
            )
            r.raise_for_status()
            o = r.json().get("output", {})
            if not o:
                return None
            out: dict = {
                "price": Decimal(o["stck_prpr"]),  # 주식 현재가
                "prev_close": Decimal(o.get("stck_sdpr") or o["stck_prpr"]),  # 전일종가
            }
            try:
                out["volume"] = Decimal(o.get("acml_vol") or 0)  # 누적거래량
                out["value"] = Decimal(o.get("acml_tr_pbmn") or 0)  # 누적거래대금
            except Exception:
                pass
            return out
    except Exception as e:
        logger.debug("KIS price fetch failed for {}: {}", code, e)
        return None


async def fetch_daily_candles(code: str, count: int = 100) -> list[dict]:
    """국내주식 일봉. TR=FHKST01010400 (기간별시세, 최대 100개)."""
    if not _configured():
        return []
    token = await get_access_token()
    if not token:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{_base()}/uapi/domestic-stock/v1/quotations/inquire-daily-price",
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": code,
                    "FID_PERIOD_DIV_CODE": "D",
                    "FID_ORG_ADJ_PRC": "0",
                },
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": settings.KIS_APP_KEY,
                    "appsecret": settings.KIS_APP_SECRET,
                    "tr_id": "FHKST01010400",
                },
            )
            r.raise_for_status()
            data = r.json()
        rows = data.get("output", []) or []
        out: list[dict] = []
        from datetime import datetime as _dt

        for row in reversed(rows[:count]):
            try:
                date = row.get("stck_bsop_date") or row.get("bstp_nmix_bsop_date")
                if not date:
                    continue
                ts = int(_dt.strptime(date, "%Y%m%d").timestamp())
                out.append(
                    {
                        "time": ts,
                        "open": float(row["stck_oprc"]),
                        "high": float(row["stck_hgpr"]),
                        "low": float(row["stck_lwpr"]),
                        "close": float(row["stck_clpr"]),
                        "volume": float(row.get("acml_vol") or 0),
                    }
                )
            except Exception:
                continue
        return out
    except Exception as e:
        logger.warning("KIS daily candles failed {}: {}", code, e)
        return []


async def fetch_minute_candles(code: str, count: int = 100) -> list[dict]:
    """국내주식 당일 분봉 (1분). TR=FHKST03010200."""
    if not _configured():
        return []
    token = await get_access_token()
    if not token:
        return []
    try:
        from datetime import datetime as _dt

        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f"{_base()}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                params={
                    "FID_ETC_CLS_CODE": "",
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": code,
                    "FID_INPUT_HOUR_1": "153000",  # 장마감 시간 기준 역순
                    "FID_PW_DATA_INCU_YN": "N",
                },
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": settings.KIS_APP_KEY,
                    "appsecret": settings.KIS_APP_SECRET,
                    "tr_id": "FHKST03010200",
                },
            )
            r.raise_for_status()
            data = r.json()
        rows = data.get("output2", []) or []
        out: list[dict] = []
        for row in reversed(rows[:count]):
            try:
                date = row["stck_bsop_date"]
                hhmm = row["stck_cntg_hour"]  # HHMMSS
                ts = int(_dt.strptime(date + hhmm, "%Y%m%d%H%M%S").timestamp())
                out.append(
                    {
                        "time": ts,
                        "open": float(row["stck_oprc"]),
                        "high": float(row["stck_hgpr"]),
                        "low": float(row["stck_lwpr"]),
                        "close": float(row["stck_prpr"]),
                        "volume": float(row.get("cntg_vol") or 0),
                    }
                )
            except Exception:
                continue
        return out
    except Exception as e:
        logger.warning("KIS minute candles failed {}: {}", code, e)
        return []


async def fetch_price_pykrx(code: str) -> dict | None:
    """KIS 실패 시 pykrx로 최근 영업일 종가 fallback."""
    def _fetch() -> dict | None:
        try:
            from datetime import datetime, timedelta
            from pykrx import stock  # type: ignore

            today = datetime.now()
            for d in range(0, 10):
                date = (today - timedelta(days=d)).strftime("%Y%m%d")
                try:
                    df = stock.get_market_ohlcv(date, date, code)
                    if df is not None and len(df) > 0:
                        last = df.iloc[-1]
                        close = Decimal(str(int(last["종가"])))
                        # 전일 종가
                        prev = close
                        try:
                            date2 = (today - timedelta(days=d + 7)).strftime("%Y%m%d")
                            df2 = stock.get_market_ohlcv(date2, date, code)
                            if df2 is not None and len(df2) >= 2:
                                prev = Decimal(str(int(df2.iloc[-2]["종가"])))
                        except Exception:
                            pass
                        return {"price": close, "prev_close": prev}
                except Exception:
                    continue
        except Exception as e:
            logger.debug("pykrx fallback failed for {}: {}", code, e)
        return None

    return await asyncio.to_thread(_fetch)


async def fetch_prices(codes: list[str]) -> dict[str, dict]:
    """다수 코드. KIS는 단건 API라 동시성 제어해서 순회."""
    sem = asyncio.Semaphore(2)  # 모의 초당 2건 한도

    async def one(code: str) -> tuple[str, dict | None]:
        async with sem:
            return code, await fetch_price(code)

    results = await asyncio.gather(*(one(c) for c in codes))
    return {c: q for c, q in results if q}


async def fetch_symbol_master_krx() -> list[dict]:
    """KRX 종목 마스터 — pykrx로 받는다 (KIS API에는 마스터 다운로드 별도)."""
    def _fetch() -> list[dict]:
        try:
            from pykrx import stock  # type: ignore

            out: list[dict] = []
            for mk in ("KOSPI", "KOSDAQ"):
                tickers = stock.get_market_ticker_list(market=mk)
                for code in tickers:
                    try:
                        name = stock.get_market_ticker_name(code)
                        out.append(
                            {
                                "code": code,
                                "name": name,
                                "market": "KRX",
                                "asset_type": "STOCK",
                                "currency": "KRW",
                                "sector": mk,
                            }
                        )
                    except Exception:
                        continue
            # ETF
            try:
                etf_tickers = stock.get_etf_ticker_list()
                for code in etf_tickers:
                    name = stock.get_etf_ticker_name(code)
                    out.append(
                        {
                            "code": code,
                            "name": name,
                            "market": "KRX",
                            "asset_type": "ETF",
                            "currency": "KRW",
                            "sector": "ETF",
                        }
                    )
            except Exception as e:
                logger.debug("pykrx ETF list skipped: {}", e)
            return out
        except Exception as e:
            logger.warning("pykrx symbol master failed: {}", e)
            return []

    return await asyncio.to_thread(_fetch)
