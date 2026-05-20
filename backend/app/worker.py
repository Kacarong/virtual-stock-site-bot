"""Worker 엔트리포인트.

Stage 1: DB 초기화만 보장하고 대기.
Stage 2~: 시세 폴러, 주문 매처, 종목 마스터 동기화 등을 APScheduler로 돌림.
"""
from __future__ import annotations

import time

from loguru import logger

from .db import init_db


def main() -> None:
    logger.info("Worker starting (stage 1 stub)")
    init_db()
    logger.info("DB ready. Worker idle — will be replaced in Stage 2 (pollers + matchers).")
    # Stage 2에서 APScheduler 기반 잡 등록 예정
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
