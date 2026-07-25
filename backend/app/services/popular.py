"""인기종목 — 시장별 거래량/거래대금/등락률 랭킹.

캐시 정책:
- UPBIT: 10초 (공개 API 무료/속도빠름)
- KRX:   60초 (pykrx는 무겁다)
- US:    60초 (yfinance + 시드 목록)
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from loguru import logger
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Price, Symbol
from .krx_marketcap_fallback import KRX_MARKET_CAP_FALLBACK
from .sources import kis as _kis
from .sources import stooq as _stooq
from .sources import toss as _toss
from .sources import upbit
from .sources.kr_seeds import KR_SEEDS
from .sources.us_seeds import US_SEEDS

Sort = Literal[
    "value", "volume", "change", "decline", "market_cap", "toss_value", "toss_volume"
]
Market = Literal["KRX", "US", "UPBIT"]

_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_TTL = {"UPBIT": 10.0, "KRX": 60.0, "US": 60.0}

# 동시 호출 시 중복 fetch 방지용 in-flight 락 (느린 KRX/US용)
_inflight: dict[str, asyncio.Lock] = {}

# 백그라운드 갱신 task 추적 (이미 도는 중이면 새로 띄우지 않음)
_bg_refresh: dict[str, asyncio.Task] = {}


def _lock_for(market: str) -> asyncio.Lock:
    lk = _inflight.get(market)
    if lk is None:
        lk = asyncio.Lock()
        _inflight[market] = lk
    return lk


def _spawn_bg_refresh(market: str) -> None:
    """백그라운드 popular fetch를 띄움 (이미 도는 중이면 무시).

    화면이 stale/DB 폴백으로 즉시 뜨는 동안 진짜 데이터를 가져와 캐시 채움.
    _force_full=True로 호출하여 폴백 단축경로를 건너뛰고 실제 fetch 수행.
    """
    existing = _bg_refresh.get(market)
    if existing and not existing.done():
        return

    async def _go() -> None:
        try:
            if market == "KRX":
                await popular_krx("value", 30, _force_full=True)
            elif market == "US":
                await popular_us("value", 30, _force_full=True)
            elif market == "UPBIT":
                await popular_upbit("value", 30)
        except Exception as e:
            logger.debug("bg refresh {} failed: {}", market, e)
        finally:
            _bg_refresh.pop(market, None)

    try:
        loop = asyncio.get_running_loop()
        _bg_refresh[market] = loop.create_task(_go())
    except RuntimeError:
        pass


def _immediate_fallback(market: str, sort: Sort, limit: int) -> list[dict] | None:
    """즉시 응답 가능한 정확한 데이터 찾기 — 메모리 캐시(디스크 백업 포함)만.

    DB Price 폴백은 거래대금/거래량이 0이라 정렬 순서가 엉뚱하게 나옴
    (가나다 순) → 사용자가 잘못된 1위로 오인. 부정확할 바엔 차라리 빈 응답.
    """
    sort_keys = ("value", "volume", "change", "decline", "market_cap")
    # 1) 정확한 sort 캐시 (만료라도) — 이 sort에 맞춰 저장됐던 정확한 순서
    if (entry := _cache.get((market, sort))):
        return _sort_rows(list(entry[1]), sort)[:limit]
    # 토스증권 기준(toss_*)은 시장 기준 캐시로 대체하지 않는다.
    # (대체하면 시장 데이터가 토스 데이터로 오인됨 — 목록이 안 바뀌는 것처럼 보임)
    if sort in ("toss_value", "toss_volume"):
        return None
    # 2) 다른 sort 캐시 (만료 포함) — 같은 row 데이터, 단지 정렬키만 바꿔 재정렬
    #    원본 row에 정확한 volume/value/market_cap이 포함돼 있어 정확한 순서 보장
    for s in sort_keys:
        if (entry := _cache.get((market, s))):
            return _sort_rows(list(entry[1]), sort)[:limit]
    return None


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


# ------------------------------------------------------------------ 디스크 백업
# 메모리 _cache 를 그대로 JSON으로 dump해서 디스크에 보관.
# 컨테이너 재시작 후에도 마지막 정확한 데이터(거래대금/순서 포함)로
# 즉시 응답 가능 → "이상한 데이터 보였다가 수정" 현상 제거.

_DISK_CACHE_PATH = Path("/data/popular_cache.json")
_last_disk_save = 0.0
_DISK_SAVE_THROTTLE = 5.0  # 5초에 한 번만 disk write


def _store(key: tuple[str, str], data: list[dict]) -> None:
    _cache[key] = (time.time(), data)


def _persist_cache_to_disk() -> None:
    """현재 _cache 전체를 JSON으로 디스크에 저장 (throttled)."""
    global _last_disk_save
    now = time.time()
    if now - _last_disk_save < _DISK_SAVE_THROTTLE:
        return
    _last_disk_save = now
    try:
        _DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            f"{m}|{s}": [ts, data] for (m, s), (ts, data) in _cache.items()
        }
        tmp = _DISK_CACHE_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(serializable, f)
        tmp.replace(_DISK_CACHE_PATH)
    except Exception as e:
        logger.debug("popular cache save fail: {}", e)


def load_disk_cache() -> None:
    """startup 시 호출 — 디스크에서 _cache 복원.

    캐시가 만료(TTL) 됐어도 일단 _cache에 넣어두면, immediate_fallback
    경로가 stale로 즉시 응답할 수 있다.
    """
    try:
        if not _DISK_CACHE_PATH.exists():
            return
        with open(_DISK_CACHE_PATH, encoding="utf-8") as f:
            loaded = json.load(f)
        n = 0
        for k, v in loaded.items():
            if "|" not in k:
                continue
            m, s = k.split("|", 1)
            ts, data = v
            _cache[(m, s)] = (float(ts), data)
            n += 1
        logger.info("popular disk cache loaded: {} keys", n)
    except Exception as e:
        logger.warning("popular cache load fail: {}", e)


def _persist_prices(market: str, rows: list[dict]) -> None:
    """popular fetch 성공 데이터를 Price 테이블에 upsert.

    이렇게 해두면 다음 호출에서 외부 소스가 실패해도 DB 폴백으로
    "데이터 없음"이 뜨지 않는다. 코인은 너무 자주라 패스 (외부 API가 안정적).
    """
    if not rows or market == "UPBIT":
        return
    try:
        db = SessionLocal()
        try:
            codes = [r["code"] for r in rows]
            db_market = market if market == "KRX" else None  # US는 NASDAQ/NYSE 섞임
            q = db.query(Symbol).filter(Symbol.code.in_(codes))
            if db_market:
                q = q.filter(Symbol.market == db_market)
            else:
                q = q.filter(Symbol.market.in_(["NASDAQ", "NYSE", "AMEX"]))
            id_by_code = {s.code: s.id for s in q.all()}
            now = datetime.utcnow()
            for r in rows:
                sid = id_by_code.get(r["code"])
                if not sid:
                    continue
                price_v = r.get("price")
                if price_v is None or price_v <= 0:
                    continue
                # change_pct로부터 prev_close 역산
                change = r.get("change_pct") or 0
                try:
                    prev = Decimal(str(price_v)) / (Decimal("1") + Decimal(str(change)) / Decimal("100"))
                except Exception:
                    prev = None
                existing = db.get(Price, sid)
                if existing:
                    existing.price = Decimal(str(price_v))
                    if prev is not None:
                        existing.prev_close = prev
                    existing.ts = now
                else:
                    db.add(Price(
                        symbol_id=sid,
                        price=Decimal(str(price_v)),
                        prev_close=prev,
                        ts=now,
                    ))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.debug("persist_prices {} skip: {}", market, e)


def _db_fallback(market: str, sort: Sort, limit: int) -> list[dict]:
    """DB Price 테이블에서 마지막 가격으로 응답 구성 (최후의 보루)."""
    try:
        db = SessionLocal()
        try:
            if market == "KRX":
                markets = ["KRX"]
            elif market == "US":
                markets = ["NASDAQ", "NYSE", "AMEX"]
            else:
                markets = ["UPBIT"]
            rows_db = (
                db.query(Symbol, Price)
                .join(Price, Price.symbol_id == Symbol.id)
                .filter(Symbol.market.in_(markets), Symbol.is_active)
                .all()
            )
            out = []
            for s, p in rows_db:
                if not p or not p.price or p.price <= 0:
                    continue
                price = float(p.price)
                prev = float(p.prev_close) if p.prev_close else price
                change_pct = ((price - prev) / prev * 100) if prev else 0.0
                mc = None
                if market == "KRX":
                    fb = KRX_MARKET_CAP_FALLBACK.get(s.code)
                    if fb:
                        mc = float(fb)
                out.append({
                    "market": s.market,
                    "code": s.code,
                    "name": s.name,
                    "price": price,
                    "change_pct": change_pct,
                    "volume": 0.0,
                    "value": 0.0,
                    "market_cap": mc,
                })
            return _sort_rows(out, sort)[:limit]
        finally:
            db.close()
    except Exception as e:
        logger.debug("db_fallback {} skip: {}", market, e)
        return []


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
    # 한 번 fetch한 데이터로 모든 sort 변형 채우기 (빈 결과는 캐시하지 않음)
    if out:
        for s in ("value", "volume", "change", "decline"):
            _store(("UPBIT", s), _sort_rows(list(out), s))  # type: ignore
        _persist_cache_to_disk()
        return _sort_rows(out, sort)[:limit]

    # 모든 소스 실패 → 만료된 캐시라도 있으면 stale로 반환
    for s in ("value", "volume", "change", "decline"):
        stale = _cache.get(("UPBIT", s))
        if stale:
            logger.warning("UPBIT popular: source failed, returning stale cache")
            return _sort_rows(list(stale[1]), sort)[:limit]
    return []


# ------------------------------------------------------------------ KRX

async def _toss_popular_rows(country: str, sort: Sort, limit: int) -> list[dict]:
    """Toss 랭킹으로 인기종목 행 생성. 이름/시장/시총은 DB·시드로 보강.

    country='KR'|'US'. market_cap 정렬은 Toss 미지원(fetch_rankings가 [] 반환) → [].
    Toss 미설정/실패 시에도 [] → 호출측 기존 폴백 경로가 실행된다.
    """
    # ETF/ETN을 걸러낸 뒤에도 limit 이 차도록 여유분(headroom)을 더 받는다.
    raw = await _toss.fetch_rankings(country, sort, count=min(100, max(limit, 30) + 30))
    if not raw:
        logger.info("toss ranking empty: country={} sort={}", country, sort)
        return []
    logger.info("toss ranking ok: country={} sort={} n={}", country, sort, len(raw))
    codes = [r["code"] for r in raw]

    def _load_db() -> dict[str, tuple[str | None, str | None, str | None]]:
        db = SessionLocal()
        try:
            return {
                s.code: (s.name, s.market, s.asset_type)
                for s in db.query(Symbol).filter(Symbol.code.in_(codes)).all()
            }
        finally:
            db.close()

    db_info = await asyncio.to_thread(_load_db)
    # Toss 종목정보(이름·시장·유형) 배치 1콜 — 이름 보강 + ETF/ETN 판별용
    try:
        toss_info = await _toss.fetch_stock_info(codes)
    except Exception:
        toss_info = {}
    kr_seed_name = {code: name for code, name, _, _ in KR_SEEDS}
    us_seed = {code: (name, mkt) for code, name, mkt, _ in US_SEEDS}

    out: list[dict] = []
    for r in raw:
        code = str(r["code"])
        db_name, db_market, db_type = db_info.get(code, (None, None, None))
        ti = toss_info.get(code) or {}
        # Toss "실시간차트"는 주식만 표기 → ETF/ETN 제외 (유형 모르면 통과=주식 취급)
        asset_type = (ti.get("asset_type") or db_type or "STOCK").upper()
        if asset_type in ("ETF", "ETN"):
            continue
        if country == "KR":
            name = ti.get("name") or db_name or kr_seed_name.get(code) or code
            market = "KRX"
            cap = KRX_MARKET_CAP_FALLBACK.get(code)
            market_cap = float(cap) if cap else None
        else:
            seed_name, seed_market = us_seed.get(code, (None, None))
            name = ti.get("name") or db_name or seed_name or code
            market = db_market or ti.get("market") or seed_market or "NASDAQ"
            market_cap = None
        price = _safe_float(r.get("price"))
        if price <= 0:
            continue
        out.append(
            {
                "market": market,
                "code": code,
                "name": name,
                "price": price,
                "change_pct": _safe_float(r.get("change_pct")),
                "volume": _safe_float(r.get("volume")),
                "value": _safe_float(r.get("value")),
                "market_cap": market_cap,
            }
        )
        if len(out) >= limit:
            break

    # Toss 종목정보를 DB에 저장(이름/검색 노출, 다음부터 캐시).
    if toss_info:
        await asyncio.to_thread(_persist_symbol_names, toss_info)
    return out


def _persist_symbol_names(info: dict[str, dict]) -> None:
    """Toss 종목정보를 Symbol 마스터에 upsert (이름 없던 종목 보강)."""
    db = SessionLocal()
    try:
        for code, fi in info.items():
            name = fi.get("name")
            market = fi.get("market") or "KRX"
            if not name:
                continue
            sym = (
                db.query(Symbol)
                .filter(Symbol.market == market, Symbol.code == code)
                .first()
            )
            if sym:
                if sym.name != name:
                    sym.name = name
            else:
                db.add(
                    Symbol(
                        code=code,
                        name=name,
                        market=market,
                        asset_type=fi.get("asset_type") or "STOCK",
                        currency=fi.get("currency") or "KRW",
                        is_active=True,
                    )
                )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug("persist symbol names failed: {}", e)
    finally:
        db.close()


async def popular_krx(sort: Sort, limit: int = 30, *, _force_full: bool = False) -> list[dict]:
    key = ("KRX", sort)
    if (c := _cached(key)) is not None:
        return c[:limit]

    lock = _lock_for("KRX")

    if not _force_full:
        # stale-while-revalidate: 즉시 응답 가능한 폴백 → 백그라운드 갱신 후 즉시 반환
        fallback = _immediate_fallback("KRX", sort, limit)
        if fallback is not None:
            if not lock.locked():
                _spawn_bg_refresh("KRX")
            return fallback

        # 폴백도 없음 (진짜 콜드 부팅) → 백그라운드에 fetch 떠넘기고 즉시 빈 응답
        # SWR이 4초 polling으로 다음 호출에 받아감 (사용자 멍하니 대기 방지)
        if not lock.locked():
            _spawn_bg_refresh("KRX")
        return []

    # _force_full=True: 백그라운드 task에서 호출됨 — 진짜 fetch 실행
    async with lock:
        if (c := _cached(("KRX", sort))) is not None:
            return c[:limit]

        # Toss 랭킹 우선 (market_cap 은 Toss 미지원 → 아래 pykrx 경로)
        if sort != "market_cap":
            toss_rows = await _toss_popular_rows("KR", sort, max(limit, 30))
            if toss_rows:
                _store(("KRX", sort), _sort_rows(list(toss_rows), sort))
                _persist_prices("KRX", toss_rows)
                _persist_cache_to_disk()
                return _sort_rows(toss_rows, sort)[:limit]

        def _fetch() -> list[dict]:
            try:
                from .sources.kis import _patch_requests_for_krx
                _patch_requests_for_krx()
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
                def _try_cap(d: str) -> "_pd.DataFrame | None":
                    """ALL → KOSPI+KOSDAQ 폴백."""
                    try:
                        df_all = stock.get_market_cap_by_ticker(d, market="ALL")
                        if df_all is not None and len(df_all) > 0:
                            return df_all
                    except Exception as e:
                        logger.warning("pykrx cap ALL fail {}: {}", d, e)
                    parts = []
                    for mkt in ("KOSPI", "KOSDAQ"):
                        try:
                            part = stock.get_market_cap_by_ticker(d, market=mkt)
                            if part is not None and len(part) > 0:
                                parts.append(part)
                        except Exception as e:
                            logger.warning("pykrx cap {} {} fail: {}", mkt, d, e)
                    if parts:
                        return _pd.concat(parts)
                    return None

                # used_date 우선, 안 되면 직전 영업일 한두 번 더 시도
                cap_df = None
                for d_off in range(0, 5):
                    cand_dt = (today - timedelta(days=d_off))
                    if cand_dt.weekday() >= 5:
                        continue
                    d_try = cand_dt.strftime("%Y%m%d")
                    cap_df = _try_cap(d_try)
                    if cap_df is not None and len(cap_df) > 0:
                        logger.info("KRX popular: market_cap date={} rows={}", d_try, len(cap_df))
                        break
                if cap_df is not None and len(cap_df) > 0:
                    cap_df = cap_df.reset_index().rename(
                        columns={"티커": "code", "시가총액": "market_cap"}
                    )
                    if "market_cap" not in cap_df.columns:
                        logger.warning(
                            "KRX cap: '시가총액' missing, columns={}",
                            list(cap_df.columns),
                        )
                    else:
                        for _r in cap_df[["code", "market_cap"]].to_dict("records"):
                            try:
                                v = float(_r["market_cap"])
                                if v > 0:
                                    cap_map[str(_r["code"])] = v
                            except Exception:
                                continue
                        logger.info("KRX popular: cap_map built rows={}", len(cap_map))
                else:
                    logger.warning("KRX popular: market_cap fetch all-failed")
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
        # 최종 폴백: pykrx 시총 fetch가 실패해 None이면 하드코딩 백업표 사용
        # (정확한 값은 아니지만 정렬 순서는 그럴듯하게 나옴)
        if market_cap is None:
            fb = KRX_MARKET_CAP_FALLBACK.get(code)
            if fb:
                market_cap = float(fb)
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
    # ★ 빈 결과는 캐시하지 않음 (다음 요청에서 다시 시도 → "데이터 없음" 락업 방지)
    if out:
        for s in ("value", "volume", "change", "decline", "market_cap"):
            _store(("KRX", s), _sort_rows(list(out), s))  # type: ignore
        _persist_prices("KRX", out)  # DB Price 보조 폴백
        _persist_cache_to_disk()      # 메인: 메모리 캐시 통째 디스크 저장
        return _sort_rows(out, sort)[:limit]

    # 모든 소스 실패 → 만료된 메모리 캐시라도 있으면 stale로 반환
    for s in ("value", "volume", "change", "decline", "market_cap"):
        stale = _cache.get(("KRX", s))
        if stale:
            logger.warning("KRX popular: all sources failed, returning stale memory cache")
            return _sort_rows(list(stale[1]), sort)[:limit]

    # 최후의 보루: DB Price 테이블 폴백
    db_rows = _db_fallback("KRX", sort, limit)
    if db_rows:
        logger.warning("KRX popular: returning DB Price fallback ({} rows)", len(db_rows))
        return db_rows
    return []


# ------------------------------------------------------------------ US

def _sort_rows(rows: list[dict], sort: Sort) -> list[dict]:
    # secondary key=code 로 안정 정렬 (값 동률 시 같은 순서 유지 → 화면 튐 방지)
    # 토스 기준은 정렬 로직상 거래대금/거래량과 동일(값 필드가 이미 토스 기준).
    if sort in ("value", "toss_value"):
        rows.sort(key=lambda x: (-(x.get("value") or 0), x.get("code", "")))
    elif sort in ("volume", "toss_volume"):
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


async def popular_us(sort: Sort, limit: int = 30, *, _force_full: bool = False) -> list[dict]:
    # 캐시 적중 시 즉시 반환
    if (c := _cached(("US", sort))) is not None:
        return c[:limit]

    lock = _lock_for("US")

    if not _force_full:
        # stale-while-revalidate: 즉시 응답 가능한 폴백 → 백그라운드 갱신 후 즉시 반환
        fallback = _immediate_fallback("US", sort, limit)
        if fallback is not None:
            if not lock.locked():
                _spawn_bg_refresh("US")
            return fallback

        # 폴백도 없음 → 백그라운드에 fetch 떠넘기고 즉시 빈 응답
        if not lock.locked():
            _spawn_bg_refresh("US")
        return []

    # _force_full=True: 백그라운드 task에서 호출됨 — 진짜 fetch 실행
    async with lock:
        # 락 진입 후 한 번 더 확인 (다른 호출이 방금 채웠을 수 있음)
        if (c := _cached(("US", sort))) is not None:
            return c[:limit]

        # Toss 랭킹 우선 (market_cap 은 Toss 미지원 → 아래 기존 경로)
        if sort != "market_cap":
            toss_rows = await _toss_popular_rows("US", sort, max(limit, 30))
            if toss_rows:
                _store(("US", sort), _sort_rows(list(toss_rows), sort))
                _persist_prices("US", toss_rows)
                _persist_cache_to_disk()
                return _sort_rows(toss_rows, sort)[:limit]

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

        # 빈 결과는 캐시하지 않음 — 다음 요청에서 다시 시도
        if out:
            _store(("US", sort), _sort_rows(list(out), sort))
            for s in ("value", "volume", "change", "decline", "market_cap"):
                if s != sort:
                    _store(("US", s), _sort_rows(list(out), s))  # type: ignore
            _persist_prices("US", out)
            _persist_cache_to_disk()
            return _sort_rows(out, sort)[:limit]

        # 모든 소스 실패 → 만료된 메모리 캐시라도 있으면 stale로 반환
        for s in ("value", "volume", "change", "decline", "market_cap"):
            stale = _cache.get(("US", s))
            if stale:
                logger.warning("US popular: all sources failed, returning stale memory cache")
                return _sort_rows(list(stale[1]), sort)[:limit]

        # 최후의 보루: DB Price 테이블 폴백
        db_rows = _db_fallback("US", sort, limit)
        if db_rows:
            logger.warning("US popular: returning DB Price fallback ({} rows)", len(db_rows))
            return db_rows
        return []


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
