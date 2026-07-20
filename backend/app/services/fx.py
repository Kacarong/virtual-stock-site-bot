"""USD/KRW 환율 캐시.

yfinance에서 USDKRW=X 를 받아서 1시간 캐싱.
실패 시 마지막 값 유지.
"""
from __future__ import annotations

import time
from decimal import Decimal

from loguru import logger

from .sources.toss import fetch_usdkrw as _toss_usdkrw
from .sources.yfinance_src import fetch_usdkrw as _yf_usdkrw

_cache: dict = {"rate": Decimal("1350"), "ts": 0.0}  # 기본값
TTL = 60 * 60  # 1시간


async def get_usdkrw() -> Decimal:
    now = time.time()
    if now - _cache["ts"] < TTL and _cache["rate"]:
        return _cache["rate"]
    rate = await _toss_usdkrw()
    if not rate:
        rate = await _yf_usdkrw()
    if rate:
        _cache["rate"] = rate
        _cache["ts"] = now
    else:
        logger.warning("USDKRW fetch failed, using cached/default {}", _cache["rate"])
    return _cache["rate"]
