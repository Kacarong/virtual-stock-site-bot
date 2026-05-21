"""차트용 OHLC 히스토리.

소스 우선순위 (NAS에서 yfinance 자주 죽음):
- UPBIT: 공개 API /v1/candles/...                  (모든 interval 지원)
- KRX:   KIS API (일/분봉) → yfinance fallback
- US:    yfinance (1m/1h 가능) → Stooq (1d만)

지원 interval: 1m / 5m / 1h / 1d
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Literal

from loguru import logger

from .sources import kis as _kis
from .sources import stooq as _stooq
from .sources import upbit as _upbit

Interval = Literal["1m", "5m", "1h", "1d"]


def _yf_symbol(market: str, code: str) -> str:
    if market == "KRX":
        return f"{code}.KS"
    return code


async def _yf_history(market: str, code: str, period: str, interval: str) -> list[dict]:
    def _go() -> list[dict]:
        try:
            import yfinance as yf  # type: ignore

            t = yf.Ticker(_yf_symbol(market, code))
            df = t.history(period=period, interval=interval, auto_adjust=False)
            if df.empty:
                return []
            out: list[dict] = []
            for ts, row in df.iterrows():
                out.append(
                    {
                        "time": int(ts.timestamp()),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume", 0) or 0),
                    }
                )
            return out
        except Exception as e:
            logger.warning("yf history failed {} {}: {}", market, code, e)
            return []

    return await asyncio.to_thread(_go)


def _upbit_normalize(rows: list[dict]) -> list[dict]:
    out = []
    for row in reversed(rows):
        try:
            ts_str = row.get("candle_date_time_utc") or row.get("candle_date_time_kst")
            if not ts_str:
                continue
            ts = int(datetime.fromisoformat(ts_str).timestamp())
            out.append(
                {
                    "time": ts,
                    "open": float(row["opening_price"]),
                    "high": float(row["high_price"]),
                    "low": float(row["low_price"]),
                    "close": float(row["trade_price"]),
                    "volume": float(row.get("candle_acc_trade_volume") or 0),
                }
            )
        except Exception:
            continue
    return out


async def _upbit_history(code: str, interval: Interval) -> list[dict]:
    unit_map = {"1m": "1m", "5m": "5m", "1h": "60m", "1d": "1d"}
    unit = unit_map.get(interval, "1d")
    rows = await _upbit.fetch_candles(code, unit=unit, count=200)
    return _upbit_normalize(rows)


async def _krx_history(code: str, interval: Interval) -> list[dict]:
    # KIS 우선
    if interval == "1d":
        rows = await _kis.fetch_daily_candles(code, count=180)
        if rows:
            return rows
    elif interval == "1m":
        rows = await _kis.fetch_minute_candles(code, count=200)
        if rows:
            return rows
    # 그 외(5m/1h) 또는 KIS 실패 → yfinance fallback
    period_map = {"1m": "5d", "5m": "5d", "1h": "1mo", "1d": "6mo"}
    yf_interval = {"1m": "1m", "5m": "5m", "1h": "60m", "1d": "1d"}[interval]
    return await _yf_history("KRX", code, period_map[interval], yf_interval)


async def _us_history(market: str, code: str, interval: Interval) -> list[dict]:
    # 1d 는 Stooq 우선 (안정적)
    if interval == "1d":
        rows = await _stooq.fetch_history(code, count=180)
        if rows:
            return rows
    period_map = {"1m": "5d", "5m": "5d", "1h": "1mo", "1d": "6mo"}
    yf_interval = {"1m": "1m", "5m": "5m", "1h": "60m", "1d": "1d"}[interval]
    return await _yf_history(market, code, period_map[interval], yf_interval)


async def get_history(market: str, code: str, interval: Interval = "1d") -> list[dict]:
    market = market.upper()
    if market == "UPBIT":
        return await _upbit_history(code, interval)
    if market == "KRX":
        return await _krx_history(code, interval)
    if market in ("NASDAQ", "NYSE"):
        return await _us_history(market, code, interval)
    return []
