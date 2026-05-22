"""Stooq 공개 CSV API — 인증 불필요, 글로벌 액세스.

- 미국 주식: AAPL → aapl.us
- 다수 종목 일괄: ?s=aapl.us+msft.us+nvda.us
- 응답: CSV (Symbol,Date,Time,Open,High,Low,Close,Volume)

NAS에서 yfinance가 막힐 때 US 시세용 폴백.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
from loguru import logger

BASE = "https://stooq.com/q/l/"
HIST_BASE = "https://stooq.com/q/d/l/"


async def fetch_history(code: str, count: int = 180) -> list[dict]:
    """일봉 히스토리 — Stooq d/l 엔드포인트 (CSV)."""
    sym = code.lower().replace("-", "-") + ".us"
    url = f"{HIST_BASE}?s={sym}&i=d"
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(url)
            r.raise_for_status()
            text = r.text
    except Exception as e:
        logger.warning("stooq history failed {}: {}", code, e)
        return []
    from datetime import datetime as _dt

    out: list[dict] = []
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return []
    # header: Date,Open,High,Low,Close,Volume
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        try:
            ts = int(_dt.strptime(parts[0], "%Y-%m-%d").timestamp())
            out.append(
                {
                    "time": ts,
                    "open": float(parts[1]),
                    "high": float(parts[2]),
                    "low": float(parts[3]),
                    "close": float(parts[4]),
                    "volume": float(parts[5] or 0),
                }
            )
        except Exception:
            continue
    return out[-count:]


async def _stooq_chunk(client: httpx.AsyncClient, syms_param: str) -> str:
    url = f"{BASE}?s={syms_param}&f=sd2t2ohlcv&h&e=csv"
    r = await client.get(url)
    r.raise_for_status()
    return r.text


async def fetch_quotes_kr(codes: list[str]) -> dict[str, dict]:
    """Stooq로 KR 주식 quote 일괄 조회. {CODE: {price, prev_close, volume}}.

    KRX 코드는 6자리 숫자 (예: 005930). Stooq에서는 `005930.kr` 형식.
    Stooq는 한 요청당 안정적으로 5개 정도까지만 응답 → 청크 5개로 끊고 병렬 호출.
    """
    if not codes:
        return {}
    CHUNK = 5
    chunks = [codes[i:i+CHUNK] for i in range(0, len(codes), CHUNK)]

    async def one(chunk: list[str], client: httpx.AsyncClient) -> str:
        syms = "+".join([f"{c}.kr" for c in chunk])
        try:
            return await _stooq_chunk(client, syms)
        except Exception as e:
            logger.debug("stooq KR chunk fail: {}", e)
            return ""

    out: dict[str, dict] = {}
    # httpx로 동시 ~20개씩 병렬
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=20)
    async with httpx.AsyncClient(timeout=8, limits=limits) as client:
        texts = await asyncio.gather(*[one(ch, client) for ch in chunks])

    for text in texts:
        if not text:
            continue
        lines = text.strip().splitlines()
        if len(lines) < 2:
            continue
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 8:
                continue
            try:
                sym_raw = parts[0]
                if ".KR" not in sym_raw.upper():
                    continue
                sym = sym_raw.split(".")[0]
                close_str, open_str, vol_str = parts[6], parts[3], parts[7]
                if close_str in ("N/D", "") or open_str in ("N/D", ""):
                    continue
                close = Decimal(close_str)
                open_ = Decimal(open_str)
                vol = Decimal(vol_str) if vol_str not in ("N/D", "") else Decimal("0")
                out[sym] = {
                    "price": close,
                    "prev_close": open_,
                    "volume": vol,
                }
            except Exception:
                continue
    return out


async def fetch_quotes(codes: list[str]) -> dict[str, dict]:
    """Stooq로 US 주식 quote 일괄 조회. {CODE: {price, prev_close, volume}}.

    Stooq는 한 요청당 5개 정도까지 안정적으로 응답 → 청크 5개로 끊고 병렬 호출.
    """
    if not codes:
        return {}
    CHUNK = 5
    chunks = [codes[i:i+CHUNK] for i in range(0, len(codes), CHUNK)]

    async def one(chunk: list[str], client: httpx.AsyncClient) -> str:
        syms = "+".join([f"{c.lower().replace('.', '-')}.us" for c in chunk])
        try:
            return await _stooq_chunk(client, syms)
        except Exception as e:
            logger.debug("stooq US chunk fail: {}", e)
            return ""

    out: dict[str, dict] = {}
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=20)
    async with httpx.AsyncClient(timeout=8, limits=limits) as client:
        texts = await asyncio.gather(*[one(ch, client) for ch in chunks])

    for text in texts:
        if not text:
            continue
        lines = text.strip().splitlines()
        if len(lines) < 2:
            continue
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 8:
                continue
            try:
                sym_raw = parts[0]
                if "." not in sym_raw:
                    continue
                sym = sym_raw.split(".")[0].upper().replace("-", ".")
                sym = sym.replace(".", "-") if sym == "BRK-B" or "-" in parts[0] else sym
                close_str, open_str, vol_str = parts[6], parts[3], parts[7]
                if close_str in ("N/D", "") or open_str in ("N/D", ""):
                    continue
                close = Decimal(close_str)
                open_ = Decimal(open_str)
                vol = Decimal(vol_str) if vol_str not in ("N/D", "") else Decimal("0")
                out[sym] = {
                    "price": close,
                    "prev_close": open_,
                    "volume": vol,
                }
            except Exception:
                continue
    return out
