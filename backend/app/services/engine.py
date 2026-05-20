"""거래 엔진.

place_order: 주문 생성 + 시장가는 즉시 체결 시도
execute_market_order: 시장가 체결 (현재가 기준)
match_limit_orders: 지정가 대기열 매칭 (Worker 1초 틱)
trigger_scheduled_orders: 예약 주문 트리거 (Worker 1초 틱)

결제 통화:
- KRX/UPBIT: KRW
- NASDAQ/NYSE: USD (cash_usd 우선, 부족하면 KRW에서 환전)
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from ..models import CashLedger, Holding, Order, Price, Symbol, Trade, User
from .fees import calc_cost, fx_buy_usd, fx_sell_usd, quantize_money
from .fx import get_usdkrw
from .market_calendar import is_market_open
from .quotes import fetch_one, get_quote

ZERO = Decimal("0")


class OrderError(Exception):
    pass


def _currency(market: str) -> str:
    if market in ("NASDAQ", "NYSE"):
        return "USD"
    return "KRW"


async def _current_price(sym: Symbol, db: Session) -> Decimal | None:
    p = db.get(Price, sym.id)
    if p and p.price:
        return p.price
    q = await get_quote(sym.market, sym.code)
    if q:
        return q["price"]
    return None


# --- 주문 생성 -------------------------------------------------------

async def place_order(
    db: Session,
    *,
    user: User,
    symbol_id: int,
    side: str,
    order_type: str,
    qty: Decimal,
    limit_price: Decimal | None = None,
    scheduled_at: datetime | None = None,
) -> Order:
    side = side.upper()
    order_type = order_type.upper()
    if side not in ("BUY", "SELL"):
        raise OrderError("side must be BUY or SELL")
    if order_type not in ("MARKET", "LIMIT", "SCHEDULED"):
        raise OrderError("invalid order_type")
    if qty <= 0:
        raise OrderError("qty must be positive")
    if order_type == "LIMIT" and (not limit_price or limit_price <= 0):
        raise OrderError("limit_price required for LIMIT")
    if order_type == "SCHEDULED" and not scheduled_at:
        raise OrderError("scheduled_at required for SCHEDULED")

    sym = db.get(Symbol, symbol_id)
    if not sym or not sym.is_active:
        raise OrderError("symbol not found")

    # 매도는 보유 검증
    if side == "SELL":
        h = (
            db.query(Holding)
            .filter(Holding.user_id == user.id, Holding.symbol_id == symbol_id)
            .first()
        )
        if not h or h.qty < qty:
            raise OrderError("insufficient holding")

    order = Order(
        user_id=user.id,
        symbol_id=symbol_id,
        side=side,
        order_type=order_type,
        qty=qty,
        limit_price=limit_price,
        scheduled_at=scheduled_at,
        status="PENDING",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # 시장가는 즉시 시도 (장 중이면)
    if order_type == "MARKET":
        await _try_execute_market(db, order)

    return order


# --- 체결 ------------------------------------------------------------

async def _try_execute_market(db: Session, order: Order) -> None:
    """시장가 즉시 체결. 마감 중이면 그대로 PENDING 유지 → 다음 개장 시 매처가 시가에 체결."""
    sym = db.get(Symbol, order.symbol_id)
    if not is_market_open(sym.market):
        return  # 다음 개장 시 매처가 처리
    price = await _current_price(sym, db)
    if price is None:
        order.status = "REJECTED"
        order.reject_reason = "no price"
        db.commit()
        return
    await _fill(db, order, price)


async def _fill(db: Session, order: Order, fill_price: Decimal) -> None:
    """전량 체결 + 자산/현금 정산."""
    sym = db.get(Symbol, order.symbol_id)
    user = db.get(User, order.user_id)
    cost = calc_cost(market=sym.market, side=order.side, price=fill_price, qty=order.qty)

    currency = _currency(sym.market)

    if order.side == "BUY":
        # 결제: KRW 또는 USD
        need = cost.net
        if currency == "USD":
            if user.cash_usd >= need:
                user.cash_usd = quantize_money(user.cash_usd - need)
            else:
                # 부족분은 KRW에서 환전
                shortfall_usd = need - user.cash_usd
                rate = await get_usdkrw()
                krw_needed = quantize_money(shortfall_usd * rate * (Decimal("1") + Decimal("0.01")))
                if user.cash_krw < krw_needed:
                    order.status = "REJECTED"
                    order.reject_reason = "insufficient KRW for FX"
                    db.commit()
                    return
                user.cash_krw = quantize_money(user.cash_krw - krw_needed)
                user.cash_usd = ZERO
                # 환전 원장
                db.add(
                    CashLedger(
                        user_id=user.id,
                        currency="KRW",
                        amount=-krw_needed,
                        reason="FX",
                        ref_id=order.id,
                        memo=f"USD 매수 환전 {shortfall_usd}",
                    )
                )
                db.add(
                    CashLedger(
                        user_id=user.id,
                        currency="USD",
                        amount=shortfall_usd,
                        reason="FX",
                        ref_id=order.id,
                    )
                )
            db.add(
                CashLedger(
                    user_id=user.id,
                    currency="USD",
                    amount=-need,
                    reason="TRADE",
                    ref_id=order.id,
                )
            )
        else:  # KRW
            if user.cash_krw < need:
                order.status = "REJECTED"
                order.reject_reason = "insufficient cash"
                db.commit()
                return
            user.cash_krw = quantize_money(user.cash_krw - need)
            db.add(
                CashLedger(
                    user_id=user.id,
                    currency="KRW",
                    amount=-need,
                    reason="TRADE",
                    ref_id=order.id,
                )
            )

        # 보유 증가
        h = (
            db.query(Holding)
            .filter(Holding.user_id == user.id, Holding.symbol_id == order.symbol_id)
            .first()
        )
        if h:
            new_qty = h.qty + order.qty
            # 평단가 가중평균
            new_avg = (h.avg_cost * h.qty + fill_price * order.qty) / new_qty
            h.qty = new_qty
            h.avg_cost = quantize_money(new_avg)
        else:
            db.add(
                Holding(
                    user_id=user.id,
                    symbol_id=order.symbol_id,
                    qty=order.qty,
                    avg_cost=quantize_money(fill_price),
                )
            )

    else:  # SELL
        h = (
            db.query(Holding)
            .filter(Holding.user_id == user.id, Holding.symbol_id == order.symbol_id)
            .first()
        )
        if not h or h.qty < order.qty:
            order.status = "REJECTED"
            order.reject_reason = "insufficient holding"
            db.commit()
            return
        h.qty -= order.qty
        if h.qty == 0:
            db.delete(h)

        # 현금 수령
        recv = cost.net
        if currency == "USD":
            user.cash_usd = quantize_money(user.cash_usd + recv)
        else:
            user.cash_krw = quantize_money(user.cash_krw + recv)
        db.add(
            CashLedger(
                user_id=user.id,
                currency=currency,
                amount=recv,
                reason="TRADE",
                ref_id=order.id,
            )
        )

    # 체결 기록
    db.add(
        Trade(
            order_id=order.id,
            price=quantize_money(fill_price),
            qty=order.qty,
            fee=cost.fee,
            tax=cost.tax,
        )
    )
    order.status = "FILLED"
    order.filled_qty = order.qty
    order.avg_fill_price = quantize_money(fill_price)
    db.commit()
    logger.info(
        "order {} FILLED {} {} {} @ {}",
        order.id,
        order.side,
        order.qty,
        sym.code,
        fill_price,
    )


# --- 매처 (Worker 1초 틱) ------------------------------------------

async def match_pending_orders(db: Session) -> int:
    """대기 중 주문 처리.

    - PENDING MARKET: 장이 열렸으면 현재가에 체결 (장 마감 중 들어온 시장가 → 개장 시 시가)
    - PENDING LIMIT: 가격 조건 충족 시 체결
    - PENDING SCHEDULED: scheduled_at 도래 시 시장가로 전환
    """
    pending = db.query(Order).filter(Order.status == "PENDING").all()
    filled = 0
    now = datetime.utcnow()
    for o in pending:
        sym = db.get(Symbol, o.symbol_id)
        if not sym:
            continue

        if o.order_type == "SCHEDULED":
            if o.scheduled_at and o.scheduled_at <= now:
                # 시장가로 전환 후 체결 시도
                if not is_market_open(sym.market):
                    continue
                price = await _current_price(sym, db)
                if price:
                    await _fill(db, o, price)
                    filled += 1
            continue

        if not is_market_open(sym.market):
            continue

        price = await _current_price(sym, db)
        if price is None:
            continue

        if o.order_type == "MARKET":
            await _fill(db, o, price)
            filled += 1
        elif o.order_type == "LIMIT":
            # BUY: 현재가 ≤ 지정가, SELL: 현재가 ≥ 지정가
            if (o.side == "BUY" and price <= o.limit_price) or (
                o.side == "SELL" and price >= o.limit_price
            ):
                # 지정가 주문은 지정가에 체결 (보수적 가정)
                await _fill(db, o, o.limit_price)
                filled += 1
    return filled


def cancel_order(db: Session, *, user: User, order_id: int) -> Order:
    o = db.get(Order, order_id)
    if not o or o.user_id != user.id:
        raise OrderError("order not found")
    if o.status != "PENDING":
        raise OrderError(f"cannot cancel: status={o.status}")
    o.status = "CANCELLED"
    db.commit()
    return o
