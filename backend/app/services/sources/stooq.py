"""Stooq 공개 CSV API — 인증 불필요, 글로벌 액세스.

- 미국 주식: AAPL → aapl.us
- 다수 종목 일괄: ?s=aapl.us+msft.us+nvda.us
- 응답: CSV (Symbol,Date,Time,Open,High,Low,Close,Volume)

NAS에서 yfinance가 막힐 때 US 시세용 폴백.
"""
from __future__ import annotations

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
        async with httpx.AsyncClient(timeout=15) as c:
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


async def fetch_quotes(codes: list[str]) -> dict[str, dict]:
    """Stooq로 US 주식 quote 일괄 조회. {CODE: {price, prev_close, volume}}.

    Stooq는 한 응답 안에 Open=시가/Close=현재가. prev_close는 별도 호출 필요해서
    여기서는 'Open' 대신 보다 정확한 전일 종가를 위해 d1 + d2 호출 가능하지만,
    당장 정렬용으로는 close + volume + change_pct(=(close-open)/open*100 임시) 사용.
    더 정확히 하려면 stooq history API 호출 필요.
    """
    if not codes:
        return {}
    syms = "+".join([f"{c.lower().replace('.', '-')}.us" for c in codes])
    url = f"{BASE}?s={syms}&f=sd2t2ohlcv&h&e=csv"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url)
            r.raise_for_status()
            text = r.text
    except Exception as e:
        logger.warning("stooq fetch failed: {}", e)
        return {}

    out: dict[str, dict] = {}
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return {}
    # header: Symbol,Date,Time,Open,High,Low,Close,Volume
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 8:
            continue
        try:
            sym_raw = parts[0]
            if "." not in sym_raw:
                continue
            sym = sym_raw.split(".")[0].upper().replace("-", ".")  # brk-b → BRK.B (우리는 BRK-B 사용)
            # 우리 코드 표기로 되돌리기
            sym = sym.replace(".", "-") if sym == "BRK-B" or "-" in parts[0] else sym
            close_str, open_str, vol_str = parts[6], parts[3], parts[7]
            if close_str in ("N/D", "") or open_str in ("N/D", ""):
                continue
            close = Decimal(close_str)
            open_ = Decimal(open_str)
            vol = Decimal(vol_str) if vol_str not in ("N/D", "") else Decimal("0")
            out[sym] = {
                "price": close,
                "prev_close": open_,  # 정확한 전일종가 아님 (당일 시가). UI에서 큰 차이 없음.
                "volume": vol,
            }
        except Exception:
            continue
    return out
