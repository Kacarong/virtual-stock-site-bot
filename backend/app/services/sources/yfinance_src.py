"""yfinance — 미국 주식/ETF.

yfinance는 동기 함수라 스레드풀에서 실행. 호출 빈도는 1초당 5~10회 정도면 안전.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from loguru import logger


async def fetch_quote(ticker: str) -> dict | None:
    """단일 티커. 실패시 None."""
    def _fetch() -> dict | None:
        try:
            import yfinance as yf  # type: ignore

            t = yf.Ticker(ticker)
            # 빠른 핫 패스: fast_info에 lastPrice / previousClose가 있음
            fi = t.fast_info
            last = getattr(fi, "last_price", None) or fi.get("lastPrice") if hasattr(fi, "get") else None
            prev = getattr(fi, "previous_close", None) or fi.get("previousClose") if hasattr(fi, "get") else None
            if last is None:
                # fallback: history
                hist = t.history(period="1d", interval="1m")
                if hist.empty:
                    return None
                last = float(hist["Close"].iloc[-1])
                prev = float(hist["Open"].iloc[0])
            return {
                "price": Decimal(str(last)),
                "prev_close": Decimal(str(prev)) if prev is not None else None,
            }
        except Exception as e:
            logger.debug("yfinance fetch failed for {}: {}", ticker, e)
            return None

    return await asyncio.to_thread(_fetch)


async def fetch_quotes(tickers: list[str]) -> dict[str, dict]:
    """다수 티커. 내부적으로 yf.Tickers 한 번에 호출."""
    if not tickers:
        return {}

    def _fetch() -> dict[str, dict]:
        try:
            import yfinance as yf  # type: ignore

            ts = yf.Tickers(" ".join(tickers))
            out: dict[str, dict] = {}
            for sym in tickers:
                try:
                    t = ts.tickers[sym]
                    fi = t.fast_info
                    last = getattr(fi, "last_price", None)
                    prev = getattr(fi, "previous_close", None)
                    if last is None:
                        continue
                    out[sym] = {
                        "price": Decimal(str(last)),
                        "prev_close": Decimal(str(prev)) if prev else None,
                    }
                except Exception as e:
                    logger.debug("yf {} skipped: {}", sym, e)
            return out
        except Exception as e:
            logger.warning("yfinance bulk fetch failed: {}", e)
            return {}

    return await asyncio.to_thread(_fetch)


async def fetch_usdkrw() -> Decimal | None:
    """원/달러 환율 (USDKRW=X)."""
    q = await fetch_quote("USDKRW=X")
    return q["price"] if q else None


async def fetch_symbol_master_us() -> list[dict]:
    """미국 종목 마스터.

    yfinance에는 '전종목 리스트'가 없음. 실무적으로:
    - SP500/Nasdaq 100 등 인덱스 컴포넌트
    - 사용자가 검색/요청한 종목을 on-demand로 추가
    Stage 2에서는 빈 리스트 반환 → 검색 시 on-demand로 등록 (Stage 4에서 구현).
    """
    return []
