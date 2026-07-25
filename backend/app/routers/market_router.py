"""시장 조회 API.

- GET /market/search?q=...        종목명/코드 검색
- GET /market/quote/{market}/{code}  현재가 (보유/관심이면 DB, 아니면 on-demand)
- GET /market/status               시장별 개장 여부
- POST /market/symbols/sync        (admin) 수동 동기화
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import admin_required, current_user
from ..db import get_db
from ..models import Price, Symbol, User
from ..services.industries import industries as industries_svc
from ..services.industries import industry_label
from ..services.market_calendar import is_market_open, next_open
from ..services.history import get_history
from ..services.popular import popular as popular_svc
from ..services.quotes import get_quote
from ..services.sources import toss as _toss
from ..services.symbol_sync import sync_all

router = APIRouter(prefix="/market", tags=["market"])

# --- 거래비율(호가 잔량 근사) 캐시 ------------------------------------
# 종목별 매수/매도 호가 총잔량 비율. 응답을 막지 않도록 캐시만 즉시 반환하고
# 만료분은 백그라운드로 갱신한다. (Toss "거래 비율"의 근사)
_ratio_cache: dict[str, tuple[float, float | None]] = {}
_RATIO_TTL = 30.0


def _spawn_ratio_refresh(codes: list[str]) -> None:
    now = time.time()
    need = [
        c
        for c in codes
        if not (_ratio_cache.get(c) and now - _ratio_cache[c][0] < _RATIO_TTL)
    ]
    if not need:
        return

    async def _go() -> None:
        sem = asyncio.Semaphore(6)

        async def _one(code: str) -> None:
            async with sem:
                try:
                    ob = await _toss.fetch_orderbook(code)
                except Exception:
                    ob = None
                r: float | None = None
                if ob:
                    bids = sum(x.get("volume") or 0 for x in ob.get("bids", []))
                    asks = sum(x.get("volume") or 0 for x in ob.get("asks", []))
                    tot = bids + asks
                    r = (bids / tot) if tot > 0 else None
                _ratio_cache[code] = (time.time(), r)

        await asyncio.gather(*(_one(c) for c in need))

    try:
        asyncio.get_running_loop().create_task(_go())
    except RuntimeError:
        pass


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=50),
    limit: int = 30,
    db: Session = Depends(get_db),
) -> list[dict]:
    """종목 검색.

    - 한/영문 검색 모두 대응 (Symbol 한글명 + 영문 alias)
    - 매칭 우선순위: 코드 정확일치 > 이름 prefix > 코드/이름 부분일치
    - Unicode NFC 정규화로 macOS NFD 입력도 매칭
    """
    import unicodedata
    from ..services.search_aliases import EN_TO_CODE

    qn = unicodedata.normalize("NFC", q.strip())
    if not qn:
        return []
    like = f"%{qn}%"
    starts = f"{qn}%"

    # 1) 영문 alias → code 변환 (한 단어 검색만)
    alias_codes: set[str] = set()
    qn_lower = qn.lower()
    for alias, code in EN_TO_CODE.items():
        if alias in qn_lower:
            alias_codes.add(code)

    base = db.query(Symbol).filter(Symbol.is_active)
    # OR 조건: 코드/이름 ilike OR alias code 매칭
    conds = [Symbol.code.ilike(like), Symbol.name.ilike(like)]
    if alias_codes:
        conds.append(Symbol.code.in_(list(alias_codes)))
    rows = base.filter(or_(*conds)).limit(200).all()

    # 시드 자가복구 — DB 동기화 실패 시에도 시드는 검색되도록 즉시 insert
    from ..services.sources.kr_seeds import KR_SEEDS
    from ..services.sources.us_seeds import US_SEEDS

    seen_keys = {(s.market, s.code) for s in rows}
    added: list[Symbol] = []
    for code, name, asset_type, sector in KR_SEEDS:
        if ("KRX", code) in seen_keys:
            continue
        if qn in name or qn in code or qn_lower in name.lower():
            s = Symbol(
                code=code, name=name, market="KRX",
                asset_type=asset_type, currency="KRW", sector=sector,
                is_active=True,
            )
            db.add(s)
            try:
                db.commit()
                db.refresh(s)
                added.append(s)
            except Exception:
                db.rollback()
    for code, name, mkt, asset_type in US_SEEDS:
        if (mkt, code) in seen_keys:
            continue
        nl = name.lower()
        if qn in name or qn_lower == code.lower() or qn_lower in nl:
            s = Symbol(
                code=code, name=name, market=mkt,
                asset_type=asset_type, currency="USD",
                is_active=True,
            )
            db.add(s)
            try:
                db.commit()
                db.refresh(s)
                added.append(s)
            except Exception:
                db.rollback()
    rows.extend(added)

    # 우선순위 점수: 코드 정확>이름 정확>코드 prefix>이름 prefix>코드 부분>이름 부분>alias>기타
    def score(s: Symbol) -> tuple:
        cl = s.code.lower()
        nl = s.name.lower()
        if cl == qn_lower:
            return (0, 0, s.market, s.code)
        if nl == qn_lower:
            return (1, 0, s.market, s.code)
        if cl.startswith(qn_lower):
            return (2, len(cl), s.market, s.code)
        if nl.startswith(qn_lower):
            return (3, len(nl), s.market, s.code)
        if qn_lower in cl:
            return (4, len(cl), s.market, s.code)
        if qn_lower in nl:
            return (5, len(nl), s.market, s.code)
        if s.code in alias_codes:
            return (6, 0, s.market, s.code)
        return (9, 0, s.market, s.code)

    rows.sort(key=score)
    rows = rows[:limit]

    # 시드와 이름이 다르면 한글명으로 보정
    dirty = False
    for s in rows:
        seed = _seed_name(s.market, s.code)
        if seed and s.name != seed:
            s.name = seed
            dirty = True
    if dirty:
        try:
            db.commit()
        except Exception:
            db.rollback()
    return [
        {
            "id": s.id,
            "code": s.code,
            "name": s.name,
            "market": s.market,
            "asset_type": s.asset_type,
            "currency": s.currency,
        }
        for s in rows
    ]


def _seed_name(market: str, code: str) -> str | None:
    """DB가 비어 있어도 시드에서 한글 이름을 가져오는 fallback."""
    if market == "KRX":
        from ..services.sources.kr_seeds import KR_SEEDS
        for c, n, _, _ in KR_SEEDS:
            if c == code:
                return n
    elif market in ("NASDAQ", "NYSE", "AMEX"):
        from ..services.sources.us_seeds import US_SEEDS
        for c, n, _, _ in US_SEEDS:
            if c == code:
                return n
    elif market == "UPBIT":
        # 업비트 시드는 별도 없음 (API에서 동기화)
        return None
    return None


@router.get("/quote/{market}/{code}")
async def quote(market: str, code: str, db: Session = Depends(get_db)) -> dict:
    """현재가 — DB 캐시 우선, 외부 호출은 짧은 타임아웃 + 백그라운드 갱신.

    1. DB Price 있고 60초 이내 → 즉시 반환 + 백그라운드 갱신 trigger
    2. DB Price 있고 오래됨    → 짧게 기다려보고 안 오면 DB 값 + 백그라운드 갱신
    3. DB Price 없음            → 외부 호출 (max_wait=2s)
    """
    from datetime import datetime, timedelta
    from ..services.quotes import _spawn_refresh

    mkt = market.upper()
    sym = (
        db.query(Symbol)
        .filter(Symbol.market == mkt, Symbol.code == code)
        .first()
    )

    # 시드 한글명 가져오기
    seed_name = _seed_name(mkt, code)

    # DB에 없으면 시드로 즉시 등록 (사용자가 매수 못 하는 일 방지)
    if not sym and seed_name:
        from ..services.sources.us_seeds import US_SEEDS
        from ..services.sources.kr_seeds import KR_SEEDS
        meta_us = next((x for x in US_SEEDS if x[0] == code), None)
        meta_kr = next((x for x in KR_SEEDS if x[0] == code), None)
        if meta_us:
            _, name, m, asset_type = meta_us
            sym = Symbol(code=code, name=name, market=m, asset_type=asset_type, currency="USD", is_active=True)
        elif meta_kr:
            _, name, asset_type, sector = meta_kr
            sym = Symbol(code=code, name=name, market="KRX", asset_type=asset_type, currency="KRW", sector=sector, is_active=True)
        if sym:
            db.add(sym)
            try:
                db.commit()
                db.refresh(sym)
            except Exception:
                db.rollback()
                sym = None

    db_price = db.get(Price, sym.id) if sym else None

    # 이름 자가복구
    if sym and seed_name and sym.name != seed_name:
        sym.name = seed_name
        try:
            db.commit()
        except Exception:
            db.rollback()
    display_name = (sym.name if sym else None) or seed_name or code

    # 이름 미해결(코드 그대로) → Toss 종목정보로 해결 + DB에 반영.
    # pykrx 전종목 목록에 없는 ETN/레버리지 등이 코드로만 뜨는 것을 보완.
    if display_name == code:
        try:
            info = (await _toss.fetch_stock_info([code])).get(code)
        except Exception:
            info = None
        if info and info.get("name"):
            display_name = info["name"]
            if sym:
                sym.name = display_name
            else:
                sym = Symbol(
                    code=code,
                    name=display_name,
                    market=mkt,
                    asset_type=info.get("asset_type", "STOCK"),
                    currency=info.get("currency")
                    or ("USD" if mkt in ("NASDAQ", "NYSE", "AMEX") else "KRW"),
                    is_active=True,
                )
                db.add(sym)
            try:
                db.commit()
                db.refresh(sym)
                db_price = db.get(Price, sym.id) if sym else db_price
            except Exception:
                db.rollback()

    # DB Price가 신선하면 즉시 반환 (UPBIT는 30s, 그 외는 60s)
    fresh_window = timedelta(seconds=30 if mkt == "UPBIT" else 60)
    db_fresh = (
        db_price is not None
        and db_price.ts is not None
        and (datetime.utcnow() - db_price.ts) < fresh_window
    )

    if db_fresh:
        _spawn_refresh(mkt, code)
        return {
            "market": mkt,
            "code": code,
            "name": display_name,
            "symbol_id": sym.id if sym else None,
            "currency": sym.currency if sym else ("USD" if mkt in ("NASDAQ", "NYSE", "AMEX") else "KRW"),
            "price": str(db_price.price),
            "prev_close": str(db_price.prev_close) if db_price.prev_close else None,
            "source": "db_fresh",
        }

    # DB가 오래됐거나 없음 → 외부 호출 (DB가 있으면 짧게, 없으면 좀 더 기다림)
    q = await get_quote(mkt, code, max_wait=1.5 if db_price else 3.0)

    if not q and not db_price:
        raise HTTPException(status_code=404, detail="quote unavailable")

    price = q["price"] if q else db_price.price
    prev = (q.get("prev_close") if q else None) or (db_price.prev_close if db_price else None)
    return {
        "market": mkt,
        "code": code,
        "name": display_name,
        "symbol_id": sym.id if sym else None,
        "currency": sym.currency if sym else ("USD" if mkt in ("NASDAQ", "NYSE", "AMEX") else "KRW"),
        "price": str(price),
        "prev_close": str(prev) if prev else None,
        "source": "ondemand" if q else "db_stale",
    }


@router.get("/status")
def status() -> dict:
    """시장별 개장 여부 + 운영 시간 (현지 + 한국 시간 환산)."""
    from datetime import datetime
    from ..services.market_calendar import HOURS, KST

    out = {}
    for m in ("KRX", "NASDAQ", "NYSE", "UPBIT"):
        info: dict = {
            "open": is_market_open(m),
            "next_open": next_open(m).isoformat() if m != "UPBIT" else None,
        }
        if m == "UPBIT":
            info["hours_local"] = "24시간"
            info["hours_kst"] = "24시간"
        elif m in HOURS:
            open_t, close_t, tz = HOURS[m]
            info["hours_local"] = f"{open_t.strftime('%H:%M')}~{close_t.strftime('%H:%M')}"
            today_local = datetime.now(tz)
            o = today_local.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0).astimezone(KST)
            c = today_local.replace(hour=close_t.hour, minute=close_t.minute, second=0, microsecond=0).astimezone(KST)
            if c.day != o.day or c < o:
                info["hours_kst"] = f"{o.strftime('%H:%M')}~익일 {c.strftime('%H:%M')}"
            else:
                info["hours_kst"] = f"{o.strftime('%H:%M')}~{c.strftime('%H:%M')}"
        out[m] = info
    return out


@router.get("/indicators")
async def indicators() -> list[dict]:
    """상단 지표바용: 나스닥(yfinance) + 코스피(Toss). 실패 항목은 생략."""
    import asyncio as _asyncio

    from ..services.history import _yf_history
    from ..services.sources import yfinance_src as _yf

    async def _nasdaq() -> dict | None:
        try:
            q = await _yf.fetch_quote("^IXIC")
            if not q:
                return None
            price = float(q["price"])
            prev = float(q.get("prev_close") or price)
            hist = await _yf_history("NASDAQ", "^IXIC", "1mo", "1d")
            spark = [float(r["close"]) for r in hist][-30:]
            return {
                "key": "NASDAQ",
                "label": "나스닥",
                "price": price,
                "change_pct": ((price - prev) / prev * 100) if prev else 0.0,
                "spark": spark,
                "currency": "USD",
            }
        except Exception:
            return None

    async def _kospi() -> dict | None:
        try:
            candles = await _toss.fetch_index_candles("KOSPI", "1d", 30)
            prices = await _toss.fetch_index_prices(["KOSPI"])
            if prices.get("KOSPI"):
                last = float(prices["KOSPI"])
            elif candles:
                last = float(candles[-1]["close"])
            else:
                return None
            prev = float(candles[-2]["close"]) if len(candles) >= 2 else last
            spark = [float(r["close"]) for r in candles][-30:]
            return {
                "key": "KOSPI",
                "label": "코스피",
                "price": last,
                "change_pct": ((last - prev) / prev * 100) if prev else 0.0,
                "spark": spark,
                "currency": "KRW",
            }
        except Exception:
            return None

    results = await _asyncio.gather(_nasdaq(), _kospi())
    return [r for r in results if r]


@router.get("/orderbook/{market}/{code}")
async def orderbook(market: str, code: str) -> dict:
    """호가 (Toss). 미지원/실패 시 빈 호가."""
    ob = await _toss.fetch_orderbook(code)
    return ob or {"asks": [], "bids": [], "currency": None}


@router.get("/trades/{market}/{code}")
async def market_trades(market: str, code: str, count: int = 30) -> list[dict]:
    """최근 체결 (Toss)."""
    return await _toss.fetch_trades(code, count)


@router.get("/history/{market}/{code}")
async def history(market: str, code: str, interval: str = "1d") -> list[dict]:
    if interval not in ("1d", "1h", "5m", "1m", "1w", "1mo", "all"):
        raise HTTPException(400, "interval must be 1m/5m/1h/1d/1w/1mo/all")
    return await get_history(market.upper(), code, interval)  # type: ignore


@router.get("/popular")
async def popular(
    market: str = Query(..., pattern="^(KRX|US|UPBIT)$"),
    sort: str = Query(
        "value",
        pattern="^(value|volume|change|decline|market_cap|toss_value|toss_volume)$",
    ),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict]:
    """시장별 인기종목.

    - market: KRX(국내) / US(해외) / UPBIT(코인)
    - sort:   value(거래대금) / volume(거래량) / change(급등) /
              decline(급락) / market_cap(시가총액)
    """
    rows = await popular_svc(market, sort, limit)  # type: ignore
    # 관심(하트) 토글용 symbol_id 보강
    if rows:
        codes = [r["code"] for r in rows]
        id_map = {
            (s.market, s.code): s.id
            for s in db.query(Symbol.id, Symbol.market, Symbol.code)
            .filter(Symbol.code.in_(codes))
            .all()
        }
        for r in rows:
            r["symbol_id"] = id_map.get((r["market"], r["code"]))
            r["industry"] = industry_label(r["market"], r["code"], r.get("name"))
        # 거래비율(호가 근사) — 코인 제외. 캐시 즉시반환 + 만료분 백그라운드 갱신.
        if market != "UPBIT":
            row_codes = [r["code"] for r in rows]
            _spawn_ratio_refresh(row_codes)
            for r in rows:
                c = _ratio_cache.get(r["code"])
                r["buy_ratio"] = c[1] if c else None
    return rows


@router.get("/industries")
async def industries() -> list[dict]:
    """업종별/테마별 종목 — 한국/미국/코인 묶음."""
    return await industries_svc()


@router.post("/symbols/sync")
async def manual_sync(_admin: User = Depends(admin_required)) -> dict:
    return await sync_all()


@router.get("/debug")
async def debug(_user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """진단: 외부 소스 / DB 상태."""
    import asyncio as _asyncio

    out: dict = {}

    # Symbol DB
    out["symbol_count"] = {
        m: db.query(Symbol).filter(Symbol.market == m).count()
        for m in ("KRX", "NASDAQ", "NYSE", "UPBIT")
    }
    out["sample_krx"] = [
        {"code": s.code, "name": s.name}
        for s in db.query(Symbol).filter(Symbol.market == "KRX").limit(5).all()
    ]

    # pykrx 상태
    def _check_pykrx() -> dict:
        try:
            from ..services.sources.kis import _patch_requests_for_krx
            _patch_requests_for_krx()
            from datetime import datetime, timedelta

            from pykrx import stock  # type: ignore

            res: dict = {"installed": True}
            today = datetime.now()
            for d in range(0, 7):
                date = (today - timedelta(days=d)).strftime("%Y%m%d")
                try:
                    df = stock.get_market_ohlcv_by_ticker(date=date, market="ALL")
                    if df is not None and len(df) > 0:
                        res["sample_date"] = date
                        res["rows"] = len(df)
                        return res
                except Exception as e:
                    res.setdefault("errors", []).append(f"{date}: {e}")
            res["empty"] = True
            return res
        except Exception as e:
            return {"installed": False, "error": str(e)}

    out["pykrx"] = await _asyncio.wait_for(_asyncio.to_thread(_check_pykrx), timeout=30)

    # yfinance 상태
    def _check_yf() -> dict:
        try:
            import yfinance as yf  # type: ignore

            t = yf.Ticker("AAPL")
            fi = t.fast_info
            return {
                "installed": True,
                "AAPL_price": float(fi.last_price or 0),
                "AAPL_prev": float(fi.previous_close or 0),
            }
        except Exception as e:
            return {"installed": False, "error": str(e)}

    out["yfinance"] = await _asyncio.wait_for(_asyncio.to_thread(_check_yf), timeout=20)

    # KIS 상태
    from ..services.sources import kis as _kis

    out["kis"] = {
        "configured": _kis._configured(),
        "env": _kis.settings.KIS_ENV if _kis._configured() else None,
    }
    if _kis._configured():
        tok = await _kis.get_access_token()
        out["kis"]["token_ok"] = bool(tok)
        sample = await _kis.fetch_price("005930")
        out["kis"]["samsung_quote"] = {k: str(v) for k, v in sample.items()} if sample else None

    return out
