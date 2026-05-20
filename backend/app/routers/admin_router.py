"""관리자 API.

웹 관리자 페이지 + Discord 봇 모두 동일 권한 정책 (.env의 ADMIN_DISCORD_IDS).
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import admin_required
from ..db import get_db
from ..models import CashLedger, Holding, Order, User

router = APIRouter(prefix="/admin", tags=["admin"])


class CashAdjust(BaseModel):
    currency: str  # KRW / USD
    amount: Decimal  # 양수=지급, 음수=차감
    memo: str | None = None


@router.get("/users")
def list_users(
    _admin: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "discord_id": u.discord_id,
            "username": u.username,
            "cash_krw": str(u.cash_krw),
            "cash_usd": str(u.cash_usd),
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat(),
        }
        for u in rows
    ]


@router.post("/users/{user_id}/cash")
def adjust_cash(
    user_id: int,
    body: CashAdjust,
    admin: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "user not found")
    if body.currency.upper() not in ("KRW", "USD"):
        raise HTTPException(400, "currency must be KRW or USD")

    if body.currency.upper() == "KRW":
        u.cash_krw = (u.cash_krw or Decimal("0")) + body.amount
        if u.cash_krw < 0:
            raise HTTPException(400, "would result in negative KRW")
    else:
        u.cash_usd = (u.cash_usd or Decimal("0")) + body.amount
        if u.cash_usd < 0:
            raise HTTPException(400, "would result in negative USD")

    db.add(
        CashLedger(
            user_id=user_id,
            currency=body.currency.upper(),
            amount=body.amount,
            reason="ADMIN",
            memo=body.memo or f"by {admin.username}",
        )
    )
    db.commit()
    return {"ok": True, "cash_krw": str(u.cash_krw), "cash_usd": str(u.cash_usd)}


@router.post("/users/{user_id}/reset")
def reset_user(
    user_id: int,
    admin: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> dict:
    """사용자 보유/주문 초기화하고 초기 자본금만 남김."""
    from ..config import settings

    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "user not found")
    db.query(Holding).filter(Holding.user_id == user_id).delete()
    db.query(Order).filter(Order.user_id == user_id).delete()
    u.cash_krw = Decimal(settings.INITIAL_CASH_KRW)
    u.cash_usd = Decimal("0")
    db.add(
        CashLedger(
            user_id=user_id,
            currency="KRW",
            amount=Decimal(settings.INITIAL_CASH_KRW),
            reason="ADMIN",
            memo=f"reset by {admin.username}",
        )
    )
    db.commit()
    return {"ok": True}
