"""Worker 엔트리포인트.

- 시세 폴러 (보유/관심 종목 1초 폴링, UPBIT 즉시, KRX/US는 정규장만)
- 종목 마스터 일일 동기화 (매일 새벽 KST 05:00)
- 주문 매처는 Stage 3에서 추가
"""
from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from .db import init_db
from .services.price_poller import run_pollers
from .services.symbol_sync import sync_all


async def main() -> None:
    logger.info("Worker starting (stage 2)")
    init_db()

    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    # 매일 05:00 KST 종목 마스터 동기화
    scheduler.add_job(
        sync_all,
        CronTrigger(hour=5, minute=0),
        id="symbol_sync",
        replace_existing=True,
    )
    scheduler.start()

    # 시작 시 1회 동기화
    try:
        await sync_all()
    except Exception as e:
        logger.warning("initial sync failed: {}", e)

    # 폴러는 무한 루프
    await run_pollers()


if __name__ == "__main__":
    asyncio.run(main())
