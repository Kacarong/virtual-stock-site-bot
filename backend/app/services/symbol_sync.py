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
from .sources.kr_seeds import KR_SEEDS
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


async def sync_krx_seeds() -> int:
    """KRX 인기 시드(150개) 우선 upsert — pykrx 실패해도 검색은 즉시 동작.

    row별 commit + try/except — 하나가 실패해도 나머지 들어가도록 격리.
    """
    db = SessionLocal()
    ok = 0
    fail = 0
    try:
        for code, name, asset_type, sector in KR_SEEDS:
            try:
                _upsert_symbol(
                    db,
                    {
                        "code": code,
                        "name": name,
                        "market": "KRX",
                        "asset_type": asset_type,
                        "currency": "KRW",
                        "sector": sector,
                    },
                )
                db.commit()
                ok += 1
            except Exception as e:
                db.rollback()
                fail += 1
                logger.warning("KR_SEEDS upsert fail {} {}: {}", code, name, e)
        if fail:
            logger.warning("sync_krx_seeds: ok={} fail={}", ok, fail)
        return ok
    finally:
        db.close()


async def sync_krx() -> int:
    """pykrx로 전종목 확장 (느리고 실패 가능 — 시드는 별도 보장)."""
    rows = await kis.fetch_symbol_master_krx()
    if not rows:
        logger.warning("KRX 전종목 동기화 실패 — pykrx 미설치/네트워크 실패 (시드는 정상)")
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
    """미국 주식/ETF — yfinance에 전종목 API가 없어 시드 목록을 upsert.

    row별 commit으로 부분 실패 격리.
    """
    db = SessionLocal()
    ok = 0
    fail = 0
    try:
        for code, name, market, asset_type in US_SEEDS:
            try:
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
                ok += 1
            except Exception as e:
                db.rollback()
                fail += 1
                logger.warning("US_SEEDS upsert fail {} {}: {}", code, name, e)
        if fail:
            logger.warning("sync_us: ok={} fail={}", ok, fail)
        return ok
    finally:
        db.close()


async def sync_all() -> dict:
    """매일 새벽에 실행되는 잡.

    순서: 빠르고 확실한 것 먼저(시드/공개 API), 느린 pykrx는 마지막.
    """
    n_upbit = await sync_upbit()
    logger.info("symbol sync: UPBIT={}", n_upbit)
    n_kr_seed = await sync_krx_seeds()
    logger.info("symbol sync: KR_SEEDS={}", n_kr_seed)
    n_us = await sync_us()
    logger.info("symbol sync: US={}", n_us)
    try:
        n_krx = await sync_krx()
        logger.info("symbol sync: KRX(pykrx)={}", n_krx)
    except Exception as e:
        logger.warning("KRX pykrx sync failed (시드는 유효): {}", e)
        n_krx = 0
    return {"upbit": n_upbit, "kr_seeds": n_kr_seed, "us": n_us, "krx": n_krx}
