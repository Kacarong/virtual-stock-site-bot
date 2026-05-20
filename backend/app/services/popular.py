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
from .sources import upbit
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


# popular US용 인기 50개 (전체 시드 130개 중 시총 상위)
US_POPULAR_CODES = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "ORCL", "CRM",
    "AMD", "NFLX", "ADBE", "INTC", "QCOM", "CSCO", "PLTR", "UBER", "SHOP", "ABNB",
    "JPM", "V", "MA", "BAC", "WFC", "GS", "BRK-B", "BLK", "COIN",
    "WMT", "COST", "HD", "NKE", "SBUX", "MCD", "DIS", "KO",
    "LLY", "UNH", "JNJ", "ABBV", "XOM", "CVX",
    "BABA", "TSM", "ASML", "SMCI", "MSTR",
    "SPY", "QQQ", "VOO", "IBIT",
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

    def _fetch() -> list[dict]:
        try:
            from datetime import datetime, timedelta
            from pykrx import stock  # type: ignore

            # 가장 가까운 영업일 (오늘 데이터 없으면 -1, -2...)
            today = datetime.now()
            df = None
            for d in range(0, 7):
                date = (today - timedelta(days=d)).strftime("%Y%m%d")
                try:
                    df = stock.get_market_ohlcv_by_ticker(date=date, market="ALL")
                    if df is not None and len(df) > 0:
                        break
                except Exception:
                    continue
            if df is None or len(df) == 0:
                return []
            # 컬럼: 시가/고가/저가/종가/거래량/거래대금/등락률
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

    rows = await asyncio.to_thread(_fetch)

    # 이름 붙이기
    db = SessionLocal()
    try:
        name_by = {s.code: s.name for s in db.query(Symbol).filter(Symbol.market == "KRX").all()}
    finally:
        db.close()

    out = []
    for r in rows:
        code = str(r["code"])
        if code not in name_by:
            continue  # 마스터에 없는 종목 스킵
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
    if sort == "value":
        rows.sort(key=lambda x: x["value"], reverse=True)
    elif sort == "volume":
        rows.sort(key=lambda x: x["volume"], reverse=True)
    else:
        rows.sort(key=lambda x: x["change_pct"], reverse=True)
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

        def _fetch() -> list[dict]:
            try:
                import yfinance as yf  # type: ignore

                codes = US_POPULAR_CODES
                name_by = {c: n for c, n, _, _ in US_SEEDS}
                market_by = {c: m for c, _, m, _ in US_SEEDS}
                data = yf.download(
                    tickers=" ".join(codes),
                    period="2d",
                    interval="1d",
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )
                out: list[dict] = []
                for code in codes:
                    try:
                        d = data[code] if len(codes) > 1 else data
                        if d is None or len(d) == 0:
                            continue
                        last = d.iloc[-1]
                        prev = d.iloc[-2] if len(d) >= 2 else last
                        price = float(last["Close"])
                        prev_close = float(prev["Close"]) or price
                        volume = float(last["Volume"])
                        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
                        out.append(
                            {
                                "market": market_by.get(code, "NASDAQ"),
                                "code": code,
                                "name": name_by.get(code, code),
                                "price": price,
                                "change_pct": change_pct,
                                "volume": volume,
                                "value": price * volume,
                            }
                        )
                    except Exception:
                        continue
                return out
            except Exception as e:
                logger.warning("US popular fetch failed: {}", e)
                return []

        try:
            out = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=20.0)
        except asyncio.TimeoutError:
            logger.warning("US popular fetch timeout")
            out = []

        _store(("US", sort), _sort_rows(list(out), sort))
        # 다른 정렬도 같은 데이터로 미리 캐시
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
