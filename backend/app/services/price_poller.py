"""보유/관심 종목 시세 폴러.

- 1초 틱: holdings.symbol ∪ watchlist.symbol 의 활성 종목을 그룹 폴링
- KRX/미국주식은 정규장 + 폴링간격을 시장별로 조정 (KIS rate limit)
- UPBIT는 24/7
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Holding, Price, Symbol, Watchlist
from .market_calendar import is_market_open
from .quotes import fetch_many

# 시장별 폴링 간격 (초) — Rate limit 고려
INTERVALS = {
    "UPBIT": 1.0,
    "KRX": 1.0,    # 모의 2건/초인데 활성 종목 5개 이하 기준
    "NASDAQ": 5.0, # yfinance는 좀 보수적으로
    "NYSE": 5.0,
}


def _active_codes(db: Session) -> dict[str, list[str]]:
    """시장별 활성 종목 코드 리스트."""
    q = (
        select(Symbol.market, Symbol.code)
        .distinct()
        .where(
            Symbol.id.in_(
                select(Holding.symbol_id).where(Holding.qty > 0).union(select(Watchlist.symbol_id))
            )
        )
    )
    rows = db.execute(q).all()
    out: dict[str, list[str]] = {}
    for market, code in rows:
        out.setdefault(market, []).append(code)
    return out


def _upsert_prices(db: Session, market: str, quotes: dict[str, dict]) -> None:
    if not quotes:
        return
    codes = list(quotes.keys())
    rows = (
        db.execute(
            select(Symbol.id, Symbol.code).where(
                Symbol.market == market, Symbol.code.in_(codes)
            )
        )
        .all()
    )
    id_by_code = {c: i for i, c in rows}
    now = datetime.utcnow()
    for code, q in quotes.items():
        sid = id_by_code.get(code)
        if not sid:
            continue
        existing = db.get(Price, sid)
        if existing:
            existing.price = q["price"]
            existing.prev_close = q.get("prev_close")
            existing.ts = now
        else:
            db.add(
                Price(
                    symbol_id=sid,
                    price=q["price"],
                    prev_close=q.get("prev_close"),
                    ts=now,
                )
            )
    db.commit()


async def _poll_market(market: str) -> None:
    interval = INTERVALS.get(market, 5.0)
    while True:
        try:
            db = SessionLocal()
            try:
                by_market = _active_codes(db)
                codes = by_market.get(market, [])
            finally:
                db.close()

            if not codes:
                await asyncio.sleep(interval)
                continue

            if market != "UPBIT" and not is_market_open(market):
                # 장 외 시간엔 폴링 부담 줄이기
                await asyncio.sleep(30)
                continue

            quotes = await fetch_many(market, codes)
            if quotes:
                db = SessionLocal()
                try:
                    _upsert_prices(db, market, quotes)
                finally:
                    db.close()
        except Exception as e:
            logger.exception("poller {} error: {}", market, e)
        await asyncio.sleep(interval)


async def run_pollers() -> None:
    """모든 시장 폴러 동시 실행."""
    await asyncio.gather(
        _poll_market("UPBIT"),
        _poll_market("KRX"),
        _poll_market("NASDAQ"),
        _poll_market("NYSE"),
    )
