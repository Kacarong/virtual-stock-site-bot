"""yfinance — 미국 주식/ETF.

yfinance는 동기 함수라 스레드풀에서 실행. 호출 빈도는 1초당 5~10회 정도면 안전.

NOTE: 과거에 t.fast_info.last_price 를 1차로 썼는데, yfinance 내부에서
share count fetch가 깨지면(예: 일부 ETF/지수) fast_info 전체가 None을 뱉어
가격을 못 받음. 따라서 history(period='5d')를 1차 경로로 쓰고, fast_info는
이미 캐시된 경우에만 쇼트컷으로 사용.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from loguru import logger


def _extract_from_history(hist) -> tuple[float | None, float | None]:
    """history DataFrame → (last_close, prev_close)."""
    try:
        if hist is None or hist.empty:
            return None, None
        closes = hist["Close"].dropna()
        if len(closes) == 0:
            return None, None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev
    except Exception:
        return None, None


def _try_fast_info(t) -> tuple[float | None, float | None]:
    """fast_info 쇼트컷. 실패해도 무시."""
    try:
        fi = t.fast_info
        last = getattr(fi, "last_price", None)
        prev = getattr(fi, "previous_close", None)
        return (
            float(last) if last is not None else None,
            float(prev) if prev is not None else None,
        )
    except Exception:
        return None, None


async def fetch_quote(ticker: str) -> dict | None:
    """단일 티커. 실패시 None."""
    def _fetch() -> dict | None:
        try:
            import yfinance as yf  # type: ignore

            t = yf.Ticker(ticker)
            # 1차: fast_info 쇼트컷 (성공하면 1콜로 끝남)
            last, prev = _try_fast_info(t)
            # 2차: history (fast_info가 깨졌어도 안정적)
            if last is None:
                hist = t.history(period="5d", interval="1d")
                last, prev2 = _extract_from_history(hist)
                if prev is None:
                    prev = prev2
            if last is None:
                return None
            return {
                "price": Decimal(str(last)),
                "prev_close": Decimal(str(prev)) if prev is not None else None,
            }
        except Exception as e:
            logger.debug("yfinance fetch failed for {}: {}", ticker, e)
            return None

    return await asyncio.to_thread(_fetch)


async def fetch_quotes(tickers: list[str]) -> dict[str, dict]:
    """다수 티커. yf.download 한 번 호출로 모든 종가 일괄 수신."""
    if not tickers:
        return {}

    def _fetch() -> dict[str, dict]:
        try:
            import yfinance as yf  # type: ignore

            out: dict[str, dict] = {}
            # 한 번 호출로 모든 티커 5일치 일봉 받음
            try:
                df = yf.download(
                    " ".join(tickers),
                    period="5d",
                    interval="1d",
                    group_by="ticker",
                    progress=False,
                    threads=True,
                    auto_adjust=False,
                )
            except Exception as e:
                logger.warning("yfinance bulk download failed: {}", e)
                df = None

            if df is not None and not df.empty:
                # 단일 종목이면 multiindex가 아닐 수 있음
                multi = (
                    hasattr(df.columns, "levels")
                    and len(df.columns.levels) > 1
                )
                for sym in tickers:
                    try:
                        sub = df[sym] if multi and sym in df.columns.get_level_values(0) else df
                        last, prev = _extract_from_history(sub)
                        if last is None:
                            continue
                        out[sym] = {
                            "price": Decimal(str(last)),
                            "prev_close": Decimal(str(prev)) if prev is not None else None,
                        }
                    except Exception as e:
                        logger.debug("yf bulk {} parse skip: {}", sym, e)

            # 일괄 호출에서 빠진 티커는 개별 history로 한 번 더 시도
            missing = [s for s in tickers if s not in out]
            for sym in missing:
                try:
                    t = yf.Ticker(sym)
                    last, prev = _try_fast_info(t)
                    if last is None:
                        hist = t.history(period="5d", interval="1d")
                        last, prev2 = _extract_from_history(hist)
                        if prev is None:
                            prev = prev2
                    if last is None:
                        continue
                    out[sym] = {
                        "price": Decimal(str(last)),
                        "prev_close": Decimal(str(prev)) if prev is not None else None,
                    }
                except Exception as e:
                    logger.debug("yf {} individual skip: {}", sym, e)

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
