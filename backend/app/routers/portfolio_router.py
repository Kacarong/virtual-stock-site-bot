"""포트폴리오 / 자산 요약."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from sqlalchemy import func as sa_func

from ..auth import current_user
from ..db import get_db
from ..models import Holding, Price, Symbol, User
from ..services.fx import get_usdkrw

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/ranking")
async def ranking(
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """전 사용자 총자산 KRW 환산 랭킹.

    - Price DB(인터넷 끊기더라도 마지막 가격 유지)로 평가
    - 현금 + 평가금
    """
    rate = await get_usdkrw()
    users = db.query(User).all()
    out: list[dict] = []
    for u in users:
        rows = (
            db.query(Holding, Symbol, Price)
            .join(Symbol, Symbol.id == Holding.symbol_id)
            .outerjoin(Price, Price.symbol_id == Symbol.id)
            .filter(Holding.user_id == u.id, Holding.qty > 0)
            .all()
        )
        value_krw = Decimal("0")
        for h, s, p in rows:
            cur_price = p.price if p else h.avg_cost
            v = cur_price * h.qty
            if s.currency == "USD":
                v = v * rate
            value_krw += v
        cash_total = u.cash_krw + u.cash_usd * rate
        total = value_krw + cash_total
        out.append(
            {
                "user_id": u.id,
                "username": u.username,
                "avatar_url": u.avatar_url,
                "total_assets_krw": str(total),
                "cash_krw": str(cash_total),
                "holdings_krw": str(value_krw),
            }
        )
    out.sort(key=lambda x: Decimal(x["total_assets_krw"]), reverse=True)
    for i, row in enumerate(out, 1):
        row["rank"] = i
    return out


@router.get("")
async def portfolio(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    rate = await get_usdkrw()  # 1 USD = ? KRW

    holdings = (
        db.query(Holding, Symbol, Price)
        .join(Symbol, Symbol.id == Holding.symbol_id)
        .outerjoin(Price, Price.symbol_id == Symbol.id)
        .filter(Holding.user_id == user.id, Holding.qty > 0)
        .all()
    )

    items = []
    total_value_krw = Decimal("0")
    total_cost_krw = Decimal("0")
    for h, s, p in holdings:
        cur_price = p.price if p else h.avg_cost
        value_native = cur_price * h.qty
        cost_native = h.avg_cost * h.qty
        pnl_native = value_native - cost_native
        pnl_pct = (pnl_native / cost_native * 100) if cost_native else Decimal("0")

        # KRW 환산
        if s.currency == "USD":
            value_krw = value_native * rate
            cost_krw = cost_native * rate
        else:
            value_krw = value_native
            cost_krw = cost_native

        total_value_krw += value_krw
        total_cost_krw += cost_krw

        items.append(
            {
                "symbol_id": s.id,
                "code": s.code,
                "name": s.name,
                "market": s.market,
                "currency": s.currency,
                "qty": str(h.qty),
                "avg_cost": str(h.avg_cost),
                "price": str(cur_price),
                "value": str(value_native),
                "value_krw": str(value_krw),
                "pnl": str(pnl_native),
                "pnl_pct": f"{pnl_pct:.2f}",
            }
        )

    # 현금
    cash_total_krw = user.cash_krw + user.cash_usd * rate
    total_assets_krw = total_value_krw + cash_total_krw
    total_pnl_krw = total_value_krw - total_cost_krw
    total_pnl_pct = (
        (total_pnl_krw / total_cost_krw * 100) if total_cost_krw else Decimal("0")
    )

    return {
        "cash_krw": str(user.cash_krw),
        "cash_usd": str(user.cash_usd),
        "usdkrw": str(rate),
        "holdings": items,
        "summary": {
            "total_value_krw": str(total_value_krw),  # 평가금
            "total_cost_krw": str(total_cost_krw),    # 매수금
            "total_pnl_krw": str(total_pnl_krw),
            "total_pnl_pct": f"{total_pnl_pct:.2f}",
            "total_assets_krw": str(total_assets_krw),
        },
    }
