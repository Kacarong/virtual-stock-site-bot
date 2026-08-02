"""통합 시세 서비스.

- 보유/관심 종목: price_poller가 1초마다 DB의 prices 테이블 갱신
- 그 외 종목: get_quote()가 30초 캐시 + on-demand 소스 호출
              stale-while-revalidate: 캐시가 있으면 즉시 반환하면서 백그라운드 갱신

market: KRX / NASDAQ / NYSE / UPBIT
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal

from loguru import logger

from .sources import kis, stooq, toss, upbit, yfinance_src

# in-memory 캐시: (market, code) → (ts, quote)
_ondemand_cache: dict[tuple[str, str], tuple[float, dict]] = {}
CACHE_TTL = 30.0  # 초 (이 시간 안이면 캐시 그대로)
STALE_TTL = 600.0  # 초 (이 시간 안이면 stale-while-revalidate)
# 장시간 구동 시 캐시가 무한정 커져 메모리/조회가 느려지지 않도록 상한(오래된 것부터 제거)
_MAX_CACHE = 3000


def _evict_ondemand() -> None:
    if len(_ondemand_cache) <= _MAX_CACHE:
        return
    # ts 오래된 순으로 초과분 제거
    overflow = len(_ondemand_cache) - _MAX_CACHE
    for key, _ in sorted(_ondemand_cache.items(), key=lambda kv: kv[1][0])[:overflow]:
        _ondemand_cache.pop(key, None)

# 동일 종목 동시 호출 dedup
_inflight: dict[tuple[str, str], asyncio.Task] = {}


@dataclass
class Quote:
    price: Decimal
    prev_close: Decimal | None


async def fetch_one(market: str, code: str) -> dict | None:
    """소스에 직접 질의."""
    if market == "UPBIT":
        m = await upbit.fetch_prices([code])
        return m.get(code)
    if market == "KRX":
        # Toss 주 공급자 → (폴백) KIS → pykrx 종가
        q = await toss.fetch_price(code)
        if q:
            return q
        q = await kis.fetch_price(code)
        if q:
            return q
        return await kis.fetch_price_pykrx(code)
    if market in ("NASDAQ", "NYSE", "AMEX"):
        # Toss 주 공급자 → (폴백) KIS 해외 → Stooq → yfinance
        q = await toss.fetch_price(code)
        if q:
            return q
        q = await kis.fetch_overseas_price(code, market)
        if q:
            return q
        sq = await stooq.fetch_quotes([code])
        if sq.get(code):
            return sq[code]
        return await yfinance_src.fetch_quote(code)
    return None


async def fetch_many(market: str, codes: list[str]) -> dict[str, dict]:
    """소스에 한 번에 다수 질의."""
    if not codes:
        return {}
    if market == "UPBIT":
        return await upbit.fetch_prices(codes)
    if market == "KRX":
        q = await toss.fetch_prices(codes)
        if q:
            return q
        return await kis.fetch_prices(codes)
    if market in ("NASDAQ", "NYSE", "AMEX"):
        q = await toss.fetch_prices(codes)
        if q:
            return q
        return await yfinance_src.fetch_quotes(codes)
    return {}


async def _fetch_and_store(market: str, code: str) -> dict | None:
    """fetch_one + 캐시 저장."""
    try:
        q = await fetch_one(market, code)
    except Exception as e:
        logger.warning("quote fetch failed {}/{}: {}", market, code, e)
        return None
    if q:
        _ondemand_cache[(market, code)] = (time.time(), q)
        _evict_ondemand()
    return q


def _ensure_inflight(market: str, code: str) -> asyncio.Task:
    """진행 중 task 있으면 그것을, 없으면 새로 생성하여 반환."""
    key = (market, code)
    t = _inflight.get(key)
    if t and not t.done():
        return t

    async def _runner():
        try:
            return await _fetch_and_store(market, code)
        finally:
            _inflight.pop(key, None)

    new_task = asyncio.create_task(_runner())
    _inflight[key] = new_task
    return new_task


def _spawn_refresh(market: str, code: str) -> None:
    """백그라운드 갱신 (이미 진행 중이면 skip)."""
    try:
        _ensure_inflight(market, code)
    except RuntimeError:
        pass  # 이벤트 루프 없음


async def get_quote(
    market: str, code: str, *, max_wait: float = 2.0
) -> dict | None:
    """캐시 + on-demand (stale-while-revalidate).

    - 캐시가 fresh(<30s) → 즉시 반환
    - 캐시가 stale(<600s) → 즉시 반환 + 백그라운드 갱신
    - 캐시 없음 → on-demand 호출 (max_wait 초 안에 못 받으면 None)
    """
    key = (market, code)
    now = time.time()
    cached = _ondemand_cache.get(key)

    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    if cached and now - cached[0] < STALE_TTL:
        # stale → 즉시 반환 + 백그라운드 갱신
        _spawn_refresh(market, code)
        return cached[1]

    # 캐시 없음 → on-demand (inflight 공유 + 타임아웃)
    task = _ensure_inflight(market, code)
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=max_wait)
    except asyncio.TimeoutError:
        # 타임아웃은 task가 계속 진행 → 다음 요청에서 캐시 hit
        return cached[1] if cached else None
