"""통합 시세 서비스.

- 보유/관심 종목: price_poller가 1초마다 DB의 prices 테이블 갱신
- 그 외 종목: get_quote()가 30초 캐시 + on-demand 소스 호출

market: KRX / NASDAQ / NYSE / UPBIT
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal

from .sources import kis, upbit, yfinance_src

# in-memory 캐시: (market, code) → (ts, quote)
_ondemand_cache: dict[tuple[str, str], tuple[float, dict]] = {}
CACHE_TTL = 30.0  # 초


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
        return await kis.fetch_price(code)
    if market in ("NASDAQ", "NYSE"):
        return await yfinance_src.fetch_quote(code)
    return None


async def fetch_many(market: str, codes: list[str]) -> dict[str, dict]:
    """소스에 한 번에 다수 질의."""
    if not codes:
        return {}
    if market == "UPBIT":
        return await upbit.fetch_prices(codes)
    if market == "KRX":
        return await kis.fetch_prices(codes)
    if market in ("NASDAQ", "NYSE"):
        return await yfinance_src.fetch_quotes(codes)
    return {}


async def get_quote(market: str, code: str) -> dict | None:
    """캐시 + on-demand."""
    key = (market, code)
    now = time.time()
    cached = _ondemand_cache.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]
    q = await fetch_one(market, code)
    if q:
        _ondemand_cache[key] = (now, q)
    return q
