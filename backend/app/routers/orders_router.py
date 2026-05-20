"""주문 라우터."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Order, Symbol, Trade, User
from ..services.engine import OrderError, cancel_order, place_order

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderCreate(BaseModel):
    symbol_id: int
    side: Literal["BUY", "SELL"]
    order_type: Literal["MARKET", "LIMIT", "SCHEDULED"]
    qty: Decimal = Field(gt=0)
    limit_price: Decimal | None = None
    scheduled_at: datetime | None = None


def _serialize(o: Order, sym: Symbol | None) -> dict:
    return {
        "id": o.id,
        "symbol_id": o.symbol_id,
        "code": sym.code if sym else None,
        "name": sym.name if sym else None,
        "market": sym.market if sym else None,
        "side": o.side,
        "order_type": o.order_type,
        "qty": str(o.qty),
        "limit_price": str(o.limit_price) if o.limit_price else None,
        "scheduled_at": o.scheduled_at.isoformat() if o.scheduled_at else None,
        "status": o.status,
        "filled_qty": str(o.filled_qty),
        "avg_fill_price": str(o.avg_fill_price) if o.avg_fill_price else None,
        "reject_reason": o.reject_reason,
        "created_at": o.created_at.isoformat(),
    }


@router.post("")
async def create(
    body: OrderCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        order = await place_order(
            db,
            user=user,
            symbol_id=body.symbol_id,
            side=body.side,
            order_type=body.order_type,
            qty=body.qty,
            limit_price=body.limit_price,
            scheduled_at=body.scheduled_at,
        )
    except OrderError as e:
        raise HTTPException(400, str(e))
    sym = db.get(Symbol, order.symbol_id)
    return _serialize(order, sym)


@router.get("")
def list_orders(
    status: str | None = None,
    limit: int = 50,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    q = db.query(Order).filter(Order.user_id == user.id)
    if status:
        q = q.filter(Order.status == status.upper())
    rows = q.order_by(Order.created_at.desc()).limit(limit).all()
    out = []
    for o in rows:
        sym = db.get(Symbol, o.symbol_id)
        out.append(_serialize(o, sym))
    return out


@router.delete("/{order_id}")
def cancel(
    order_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        o = cancel_order(db, user=user, order_id=order_id)
    except OrderError as e:
        raise HTTPException(400, str(e))
    sym = db.get(Symbol, o.symbol_id)
    return _serialize(o, sym)


@router.get("/trades")
def list_trades(
    limit: int = 100,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = (
        db.query(Trade, Order, Symbol)
        .join(Order, Order.id == Trade.order_id)
        .join(Symbol, Symbol.id == Order.symbol_id)
        .filter(Order.user_id == user.id)
        .order_by(Trade.executed_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": t.id,
            "order_id": t.order_id,
            "code": s.code,
            "name": s.name,
            "market": s.market,
            "side": o.side,
            "price": str(t.price),
            "qty": str(t.qty),
            "fee": str(t.fee),
            "tax": str(t.tax),
            "executed_at": t.executed_at.isoformat(),
        }
        for t, o, s in rows
    ]
