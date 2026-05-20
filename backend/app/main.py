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
def on_startup() -> None:
    logger.info("Initializing DB schema...")
    init_db()
    logger.info("DB ready. DEV_LOGIN={} INITIAL_CASH_KRW={}", settings.DEV_LOGIN, settings.INITIAL_CASH_KRW)


@app.get("/")
def root() -> dict:
    return {"service": "papertrade", "stage": 1, "docs": "/docs"}
