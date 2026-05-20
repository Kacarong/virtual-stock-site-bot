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

from ..auth import admin_required
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
    if interval not in ("1d", "1h", "5m"):
        raise HTTPException(400, "interval must be 1d/1h/5m")
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
