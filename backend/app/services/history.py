"""차트용 OHLC 히스토리.

소스 우선순위 (NAS에서 yfinance 자주 죽음):
- UPBIT: 공개 API /v1/candles/...                  (모든 interval 지원)
- KRX:   KIS API (일/분봉) → yfinance fallback
- US:    yfinance (1m/1h 가능) → Stooq (1d만)

지원 interval: 1m / 5m / 1h / 1d / 1w / 1mo / all

캐시: stale-while-revalidate (인터벌별 TTL).
"""
from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime
from typing import Literal

from loguru import logger

from .sources import kis as _kis
from .sources import stooq as _stooq
from .sources import toss as _toss
from .sources import upbit as _upbit

Interval = Literal["1m", "5m", "1h", "1d", "1w", "1mo", "all"]

# 캐시 fresh TTL (초): 인터벌별로 다름
_FRESH_TTL: dict[str, float] = {
    "1m": 30.0,
    "5m": 60.0,
    "1h": 300.0,
    "1d": 900.0,
    "1w": 3600.0,
    "1mo": 3600.0,
    "all": 3600.0,
}
# stale 한계 — 이 시간까지는 백그라운드 갱신하면서 즉시 반환
_STALE_TTL = 24 * 3600.0

# (market, code, interval) → (ts, rows)
_hist_cache: dict[tuple[str, str, str], tuple[float, list[dict]]] = {}
_hist_inflight: dict[tuple[str, str, str], asyncio.Task] = {}


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


async def _race(*coros) -> list[dict]:
    """여러 소스를 동시에 호출 → 가장 먼저 유효한 결과(빈 리스트 아닌)를 반환.

    실패/빈 결과는 무시하고 다음을 기다림. 모두 실패하면 [].
    중간에 결과가 오면 나머지는 취소.
    """
    tasks = [asyncio.ensure_future(c) for c in coros]
    try:
        while tasks:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for d in done:
                tasks.remove(d)
                try:
                    rows = d.result()
                except Exception:
                    rows = []
                if rows:
                    # 나머지 취소
                    for p in tasks:
                        p.cancel()
                    return rows
        return []
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


async def _krx_history(code: str, interval: Interval) -> list[dict]:
    # 주봉/월봉/전체: 일봉 받아서 집계
    if interval in ("1w", "1mo", "all"):
        rows = await _race(
            _kis.fetch_daily_candles(code, count=100),
            _yf_history("KRX", code, "max" if interval == "all" else "5y", "1d"),
        )
        if not rows:
            return []
        if interval == "1w":
            return _aggregate(rows, "W")
        if interval == "1mo":
            return _aggregate(rows, "M")
        return rows  # all = 일봉 전체
    # 일/분: KIS와 yfinance 동시 호출 → 먼저 도착하는 거 사용
    if interval == "1d":
        return await _race(
            _toss.fetch_candles(code, "1d", count=180),
            _kis.fetch_daily_candles(code, count=180),
            _yf_history("KRX", code, "6mo", "1d"),
        )
    if interval == "1m":
        return await _race(
            _toss.fetch_candles(code, "1m", count=200),
            _kis.fetch_minute_candles(code, count=200),
            _yf_history("KRX", code, "5d", "1m"),
        )
    period_map = {"5m": "5d", "1h": "1mo"}
    yf_interval = {"5m": "5m", "1h": "60m"}[interval]
    return await _yf_history("KRX", code, period_map[interval], yf_interval)


async def _us_history(market: str, code: str, interval: Interval) -> list[dict]:
    # 주봉/월봉/전체: 일봉 받아서 집계
    if interval in ("1w", "1mo", "all"):
        rows = await _race(
            _kis.fetch_overseas_daily_candles(code, market, count=100),
            _stooq.fetch_history(code, count=2000),
            _yf_history(market, code, "max" if interval == "all" else "5y", "1d"),
        )
        if not rows:
            return []
        if interval == "1w":
            return _aggregate(rows, "W")
        if interval == "1mo":
            return _aggregate(rows, "M")
        return rows
    # 1d: Toss + 기존 3개 소스 race
    if interval == "1d":
        return await _race(
            _toss.fetch_candles(code, "1d", count=180),
            _kis.fetch_overseas_daily_candles(code, market, count=180),
            _stooq.fetch_history(code, count=180),
            _yf_history(market, code, "6mo", "1d"),
        )
    if interval == "1m":
        return await _race(
            _toss.fetch_candles(code, "1m", count=200),
            _yf_history(market, code, "5d", "1m"),
        )
    period_map = {"1m": "5d", "5m": "5d", "1h": "1mo"}
    yf_interval = {"1m": "1m", "5m": "5m", "1h": "60m"}[interval]
    return await _yf_history(market, code, period_map[interval], yf_interval)


def _clean_rows(rows: list[dict]) -> list[dict]:
    """NaN/None OHLC 또는 time 누락된 캔들 제거 + 시간 오름차순."""
    def _ok(v) -> bool:
        if v is None:
            return False
        try:
            f = float(v)
        except Exception:
            return False
        return math.isfinite(f)

    out = []
    for r in rows:
        if not _ok(r.get("time")):
            continue
        if not (_ok(r.get("open")) and _ok(r.get("high")) and _ok(r.get("low")) and _ok(r.get("close"))):
            continue
        out.append(r)
    out.sort(key=lambda x: x["time"])
    # 시간 중복 제거 (마지막 값 채택)
    dedup: dict[int, dict] = {}
    for r in out:
        dedup[int(r["time"])] = r
    return list(dedup.values())


async def _fetch_history_uncached(
    market: str, code: str, interval: Interval
) -> list[dict]:
    if market == "UPBIT":
        rows = await _upbit_history(code, interval)
    elif market == "KRX":
        rows = await _krx_history(code, interval)
    elif market in ("NASDAQ", "NYSE"):
        rows = await _us_history(market, code, interval)
    else:
        rows = []
    return _clean_rows(rows)


def _spawn_hist_refresh(market: str, code: str, interval: Interval) -> None:
    key = (market, code, interval)
    t = _hist_inflight.get(key)
    if t and not t.done():
        return

    async def _runner():
        try:
            rows = await _fetch_history_uncached(market, code, interval)
            if rows:
                _hist_cache[key] = (time.time(), rows)
        except Exception as e:
            logger.warning("history refresh failed {} {} {}: {}", market, code, interval, e)
        finally:
            _hist_inflight.pop(key, None)

    try:
        _hist_inflight[key] = asyncio.create_task(_runner())
    except RuntimeError:
        pass


async def get_history(
    market: str, code: str, interval: Interval = "1d", *, max_wait: float = 2.5
) -> list[dict]:
    """차트 히스토리 — stale-while-revalidate 캐시.

    - fresh → 즉시 반환
    - stale → 즉시 반환 + 백그라운드 갱신
    - 없음  → 외부 호출 (max_wait 타임아웃)
    """
    market = market.upper()
    key = (market, code, interval)
    now = time.time()
    cached = _hist_cache.get(key)
    fresh_ttl = _FRESH_TTL.get(interval, 300.0)

    if cached and now - cached[0] < fresh_ttl:
        return cached[1]

    if cached and now - cached[0] < _STALE_TTL:
        _spawn_hist_refresh(market, code, interval)
        return cached[1]

    # 캐시 없음 → 외부 호출
    try:
        rows = await asyncio.wait_for(
            _fetch_history_uncached(market, code, interval), timeout=max_wait
        )
    except asyncio.TimeoutError:
        _spawn_hist_refresh(market, code, interval)
        return cached[1] if cached else []

    if rows:
        _hist_cache[key] = (now, rows)
    return rows or (cached[1] if cached else [])
