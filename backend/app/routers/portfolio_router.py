"""포트폴리오 / 자산 요약."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from sqlalchemy import func as sa_func

from ..auth import current_user
from ..db import get_db
from ..models import Holding, Order, Price, Symbol, Trade, User
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


# --- 실현손익 ---------------------------------------------------------

@router.get("/realized")
async def realized(
    period: str = Query("all", pattern="^(all|daily|monthly)$"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """매도 시점의 실현 손익 합계.

    각 사용자의 (BUY/SELL) 체결을 시간순으로 재생:
    - BUY: qty 누적 + 가중평균 단가 업데이트
    - SELL: 실현 PnL = (체결가 - avg_cost) * qty - fee - tax
    - 매도 후 잔여 qty=0이면 avg_cost 리셋

    period=all: 단일 합계
    period=daily: 일별 버킷 (최근 365일)
    period=monthly: 월별 버킷
    """
    rate = await get_usdkrw()

    # 사용자 주문 + 체결 시간순 조회
    rows = (
        db.query(Trade, Order, Symbol)
        .join(Order, Order.id == Trade.order_id)
        .join(Symbol, Symbol.id == Order.symbol_id)
        .filter(Order.user_id == user.id)
        .order_by(Trade.executed_at.asc())
        .all()
    )

    # symbol_id → {qty, avg_cost}
    state: dict[int, dict] = defaultdict(lambda: {"qty": Decimal("0"), "avg": Decimal("0")})
    buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    total = Decimal("0")

    def bucket_key(dt: datetime) -> str:
        if period == "daily":
            return dt.strftime("%Y-%m-%d")
        if period == "monthly":
            return dt.strftime("%Y-%m")
        return "all"

    for t, o, s in rows:
        st = state[s.id]
        price = t.price
        qty = t.qty
        if o.side == "BUY":
            new_qty = st["qty"] + qty
            if new_qty > 0:
                st["avg"] = (st["avg"] * st["qty"] + price * qty) / new_qty
            st["qty"] = new_qty
        else:  # SELL
            avg = st["avg"]
            pnl_native = (price - avg) * qty - (t.fee or Decimal("0")) - (t.tax or Decimal("0"))
            # KRW 환산 (USD는 현재 환율 사용 — 과거 환율 데이터 없음)
            pnl_krw = pnl_native * rate if s.currency == "USD" else pnl_native
            buckets[bucket_key(t.executed_at)] += pnl_krw
            total += pnl_krw
            st["qty"] -= qty
            if st["qty"] <= 0:
                st["qty"] = Decimal("0")
                st["avg"] = Decimal("0")

    if period == "all":
        return {"period": "all", "total_krw": str(total), "items": []}

    # 일별/월별 — 최근 결과 위로 정렬
    cutoff = None
    if period == "daily":
        cutoff = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")
    elif period == "monthly":
        cutoff = (datetime.utcnow() - timedelta(days=365 * 3)).strftime("%Y-%m")

    items = [
        {"bucket": k, "realized_krw": str(v)}
        for k, v in sorted(buckets.items(), reverse=True)
        if cutoff is None or k >= cutoff
    ]
    return {"period": period, "total_krw": str(total), "items": items}
