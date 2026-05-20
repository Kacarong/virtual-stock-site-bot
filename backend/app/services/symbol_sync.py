"""종목 마스터 일일 동기화.

- KRX: pykrx로 전종목 + ETF
- UPBIT: 공개 API로 전체 원화마켓
- US: 빈 — 사용자가 검색 시 on-demand로 추가 (Stage 4)
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Symbol
from .sources import kis, upbit
from .sources.us_seeds import US_SEEDS


def _upsert_symbol(db: Session, row: dict) -> None:
    sym = (
        db.query(Symbol)
        .filter(Symbol.market == row["market"], Symbol.code == row["code"])
        .first()
    )
    if sym:
        if sym.name != row["name"] or sym.sector != row.get("sector"):
            sym.name = row["name"]
            sym.sector = row.get("sector")
        sym.is_active = True
        return
    db.add(
        Symbol(
            code=row["code"],
            name=row["name"],
            market=row["market"],
            asset_type=row["asset_type"],
            currency=row["currency"],
            sector=row.get("sector"),
            is_active=True,
        )
    )


async def sync_upbit() -> int:
    rows = await upbit.fetch_markets()
    db = SessionLocal()
    try:
        for m in rows:
            _upsert_symbol(
                db,
                {
                    "code": m["market"],
                    "name": m.get("korean_name") or m["market"],
                    "market": "UPBIT",
                    "asset_type": "CRYPTO",
                    "currency": "KRW",
                    "sector": "CRYPTO",
                },
            )
        db.commit()
        return len(rows)
    finally:
        db.close()


async def sync_krx() -> int:
    rows = await kis.fetch_symbol_master_krx()
    if not rows:
        logger.warning("KRX symbol master empty — pykrx 미설치/네트워크 실패 가능")
        return 0
    db = SessionLocal()
    try:
        for r in rows:
            _upsert_symbol(db, r)
        db.commit()
        return len(rows)
    finally:
        db.close()


async def sync_us() -> int:
    """미국 주식/ETF — yfinance에 전종목 API가 없어 시드 목록을 upsert."""
    db = SessionLocal()
    try:
        for code, name, market, asset_type in US_SEEDS:
            _upsert_symbol(
                db,
                {
                    "code": code,
                    "name": name,
                    "market": market,
                    "asset_type": asset_type,
                    "currency": "USD",
                    "sector": None,
                },
            )
        db.commit()
        return len(US_SEEDS)
    finally:
        db.close()


async def sync_all() -> dict:
    """매일 새벽에 실행되는 잡."""
    n_upbit = await sync_upbit()
    logger.info("symbol sync: UPBIT={}", n_upbit)
    n_krx = await sync_krx()
    logger.info("symbol sync: KRX={}", n_krx)
    n_us = await sync_us()
    logger.info("symbol sync: US={}", n_us)
    return {"upbit": n_upbit, "krx": n_krx, "us": n_us}
