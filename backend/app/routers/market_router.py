"""시장 조회 API.

- GET /market/search?q=...        종목명/코드 검색
- GET /market/quote/{market}/{code}  현재가 (보유/관심이면 DB, 아니면 on-demand)
- GET /market/status               시장별 개장 여부
- POST /market/symbols/sync        (admin) 수동 동기화
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import admin_required, current_user
from ..db import get_db
from ..models import Price, Symbol, User
from ..services.market_calendar import is_market_open, next_open
from ..services.history import get_history
from ..services.popular import popular as popular_svc
from ..services.quotes import get_quote
from ..services.symbol_sync import sync_all

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=50),
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[dict]:
    """종목 검색 (코드/이름 부분일치)."""
    like = f"%{q}%"
    rows = (
        db.query(Symbol)
        .filter(Symbol.is_active, or_(Symbol.code.ilike(like), Symbol.name.ilike(like)))
        .order_by(Symbol.market, Symbol.code)
        .limit(limit)
        .all()
    )
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


@router.get("/quote/{market}/{code}")
async def quote(market: str, code: str, db: Session = Depends(get_db)) -> dict:
    # DB에 마스터가 있는지 먼저 확인 (UI에서 검색 후 호출하는 정상 흐름)
    sym = (
        db.query(Symbol)
        .filter(Symbol.market == market.upper(), Symbol.code == code)
        .first()
    )
    # 최신가 캐시
    db_price = db.get(Price, sym.id) if sym else None

    # On-demand 호출 (캐시 만료 또는 미존재 시)
    q = await get_quote(market.upper(), code)
    if not q and not db_price:
        raise HTTPException(status_code=404, detail="quote unavailable")

    price = q["price"] if q else db_price.price
    prev = (q.get("prev_close") if q else None) or (db_price.prev_close if db_price else None)
    return {
        "market": market.upper(),
        "code": code,
        "name": sym.name if sym else code,
        "price": str(price),
        "prev_close": str(prev) if prev else None,
        "source": "ondemand" if q else "cache",
    }


@router.get("/status")
def status() -> dict:
    out = {}
    for m in ("KRX", "NASDAQ", "NYSE", "UPBIT"):
        out[m] = {
            "open": is_market_open(m),
            "next_open": next_open(m).isoformat() if m != "UPBIT" else None,
        }
    return out


@router.get("/history/{market}/{code}")
async def history(market: str, code: str, interval: str = "1d") -> list[dict]:
    if interval not in ("1d", "1h", "5m", "1m", "1w", "1mo", "all"):
        raise HTTPException(400, "interval must be 1m/5m/1h/1d/1w/1mo/all")
    return await get_history(market.upper(), code, interval)  # type: ignore


@router.get("/popular")
async def popular(
    market: str = Query(..., pattern="^(KRX|US|UPBIT)$"),
    sort: str = Query("value", pattern="^(value|volume|change)$"),
    limit: int = Query(30, ge=1, le=100),
) -> list[dict]:
    """시장별 인기종목.

    - market: KRX(국내) / US(해외) / UPBIT(코인)
    - sort:   value(거래대금) / volume(거래량) / change(등락률)
    """
    return await popular_svc(market, sort, limit)  # type: ignore


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
