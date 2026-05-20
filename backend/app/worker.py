"""Worker 엔트리포인트.

- 시세 폴러 (시장별 비동기)
- 종목 마스터 일일 동기화 (매일 05:00 KST)
- 주문 매처 (1초 틱) — 시장가/지정가/예약 처리
"""
from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from .db import SessionLocal, init_db
from .services.engine import match_pending_orders
from .services.price_poller import run_pollers
from .services.symbol_sync import sync_all


async def matcher_loop() -> None:
    while True:
        try:
            db = SessionLocal()
            try:
                n = await match_pending_orders(db)
                if n:
                    logger.info("matcher filled {} orders", n)
            finally:
                db.close()
        except Exception as e:
            logger.exception("matcher loop error: {}", e)
        await asyncio.sleep(1)


async def main() -> None:
    logger.info("Worker starting (stage 3)")
    init_db()

    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        sync_all,
        CronTrigger(hour=5, minute=0),
        id="symbol_sync",
        replace_existing=True,
    )
    scheduler.start()

    try:
        await sync_all()
    except Exception as e:
        logger.warning("initial sync failed: {}", e)

    # 폴러 + 매처 동시 실행
    await asyncio.gather(
        run_pollers(),
        matcher_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
