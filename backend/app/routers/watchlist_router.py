"""관심종목."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Price, Symbol, User, Watchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
def list_watchlist(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = (
        db.query(Watchlist, Symbol, Price)
        .join(Symbol, Symbol.id == Watchlist.symbol_id)
        .outerjoin(Price, Price.symbol_id == Symbol.id)
        .filter(Watchlist.user_id == user.id)
        .order_by(Watchlist.created_at.desc())
        .all()
    )
    out = []
    for w, s, p in rows:
        out.append(
            {
                "symbol_id": s.id,
                "code": s.code,
                "name": s.name,
                "market": s.market,
                "currency": s.currency,
                "price": str(p.price) if p else None,
                "prev_close": str(p.prev_close) if p and p.prev_close else None,
            }
        )
    return out


@router.post("/{symbol_id}")
def add_watch(
    symbol_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    sym = db.get(Symbol, symbol_id)
    if not sym:
        raise HTTPException(404, "symbol not found")
    try:
        db.add(Watchlist(user_id=user.id, symbol_id=symbol_id))
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"ok": True}


@router.delete("/{symbol_id}")
def remove_watch(
    symbol_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    db.query(Watchlist).filter(
        Watchlist.user_id == user.id, Watchlist.symbol_id == symbol_id
    ).delete()
    db.commit()
    return {"ok": True}
