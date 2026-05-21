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

Interval = Literal["1m", "5m", "1h", "1d", "1w", "1mo", "all"]


def _aggregate(daily: list[dict], unit: str) -> list[dict]:
    """일봉 → 주봉('W') / 월봉('M') 집계."""
    from datetime import datetime as _dt

    groups: dict[str, dict] = {}
    keys: list[str] = []
    for c in daily:
        try:
            d = _dt.fromtimestamp(c["time"])
        except Exception:
            continue
        if unit == "W":
            iso = d.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
        else:  # 'M'
            key = f"{d.year}-{d.month:02d}"
        if key not in groups:
            groups[key] = {
                "time": c["time"],
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c.get("volume", 0) or 0,
            }
            keys.append(key)
        else:
            g = groups[key]
            g["high"] = max(g["high"], c["high"])
            g["low"] = min(g["low"], c["low"])
            g["close"] = c["close"]
            g["volume"] = (g.get("volume", 0) or 0) + (c.get("volume", 0) or 0)
            g["time"] = c["time"]
    return [groups[k] for k in keys]


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
    # 주/월: Upbit 전용 엔드포인트
    if interval == "1w":
        rows = await _upbit.fetch_candles(code, unit="weeks", count=200)
        return _upbit_normalize(rows)
    if interval == "1mo":
        rows = await _upbit.fetch_candles(code, unit="months", count=200)
        return _upbit_normalize(rows)
    if interval == "all":
        rows = await _upbit.fetch_candles(code, unit="1d", count=200)
        return _upbit_normalize(rows)
    unit_map = {"1m": "1m", "5m": "5m", "1h": "60m", "1d": "1d"}
    unit = unit_map.get(interval, "1d")
    rows = await _upbit.fetch_candles(code, unit=unit, count=200)
    return _upbit_normalize(rows)


async def _krx_history(code: str, interval: Interval) -> list[dict]:
    # 주봉/월봉/전체: 일봉 받아서 집계
    if interval in ("1w", "1mo", "all"):
        rows = await _kis.fetch_daily_candles(code, count=100)
        if not rows:
            rows = await _yf_history("KRX", code, "max" if interval == "all" else "5y", "1d")
        if not rows:
            return []
        if interval == "1w":
            return _aggregate(rows, "W")
        if interval == "1mo":
            return _aggregate(rows, "M")
        return rows  # all = 일봉 전체
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
    # 주봉/월봉/전체: 일봉 받아서 집계
    if interval in ("1w", "1mo", "all"):
        rows = await _kis.fetch_overseas_daily_candles(code, market, count=100)
        if not rows:
            rows = await _stooq.fetch_history(code, count=2000)
        if not rows:
            rows = await _yf_history(
                market, code, "max" if interval == "all" else "5y", "1d"
            )
        if not rows:
            return []
        if interval == "1w":
            return _aggregate(rows, "W")
        if interval == "1mo":
            return _aggregate(rows, "M")
        return rows
    # 1d: KIS 해외주식(real 키) → Stooq → yfinance
    if interval == "1d":
        rows = await _kis.fetch_overseas_daily_candles(code, market, count=180)
        if rows:
            return rows
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
