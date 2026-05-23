"""인기종목 — 시장별 거래량/거래대금/등락률 랭킹.

캐시 정책:
- UPBIT: 10초 (공개 API 무료/속도빠름)
- KRX:   60초 (pykrx는 무겁다)
- US:    60초 (yfinance + 시드 목록)
"""
from __future__ import annotations

import asyncio
import math
import time
from decimal import Decimal
from typing import Literal

from loguru import logger
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Symbol
from .sources import kis as _kis
from .sources import stooq as _stooq
from .sources import upbit
from .sources.kr_seeds import KR_SEEDS
from .sources.us_seeds import US_SEEDS

Sort = Literal["value", "volume", "change", "decline", "market_cap"]
Market = Literal["KRX", "US", "UPBIT"]

_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_TTL = {"UPBIT": 10.0, "KRX": 60.0, "US": 60.0}

# 동시 호출 시 중복 fetch 방지용 in-flight 락 (느린 KRX/US용)
_inflight: dict[str, asyncio.Lock] = {}


def _lock_for(market: str) -> asyncio.Lock:
    lk = _inflight.get(market)
    if lk is None:
        lk = asyncio.Lock()
        _inflight[market] = lk
    return lk


# popular US용 인기 ~120개 (시드 396개 중 시총/거래량 상위)
US_POPULAR_CODES = [
    # 메가캡 테크
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "ORCL",
    "CRM", "AMD", "NFLX", "ADBE", "INTC", "QCOM", "CSCO", "PLTR", "UBER", "SHOP",
    "ABNB", "ASML", "TSM", "SMCI", "ARM", "MU", "AMAT", "LRCX", "KLAC", "MRVL",
    "CRWD", "PANW", "NOW", "INTU", "SNOW", "DDOG", "ZS", "NET", "MDB", "TEAM",
    "DELL", "HPQ", "IBM", "TXN", "ADI", "NXPI", "ON", "MCHP", "WDC", "STX",
    # 금융
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BRK-B", "BLK", "C",
    "COIN", "HOOD", "SQ", "PYPL", "SOFI", "AXP", "SCHW",
    # 소비재/유통
    "WMT", "COST", "HD", "TGT", "LOW", "NKE", "SBUX", "MCD", "DIS", "KO",
    "PEP", "MDLZ", "PG", "CL",
    # 헬스
    "LLY", "UNH", "JNJ", "ABBV", "PFE", "MRK", "TMO", "ABT", "DHR", "CVS",
    "NVO",
    # 에너지/소재
    "XOM", "CVX", "COP", "SLB", "OXY",
    # 통신/미디어
    "T", "VZ", "TMUS", "CMCSA", "WBD", "NFLX",
    # 중국 ADR
    "BABA", "PDD", "JD", "BIDU", "NIO", "XPEV", "LI",
    # 크립토/관련
    "MSTR", "MARA", "RIOT", "CLSK",
    # 밈
    "GME", "AMC", "RDDT", "DJT",
    # 항공/여행
    "DAL", "UAL", "AAL", "CCL", "RCL", "BKNG",
    # ETF (대표)
    "SPY", "QQQ", "VOO", "IWM", "DIA", "IBIT", "FBTC",
    "SOXX", "SMH", "ARKK", "ARKG", "TQQQ", "SQQQ", "SOXL", "SOXS",
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLC", "XLU", "XLB",
    "VTI", "VT", "VEA", "VWO", "BND", "TLT", "GLD", "SLV",
]


def _safe_float(v, default: float = 0.0) -> float:
    """NaN/None/문자 → default. JSON 직렬화 시 NaN이 흘러 클라이언트 깨지는 것 방지."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return f


def _cached(key: tuple[str, str]) -> list[dict] | None:
    hit = _cache.get(key)
    if not hit:
        return None
    ts, data = hit
    market = key[0]
    if time.time() - ts > _TTL.get(market, 30.0):
        return None
    return data


def _store(key: tuple[str, str], data: list[dict]) -> None:
    _cache[key] = (time.time(), data)


# ------------------------------------------------------------------ UPBIT

async def popular_upbit(sort: Sort, limit: int = 30) -> list[dict]:
    key = ("UPBIT", sort)
    if (c := _cached(key)) is not None:
        return c[:limit]

    # 마켓 목록
    db = SessionLocal()
    try:
        codes = [s.code for s in db.query(Symbol).filter(Symbol.market == "UPBIT", Symbol.is_active).all()]
        name_by = {s.code: s.name for s in db.query(Symbol).filter(Symbol.market == "UPBIT").all()}
    finally:
        db.close()

    if not codes:
        # 시드라도 없으면 hardcode
        codes = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-DOGE"]
        name_by = {c: c for c in codes}

    rows = await upbit.fetch_tickers_full(codes)
    out = []
    for r in rows:
        price = float(r.get("trade_price", 0))
        prev = float(r.get("prev_closing_price", 0)) or price
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        out.append(
            {
                "market": "UPBIT",
                "code": r["market"],
                "name": name_by.get(r["market"], r["market"]),
                "price": price,
                "change_pct": change_pct,
                "volume": float(r.get("acc_trade_volume_24h", 0)),
                "value": float(r.get("acc_trade_price_24h", 0)),
                "market_cap": None,  # 코인은 시총 미지원
            }
        )
    # 한 번 fetch한 데이터로 모든 sort 변형 채우기
    for s in ("value", "volume", "change", "decline"):
        _store(("UPBIT", s), _sort_rows(list(out), s))  # type: ignore
    return _sort_rows(out, sort)[:limit]


# ------------------------------------------------------------------ KRX

async def popular_krx(sort: Sort, limit: int = 30) -> list[dict]:
    key = ("KRX", sort)
    if (c := _cached(key)) is not None:
        return c[:limit]

    lock = _lock_for("KRX")
    if lock.locked():
        # 다른 sort 캐시(stale 포함)로 즉시 응답 — 무한 로딩 방지
        for s in ("value", "volume", "change", "decline", "market_cap"):
            stale = _cache.get(("KRX", s))
            if stale:
                return _sort_rows(list(stale[1]), sort)[:limit]
        return []

    async with lock:
        if (c := _cached(("KRX", sort))) is not None:
            return c[:limit]

        def _fetch() -> list[dict]:
            try:
                from datetime import datetime, timedelta

                import pandas as _pd  # type: ignore
                from pykrx import stock  # type: ignore

                today = datetime.now()
                df = None
                used_date = None
                for d in range(0, 14):
                    cand_dt = today - timedelta(days=d)
                    # 주말 스킵 (pykrx는 평일만 데이터 있음)
                    if cand_dt.weekday() >= 5:
                        continue
                    date = cand_dt.strftime("%Y%m%d")
                    try:
                        cand = stock.get_market_ohlcv_by_ticker(date=date, market="ALL")
                        if cand is None or len(cand) == 0:
                            continue
                        # ★ 핵심 휴리스틱: 삼성전자(005930)의 종가/거래대금이 비정상이면
                        # pykrx가 partial 데이터를 흘리는 케이스 → 해당 날짜 버리고 이전 영업일 시도
                        try:
                            samsung = cand.loc["005930"]
                            price_col = "종가" if "종가" in cand.columns else cand.columns[3]
                            val_col = "거래대금" if "거래대금" in cand.columns else None
                            bad_price = _pd.isna(samsung[price_col]) or float(samsung[price_col]) <= 0
                            bad_value = False
                            if val_col is not None:
                                bad_value = _pd.isna(samsung[val_col]) or float(samsung[val_col]) <= 0
                            if bad_price or bad_value:
                                logger.info(
                                    "KRX popular: pykrx {} samsung bad (price_bad={}, value_bad={}), skip",
                                    date, bad_price, bad_value,
                                )
                                continue
                        except KeyError:
                            # 삼성 없으면 휴장일 or partial → skip
                            logger.info("KRX popular: pykrx {} no samsung row, skip", date)
                            continue
                        except Exception:
                            pass
                        df = cand
                        used_date = date
                        logger.info("KRX popular: pykrx date={} rows={}", date, len(df))
                        break
                    except Exception as e:
                        logger.debug("pykrx ohlcv try {} fail: {}", date, e)
                        continue
                if df is None or len(df) == 0:
                    logger.warning("KRX popular: pykrx returned empty (tried 10 days)")
                    return []
                df = df.reset_index().rename(
                    columns={
                        "티커": "code",
                        "종가": "price",
                        "거래량": "volume",
                        "거래대금": "value",
                        "등락률": "change_pct",
                    }
                )
                # 시가총액 (같은 date로) — 실패해도 OHLCV는 살림
                cap_map: dict[str, float] = {}
                try:
                    cap_df = stock.get_market_cap_by_ticker(date=used_date, market="ALL")
                    if cap_df is not None and len(cap_df) > 0:
                        cap_df = cap_df.reset_index().rename(
                            columns={"티커": "code", "시가총액": "market_cap"}
                        )
                        for _r in cap_df[["code", "market_cap"]].to_dict("records"):
                            try:
                                cap_map[str(_r["code"])] = float(_r["market_cap"])
                            except Exception:
                                continue
                        logger.info("KRX popular: market_cap rows={}", len(cap_map))
                except Exception as e:
                    logger.debug("pykrx market_cap fail: {}", e)
                rows = df[["code", "price", "volume", "value", "change_pct"]].to_dict("records")
                for r in rows:
                    r["market_cap"] = cap_map.get(str(r["code"]))
                return rows
            except Exception as e:
                logger.warning("KRX popular fetch failed: {}", e)
                return []

        try:
            rows = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=25.0)
        except asyncio.TimeoutError:
            logger.warning("KRX popular fetch timeout")
            rows = []

        # pykrx 실패 시: KIS → Stooq → yfinance 순으로 시드 quote 채움
        if not rows:
            logger.info("KRX popular fallback: using seeds + KIS quote")
            seed_codes = [c for c, _, asset_type, _ in KR_SEEDS if asset_type == "STOCK"]
            quotes = await _kis.fetch_prices(seed_codes)

            # KIS 미설정/실패 시 Stooq KR 폴백 (가장 빠름)
            missing = [c for c in seed_codes if not quotes.get(c)]
            if missing:
                logger.info("KRX popular: stooq KR fallback for {} codes", len(missing))
                try:
                    stooq_quotes = await asyncio.wait_for(
                        _stooq.fetch_quotes_kr(missing), timeout=15.0
                    )
                    quotes.update(stooq_quotes)
                    logger.info("KRX popular: stooq returned {} quotes", len(stooq_quotes))
                except asyncio.TimeoutError:
                    logger.warning("KRX stooq fallback timeout")

            # 그래도 누락된 종목은 yfinance 폴백 (.KS 접미)
            missing = [c for c in seed_codes if not quotes.get(c)]
            if missing:
                logger.info("KRX popular: yfinance fallback for {} codes", len(missing))

                def _yf_kr(targets: list[str]) -> dict[str, dict]:
                    try:
                        import concurrent.futures
                        import yfinance as yf  # type: ignore

                        def one(c: str):
                            try:
                                t = yf.Ticker(f"{c}.KS")
                                hist = t.history(period="5d", auto_adjust=False)
                                if hist.empty:
                                    return c, None
                                last = hist.iloc[-1]
                                prev = hist.iloc[-2] if len(hist) >= 2 else last
                                price = float(last["Close"])
                                pclose = float(prev["Close"]) or price
                                vol = float(last["Volume"])
                                return c, {
                                    "price": price,
                                    "prev_close": pclose,
                                    "volume": vol,
                                    "value": price * vol,
                                }
                            except Exception:
                                return c, None

                        out: dict[str, dict] = {}
                        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
                            for c, q in ex.map(one, targets, timeout=25):
                                if q:
                                    out[c] = q
                        return out
                    except Exception as e:
                        logger.warning("KRX yf fallback failed: {}", e)
                        return {}

                try:
                    yf_quotes = await asyncio.wait_for(
                        asyncio.to_thread(_yf_kr, missing), timeout=28.0
                    )
                    quotes.update(yf_quotes)
                except asyncio.TimeoutError:
                    logger.warning("KRX yf fallback timeout")

            rows = []
            for code in seed_codes:
                q = quotes.get(code)
                if not q:
                    continue
                price = float(q["price"])
                prev = float(q.get("prev_close") or price) or price
                volume = float(q.get("volume") or 0)
                value = float(q.get("value") or 0) or price * volume
                change_pct = ((price - prev) / prev * 100) if prev else 0.0
                rows.append(
                    {
                        "code": code,
                        "price": price,
                        "volume": volume,
                        "value": value,
                        "change_pct": change_pct,
                    }
                )

    # 이름 붙이기 (Symbol DB 우선, 없으면 KR_SEEDS, 마지막엔 code 그대로)
    db = SessionLocal()
    try:
        name_by = {s.code: s.name for s in db.query(Symbol).filter(Symbol.market == "KRX").all()}
    finally:
        db.close()
    seed_name = {code: name for code, name, _, _ in KR_SEEDS}

    out = []
    for r in rows:
        code = str(r["code"])
        name = name_by.get(code) or seed_name.get(code)
        if not name:
            continue
        price = _safe_float(r.get("price"))
        if price <= 0:
            continue  # pykrx가 정지/상폐 종목에 0/NaN 흘리는 케이스 제외
        # 매핑용으로 임시 추가 (다음 줄에서 사용)
        name_by[code] = name
        market_cap = r.get("market_cap")
        if market_cap is not None:
            mc = _safe_float(market_cap)
            market_cap = mc if mc > 0 else None
        out.append(
            {
                "market": "KRX",
                "code": code,
                "name": name_by[code],
                "price": price,
                "change_pct": _safe_float(r.get("change_pct")),
                "volume": _safe_float(r.get("volume")),
                "value": _safe_float(r.get("value")),
                "market_cap": market_cap,
            }
        )

    # 한 번 fetch한 데이터로 모든 sort 변형 캐시에 채워 토글 빠르게
    for s in ("value", "volume", "change", "decline", "market_cap"):
        _store(("KRX", s), _sort_rows(list(out), s))  # type: ignore

    return _sort_rows(out, sort)[:limit]


# ------------------------------------------------------------------ US

def _sort_rows(rows: list[dict], sort: Sort) -> list[dict]:
    # secondary key=code 로 안정 정렬 (값 동률 시 같은 순서 유지 → 화면 튐 방지)
    if sort == "value":
        rows.sort(key=lambda x: (-(x.get("value") or 0), x.get("code", "")))
    elif sort == "volume":
        rows.sort(key=lambda x: (-(x.get("volume") or 0), x.get("code", "")))
    elif sort == "change":
        rows.sort(key=lambda x: (-(x.get("change_pct") or 0), x.get("code", "")))
    elif sort == "decline":
        rows.sort(key=lambda x: ((x.get("change_pct") or 0), x.get("code", "")))
    elif sort == "market_cap":
        # 시총 없는 행(None)은 맨 뒤로 — 0/None을 -1로 두면 사전순으로 깨짐 방지
        def _cap_key(x):
            mc = x.get("market_cap")
            has = mc is not None and mc > 0
            return (0 if has else 1, -(mc or 0), x.get("code", ""))
        rows.sort(key=_cap_key)
    return rows


async def popular_us(sort: Sort, limit: int = 30) -> list[dict]:
    # 캐시 적중 시 즉시 반환
    for s in ("value", "volume", "change"):
        if (c := _cached(("US", s))) is not None and s == sort:
            return c[:limit]

    lock = _lock_for("US")
    # 락이 잠겨 있으면 기존 캐시(만료라도) 반환 — 무한 로딩 방지
    if lock.locked():
        for s in ("value", "volume", "change"):
            stale = _cache.get(("US", s))
            if stale:
                return _sort_rows(list(stale[1]), sort)[:limit]
        return []

    async with lock:
        # 락 진입 후 한 번 더 확인 (다른 호출이 방금 채웠을 수 있음)
        if (c := _cached(("US", sort))) is not None:
            return c[:limit]

        codes = US_POPULAR_CODES
        name_by = {c: n for c, n, _, _ in US_SEEDS}
        market_by = {c: m for c, _, m, _ in US_SEEDS}

        by_code: dict[str, dict] = {}

        def _add(code: str, price: float, prev: float, volume: float, value: float | None = None, market_cap: float | None = None):
            if price <= 0:
                return
            change_pct = ((price - prev) / prev * 100) if prev else 0.0
            by_code[code] = {
                "market": market_by.get(code, "NASDAQ"),
                "code": code,
                "name": name_by.get(code, code),
                "price": price,
                "change_pct": change_pct,
                "volume": volume,
                "value": value if value is not None else price * volume,
                "market_cap": market_cap,
            }

        # 0순위: KIS 해외주식 (real 키 + 해외 권한 필요)
        if _kis._configured():
            try:
                kis_quotes = await asyncio.wait_for(
                    _kis.fetch_overseas_prices(
                        [(c, market_by.get(c, "NASDAQ")) for c in codes]
                    ),
                    timeout=25.0,
                )
            except asyncio.TimeoutError:
                logger.warning("US popular: KIS overseas timeout")
                kis_quotes = {}
            for code, q in kis_quotes.items():
                if not q:
                    continue
                price = float(q["price"])
                prev = float(q.get("prev_close") or price) or price
                volume = float(q.get("volume") or 0)
                value = float(q.get("value") or 0) or price * volume
                _add(code, price, prev, volume, value)

        # 1순위: Stooq — KIS에서 못 받은 코드 보충
        missing = [c for c in codes if c not in by_code]
        if missing:
            quotes = await _stooq.fetch_quotes(missing)
            for code, q in quotes.items():
                if not q:
                    continue
                price = float(q["price"])
                prev = float(q.get("prev_close") or price) or price
                volume = float(q.get("volume") or 0)
                _add(code, price, prev, volume)

        # 2순위: yfinance — 여전히 누락된 코드만 채움
        missing = [c for c in codes if c not in by_code]
        if missing:
            logger.info("US popular: yfinance fallback for {} missing", len(missing))

            def _yf_fetch(targets: list[str]) -> list[dict]:
                try:
                    import concurrent.futures

                    import yfinance as yf  # type: ignore

                    def one(code: str) -> dict | None:
                        try:
                            t = yf.Ticker(code)
                            hist = t.history(period="5d", auto_adjust=False)
                            if hist.empty:
                                return None
                            last = hist.iloc[-1]
                            prev = hist.iloc[-2] if len(hist) >= 2 else last
                            price = float(last["Close"])
                            prev_close = float(prev["Close"]) or price
                            volume = float(last["Volume"])
                            return {
                                "code": code,
                                "price": price,
                                "prev_close": prev_close,
                                "volume": volume,
                            }
                        except Exception:
                            return None

                    res: list[dict] = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
                        for r in ex.map(one, targets, timeout=25):
                            if r:
                                res.append(r)
                    return res
                except Exception as e:
                    logger.warning("yfinance fallback failed: {}", e)
                    return []

            try:
                yf_rows = await asyncio.wait_for(
                    asyncio.to_thread(_yf_fetch, missing), timeout=28.0
                )
            except asyncio.TimeoutError:
                logger.warning("yfinance fallback timeout")
                yf_rows = []
            for r in yf_rows:
                _add(r["code"], r["price"], r["prev_close"], r["volume"])

        out = list(by_code.values())

        # 시가총액 enrich: 코드별 shares_outstanding 캐시 (1시간) → market_cap = price × shares
        if out:
            await _enrich_us_market_cap(out)

        # 모든 소스 실패 시: 가격 0인 placeholder는 표시하지 않음
        if not out:
            logger.warning("US popular all-failed, returning empty")

        _store(("US", sort), _sort_rows(list(out), sort))
        for s in ("value", "volume", "change", "decline", "market_cap"):
            if s != sort:
                _store(("US", s), _sort_rows(list(out), s))  # type: ignore
        return _sort_rows(out, sort)[:limit]


# US 시총용 shares outstanding 캐시 (1시간 TTL)
_us_shares_cache: dict[str, tuple[float, float]] = {}  # code → (ts, shares)
_US_SHARES_TTL = 3600.0


async def _enrich_us_market_cap(rows: list[dict]) -> None:
    """rows에 market_cap 채워 넣기. shares_outstanding 1시간 캐시."""
    now = time.time()
    targets = [
        r["code"] for r in rows
        if r["code"] not in _us_shares_cache
        or now - _us_shares_cache[r["code"]][0] > _US_SHARES_TTL
    ]

    if targets:
        def _fetch_shares(codes: list[str]) -> dict[str, float]:
            try:
                import concurrent.futures
                import yfinance as yf  # type: ignore

                def one(c: str) -> tuple[str, float | None]:
                    try:
                        t = yf.Ticker(c)
                        s = float(t.fast_info.shares or 0)
                        return c, s if s > 0 else None
                    except Exception:
                        return c, None

                res: dict[str, float] = {}
                with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
                    for c, s in ex.map(one, codes, timeout=20):
                        if s:
                            res[c] = s
                return res
            except Exception as e:
                logger.warning("US shares fetch failed: {}", e)
                return {}

        try:
            new_shares = await asyncio.wait_for(
                asyncio.to_thread(_fetch_shares, targets), timeout=22.0
            )
            for c, s in new_shares.items():
                _us_shares_cache[c] = (now, s)
        except asyncio.TimeoutError:
            logger.warning("US shares fetch timeout")

    for r in rows:
        entry = _us_shares_cache.get(r["code"])
        if entry and r.get("price"):
            r["market_cap"] = float(entry[1]) * float(r["price"])
        else:
            r.setdefault("market_cap", None)


# ------------------------------------------------------------------ dispatcher

async def popular(market: Market, sort: Sort = "value", limit: int = 30) -> list[dict]:
    if market == "UPBIT":
        return await popular_upbit(sort, limit)
    if market == "KRX":
        return await popular_krx(sort, limit)
    if market == "US":
        return await popular_us(sort, limit)
    return []
