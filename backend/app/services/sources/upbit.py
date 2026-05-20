"""Upbit 공개 API — 인증 불필요.

- 마켓 마스터: GET /v1/market/all?isDetails=false
- 현재가:     GET /v1/ticker?markets=KRW-BTC,KRW-ETH,...

심볼 코드 규칙: 'KRW-BTC' 형식 그대로 사용.
"""
from __future__ import annotations

from decimal import Decimal

import httpx
from loguru import logger

BASE = "https://api.upbit.com"


async def fetch_markets() -> list[dict]:
    """원화 마켓만 반환."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{BASE}/v1/market/all", params={"isDetails": "false"})
        r.raise_for_status()
        all_mk = r.json()
    return [m for m in all_mk if m["market"].startswith("KRW-")]


async def fetch_tickers_full(codes: list[str]) -> list[dict]:
    """원시 ticker 행 반환 — 거래대금 등 부가정보 포함."""
    if not codes:
        return []
    out: list[dict] = []
    CHUNK = 100
    async with httpx.AsyncClient(timeout=10) as c:
        for i in range(0, len(codes), CHUNK):
            chunk = codes[i : i + CHUNK]
            r = await c.get(f"{BASE}/v1/ticker", params={"markets": ",".join(chunk)})
            if r.status_code != 200:
                continue
            out.extend(r.json())
    return out


async def fetch_prices(codes: list[str]) -> dict[str, dict]:
    """{code: {price, prev_close}}.

    Upbit는 한 번에 다수 시세 조회 가능 (~100개 권장).
    """
    if not codes:
        return {}
    out: dict[str, dict] = {}
    # 청크로 나눠 호출
    CHUNK = 100
    async with httpx.AsyncClient(timeout=10) as c:
        for i in range(0, len(codes), CHUNK):
            chunk = codes[i : i + CHUNK]
            r = await c.get(f"{BASE}/v1/ticker", params={"markets": ",".join(chunk)})
            if r.status_code != 200:
                logger.warning("upbit ticker chunk failed: {} {}", r.status_code, r.text[:200])
                continue
            for row in r.json():
                out[row["market"]] = {
                    "price": Decimal(str(row["trade_price"])),
                    "prev_close": Decimal(str(row["prev_closing_price"])),
                }
    return out
