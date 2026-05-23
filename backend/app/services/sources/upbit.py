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


async def fetch_candles(code: str, unit: str = "1d", count: int = 200) -> list[dict]:
    """캔들 조회. unit: 1d / 1m / 5m / 15m / 60m / weeks / months."""
    if unit == "1d":
        url = f"{BASE}/v1/candles/days"
        params = {"market": code, "count": min(count, 200)}
    elif unit == "weeks":
        url = f"{BASE}/v1/candles/weeks"
        params = {"market": code, "count": min(count, 200)}
    elif unit == "months":
        url = f"{BASE}/v1/candles/months"
        params = {"market": code, "count": min(count, 200)}
    elif unit.endswith("m"):
        minutes = int(unit[:-1])
        url = f"{BASE}/v1/candles/minutes/{minutes}"
        params = {"market": code, "count": min(count, 200)}
    else:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("upbit candles failed {} {}: {}", code, unit, e)
        return []


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
    유효 코드를 사전 필터링 — 폐지/리네임된 코드(예: KRW-MATIC) 하나 때문에
    chunk 전체가 404로 실패하는 것을 방지.
    """
    if not codes:
        return {}

    # 1) 유효 KRW 마켓 화이트리스트로 사전 필터링
    try:
        valid = {m["market"] for m in await fetch_markets()}
        filtered = [c for c in codes if c in valid]
        dropped = set(codes) - set(filtered)
        if dropped:
            logger.info("upbit skip invalid markets: {}", sorted(dropped))
    except Exception as e:
        logger.warning("upbit market_all failed, no prefilter: {}", e)
        filtered = list(codes)

    out: dict[str, dict] = {}
    CHUNK = 100

    async def _fetch_one(client: httpx.AsyncClient, chunk: list[str]) -> None:
        if not chunk:
            return
        try:
            r = await client.get(f"{BASE}/v1/ticker", params={"markets": ",".join(chunk)})
            if r.status_code == 200:
                for row in r.json():
                    out[row["market"]] = {
                        "price": Decimal(str(row["trade_price"])),
                        "prev_close": Decimal(str(row["prev_closing_price"])),
                    }
                return
            # 404 등은 chunk 안에 잘못된 코드가 있다는 뜻 → 코드 단위로 fallback
            if r.status_code == 404 and len(chunk) > 1:
                for code in chunk:
                    try:
                        rr = await client.get(
                            f"{BASE}/v1/ticker", params={"markets": code}
                        )
                        if rr.status_code == 200:
                            for row in rr.json():
                                out[row["market"]] = {
                                    "price": Decimal(str(row["trade_price"])),
                                    "prev_close": Decimal(str(row["prev_closing_price"])),
                                }
                    except Exception:
                        continue
                return
            logger.warning(
                "upbit ticker chunk failed: {} {}", r.status_code, r.text[:200]
            )
        except Exception as e:
            logger.warning("upbit ticker exception: {}", e)

    async with httpx.AsyncClient(timeout=10) as c:
        for i in range(0, len(filtered), CHUNK):
            await _fetch_one(c, filtered[i : i + CHUNK])
    return out
