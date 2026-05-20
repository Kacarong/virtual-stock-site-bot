"""차트용 OHLC 히스토리.

- KRX/US: yfinance (yf 티커는 KRX의 경우 005930.KS 형식)
- UPBIT: 공개 API /v1/candles/days?market=KRW-BTC&count=N
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Literal

import httpx
from loguru import logger

Interval = Literal["1d", "1h", "5m"]


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


async def _upbit_history(code: str, count: int = 200) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://api.upbit.com/v1/candles/days",
                params={"market": code, "count": min(count, 200)},
            )
            r.raise_for_status()
            data = r.json()
        out = []
        for row in reversed(data):
            ts = int(datetime.fromisoformat(row["candle_date_time_utc"]).timestamp())
            out.append(
                {
                    "time": ts,
                    "open": float(row["opening_price"]),
                    "high": float(row["high_price"]),
                    "low": float(row["low_price"]),
                    "close": float(row["trade_price"]),
                    "volume": float(row["candle_acc_trade_volume"]),
                }
            )
        return out
    except Exception as e:
        logger.warning("upbit history failed {}: {}", code, e)
        return []


async def get_history(market: str, code: str, interval: Interval = "1d") -> list[dict]:
    market = market.upper()
    if market == "UPBIT":
        return await _upbit_history(code)
    period = {"1d": "6mo", "1h": "1mo", "5m": "5d"}[interval]
    return await _yf_history(market, code, period, interval)
