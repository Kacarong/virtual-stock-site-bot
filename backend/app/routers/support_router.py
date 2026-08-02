"""지원금(관리자 지급) API.

- 관리자: 모든 유저에게 지원금 1회 지급 + 알림 공지 생성
- 유저: 미확인 지원금 알림 조회 / 알림 끄기(닫기)
- 유저: 받은 지원금 총액 (수익 탭에서 '지원금'으로 표기)
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..auth import admin_required, current_user
from ..db import get_db
from ..models import CashLedger, SupportGrant, SupportGrantDismissal, User

router = APIRouter(prefix="/support", tags=["support"])


class GrantBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    message: str | None = Field(default=None, max_length=1000)
    amount_krw: Decimal = Field(gt=0)


@router.post("/grant")
def create_grant(
    body: GrantBody,
    admin: User = Depends(admin_required),
    db: Session = Depends(get_db),
) -> dict:
    """모든 유저에게 지원금 지급 + 알림 공지 생성 (관리자 전용)."""
    amount = Decimal(body.amount_krw)

    users = db.query(User).all()
    grant = SupportGrant(
        title=body.title.strip(),
        message=(body.message or "").strip() or None,
        amount_krw=amount,
        created_by=admin.id,
        granted_count=len(users),
    )
    db.add(grant)
    db.flush()  # grant.id 확보

    for u in users:
        u.cash_krw = (u.cash_krw or Decimal("0")) + amount
        db.add(
            CashLedger(
                user_id=u.id,
                currency="KRW",
                amount=amount,
                reason="SUPPORT",
                ref_id=grant.id,
                memo=body.title.strip(),
            )
        )
    db.commit()
    return {
        "ok": True,
        "grant_id": grant.id,
        "granted_count": len(users),
        "amount_krw": str(amount),
    }


@router.get("/notifications")
def notifications(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """이 유저가 아직 끄지 않은 지원금 알림 (최신순)."""
    dismissed_ids = [
        row[0]
        for row in db.query(SupportGrantDismissal.grant_id)
        .filter(SupportGrantDismissal.user_id == user.id)
        .all()
    ]
    q = db.query(SupportGrant)
    if dismissed_ids:
        q = q.filter(SupportGrant.id.notin_(dismissed_ids))
    grants = q.order_by(SupportGrant.created_at.desc()).limit(20).all()
    return [
        {
            "id": g.id,
            "title": g.title,
            "message": g.message,
            "amount_krw": str(g.amount_krw),
            "created_at": g.created_at.isoformat(),
        }
        for g in grants
    ]


@router.post("/notifications/{grant_id}/dismiss")
def dismiss(
    grant_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """지원금 알림 끄기(닫기)."""
    g = db.get(SupportGrant, grant_id)
    if not g:
        raise HTTPException(404, "grant not found")
    exists = (
        db.query(SupportGrantDismissal)
        .filter(
            SupportGrantDismissal.user_id == user.id,
            SupportGrantDismissal.grant_id == grant_id,
        )
        .first()
    )
    if not exists:
        db.add(SupportGrantDismissal(user_id=user.id, grant_id=grant_id))
        db.commit()
    return {"ok": True}


@router.get("/summary")
def summary(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """이 유저가 받은 지원금 총액 (수익 탭 표기용)."""
    total = (
        db.query(sa_func.coalesce(sa_func.sum(CashLedger.amount), 0))
        .filter(CashLedger.user_id == user.id, CashLedger.reason == "SUPPORT")
        .scalar()
    )
    return {"total_support_krw": str(total or Decimal("0"))}
