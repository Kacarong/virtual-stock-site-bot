"""FastAPI 엔트리포인트."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .config import settings
from .db import init_db
from .routers import (
    admin_router,
    auth_router,
    health_router,
    market_router,
    orders_router,
    portfolio_router,
    watchlist_router,
)

app = FastAPI(title="papertrade API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router.router)
app.include_router(auth_router.router)
app.include_router(market_router.router)
app.include_router(watchlist_router.router)
app.include_router(orders_router.router)
app.include_router(portfolio_router.router)
app.include_router(admin_router.router)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Initializing DB schema...")
    init_db()
    logger.info(
        "DB ready. DEV_LOGIN={} INITIAL_CASH_KRW={} KIS_ENV={}",
        settings.DEV_LOGIN,
        settings.INITIAL_CASH_KRW,
        settings.KIS_ENV,
    )
    # 시드 동기화 — 외부 의존 없이 종목 마스터 보장 (worker 안 떠 있어도 검색 가능)
    try:
        from .services.symbol_sync import sync_krx_seeds, sync_us, sync_upbit

        n_kr = await sync_krx_seeds()
        n_us = await sync_us()
        n_up = await sync_upbit()
        logger.info("seed sync ok: KR={} US={} UPBIT={}", n_kr, n_us, n_up)
    except Exception as e:
        logger.warning("startup seed sync failed: {}", e)

    # 인기 종목 + 차트 히스토리 워밍업
    import asyncio as _aio
    from .services.history import get_history as _get_history
    from .services.popular import load_disk_cache as _load_disk_cache
    from .services.popular import popular as _popular

    # 디스크에 백업된 마지막 정확한 popular 데이터 로드 (재시작 직후 즉시 응답용)
    _load_disk_cache()

    async def _warmup() -> None:
        # KRX 전종목 마스터 동기화 (KOSPI+KOSDAQ 약 2500종목, 검색 풀세트 확보)
        try:
            from .services.symbol_sync import sync_krx as _sync_krx

            n_krx_full = await _sync_krx()
            logger.info("KRX full sync done: {} symbols", n_krx_full)
        except Exception as e:
            logger.warning("KRX full sync failed: {}", e)

        try:
            await _aio.gather(
                _popular("KRX", "value", 30),
                _popular("US", "value", 30),
                _popular("UPBIT", "value", 30),
                return_exceptions=True,
            )
            logger.info("popular warmup done")
        except Exception as e:
            logger.warning("popular warmup failed: {}", e)

        # 인기 상위 10종목의 일봉 히스토리도 미리 적재 (차트 첫 진입 빠르게)
        try:
            top: list[tuple[str, str]] = []
            for m in ("KRX", "US", "UPBIT"):
                rows = await _popular(m, "value", 10)
                top.extend([(r["market"], r["code"]) for r in rows[:10]])
            tasks = [_get_history(mk, cd, "1d") for mk, cd in top]
            await _aio.gather(*tasks, return_exceptions=True)
            logger.info("history warmup done: {} symbols", len(top))
        except Exception as e:
            logger.warning("history warmup failed: {}", e)

    _aio.create_task(_warmup())


@app.get("/")
def root() -> dict:
    return {"service": "papertrade", "stage": 1, "docs": "/docs"}
