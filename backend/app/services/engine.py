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

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from ..db import lock_for_update
from ..models import CashLedger, Holding, Order, Price, Symbol, Trade, User
from .fees import FX_SPREAD, calc_cost, quantize_money
from .fx import get_usdkrw
from .market_calendar import is_market_open
from .sources import kis, toss, upbit

ZERO = Decimal("0")

# 체결용 실시간 시세 캐시 유지 시간(초)
EXEC_QUOTE_TTL = 3.0
# MONEY = Numeric(20, 8) → 정수부 12자리. 넘으면 quantize에서 InvalidOperation.
MAX_QTY = Decimal("1000000000")            # 10억 주/개
MAX_NOTIONAL = Decimal("100000000000")     # 주문 금액 1천억 (해당 통화)


class OrderError(Exception):
    pass


def _currency(market: str) -> str:
    if market in ("NASDAQ", "NYSE"):
        return "USD"
    return "KRW"


# 체결용 실시간 시세 캐시: (market, code) → (monotonic ts, price). 체결기가 1초마다 같은 종목을 묻는 것을 흡수.
_exec_quotes: dict[tuple[str, str], tuple[float, Decimal]] = {}


async def _realtime_price(market: str, code: str) -> Decimal | None:
    """실시간 소스만 조회. 일봉/종가 폴백(pykrx·Stooq·yfinance)은 쓰지 않는다."""
    if market == "UPBIT":
        q = (await upbit.fetch_prices([code])).get(code)
        return q["price"] if q else None
    if market == "KRX":
        p = (await toss._fetch_last_prices([code])).get(code)
        if p is None:
            q = await kis.fetch_price(code)
            p = q["price"] if q else None
        return p
    if market in ("NASDAQ", "NYSE", "AMEX"):
        p = (await toss._fetch_last_prices([code])).get(code)
        if p is None:
            q = await kis.fetch_overseas_price(code, market)
            p = q["price"] if q else None
        return p
    return None


async def _current_price(sym: Symbol, db: Session | None = None) -> Decimal | None:
    """체결용 현재가 (실시간 소스, 최대 EXEC_QUOTE_TTL초 캐시). 못 받으면 None → 체결하지 않는다.

    DB prices 테이블은 쓰지 않는다: 인기목록·업종 화면이 일봉 폴백 값도 ts=now로 저장해
    시각만으로는 실시간 시세인지 알 수 없다.
    """
    key = (sym.market, sym.code)
    now = time.monotonic()
    cached = _exec_quotes.get(key)
    if cached and now - cached[0] <= EXEC_QUOTE_TTL:
        return cached[1]
    try:
        price = await asyncio.wait_for(_realtime_price(sym.market, sym.code), timeout=5)
    except Exception as e:
        logger.warning("realtime quote failed {}/{}: {}", sym.market, sym.code, e)
        return None
    if price is None:
        return None
    price = Decimal(str(price))
    if price <= 0:
        return None
    _exec_quotes[key] = (now, price)
    return price


# --- 매수여력 검증 ----------------------------------------------------

def _pending_price(db: Session, o: Order) -> Decimal | None:
    """미체결 주문의 예상 체결가 (지정가 우선, 없으면 최신가 캐시)."""
    if o.limit_price:
        return o.limit_price
    p = db.get(Price, o.symbol_id)
    return p.price if p and p.price else None


def _reserved_by_currency(db: Session, user: User) -> tuple[Decimal, Decimal]:
    """미체결(PENDING) 매수 주문이 예약한 금액을 통화별(KRW, USD)로 합산."""
    reserved_krw = ZERO
    reserved_usd = ZERO
    pend = (
        db.query(Order)
        .filter(
            Order.user_id == user.id,
            Order.side == "BUY",
            Order.status == "PENDING",
        )
        .all()
    )
    for o in pend:
        ps = db.get(Symbol, o.symbol_id)
        if not ps:
            continue
        pp = _pending_price(db, o)
        if pp is None:
            continue
        cost = calc_cost(market=ps.market, side="BUY", price=pp, qty=o.qty).net
        if _currency(ps.market) == "USD":
            reserved_usd += cost
        else:
            reserved_krw += cost
    return reserved_krw, reserved_usd


def _check_buying_power(
    db: Session,
    *,
    user: User,
    sym: Symbol,
    qty: Decimal,
    price: Decimal | None,
    rate: Decimal,
) -> None:
    """매수 주문이 가용 잔액(미체결 예약분 제외)을 초과하면 즉시 거절. 호출 전 lock_for_update 필수.

    결제 로직(_fill)과 동일한 기준:
    - KRW 종목: cash_krw
    - USD 종목: cash_usd 우선, 부족분은 cash_krw에서 환전(스프레드 1%)
    USD 대기 주문이 cash_usd를 넘는 만큼은 나중에 원화를 환전해 쓰므로 원화 예약으로 함께 잡는다
    (그렇지 않으면 같은 원화가 원화 주문과 해외 주문에 동시에 잡힌다).
    가격을 알 수 없으면(시세 미상) 검증을 건너뛰고 체결 시점 검증에 위임.
    """
    if price is None or price <= 0:
        return

    est = calc_cost(market=sym.market, side="BUY", price=price, qty=qty).net
    need_krw, need_usd = _reserved_by_currency(db, user)
    currency = _currency(sym.market)
    if currency == "USD":
        need_usd += est
    else:
        need_krw += est

    usd_short = need_usd - user.cash_usd
    krw_for_fx = (
        quantize_money(usd_short * rate * (Decimal("1") + FX_SPREAD)) if usd_short > 0 else ZERO
    )
    if need_krw + krw_for_fx > user.cash_krw:
        raise OrderError("insufficient KRW for FX" if currency == "USD" and usd_short > 0
                         else "insufficient cash")


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
    # 프론트가 next_open(오프셋 포함 ISO)을 보내면 tz-aware datetime이 된다.
    # naive datetime.utcnow()와 비교하면 TypeError → HTTP 500 → naive UTC로 정규화.
    if scheduled_at is not None and scheduled_at.tzinfo is not None:
        scheduled_at = scheduled_at.astimezone(timezone.utc).replace(tzinfo=None)
    if order_type == "SCHEDULED" and scheduled_at <= datetime.utcnow():
        raise OrderError("scheduled_at must be in the future")

    if qty > MAX_QTY or (limit_price is not None and limit_price > MAX_NOTIONAL):
        raise OrderError("order too large")

    sym = db.get(Symbol, symbol_id)
    if not sym or not sym.is_active:
        raise OrderError("symbol not found")

    # 네트워크 호출(시세·환율)은 잠그기 전에 끝낸다
    if order_type == "LIMIT":
        est_price = limit_price
    else:
        est_price = await _current_price(sym, db)
    if est_price is not None and est_price * qty > MAX_NOTIONAL:
        raise OrderError("order too large")
    rate = await get_usdkrw()

    # 검증~주문 저장을 한 쓰기 잠금 안에서: 동시에 들어온 주문이 같은 잔액/보유를 함께 통과하지 못하게
    lock_for_update(db, user.id)

    # 매도는 보유 검증 (이미 걸린 매도 대기 수량 제외)
    if side == "SELL":
        h = (
            db.query(Holding)
            .filter(Holding.user_id == user.id, Holding.symbol_id == symbol_id)
            .first()
        )
        pending_sell = (
            db.query(func.coalesce(func.sum(Order.qty), 0))
            .filter(Order.user_id == user.id, Order.symbol_id == symbol_id,
                    Order.side == "SELL", Order.status == "PENDING")
            .scalar()
        )
        if not h or h.qty - Decimal(str(pending_sell)) < qty:
            db.rollback()
            raise OrderError("insufficient holding")
    else:  # BUY — 주문 시점에 잔액(미체결 예약분 포함) 검증: 보유 금액 이상 주문 방지
        try:
            _check_buying_power(db, user=user, sym=sym, qty=qty, price=est_price, rate=rate)
        except OrderError:
            db.rollback()
            raise

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
        db.refresh(order)

    return order


# --- 체결 ------------------------------------------------------------

async def _try_execute_market(db: Session, order: Order) -> None:
    """시장가 즉시 체결. 마감 중이면 그대로 PENDING 유지 → 다음 개장 시 매처가 시가에 체결."""
    sym = db.get(Symbol, order.symbol_id)
    if not is_market_open(sym.market):
        return  # 다음 개장 시 매처가 처리
    price = await _current_price(sym, db)
    if price is None:
        db.execute(
            update(Order).where(Order.id == order.id, Order.status == "PENDING")
            .values(status="REJECTED", reject_reason="no price")
        )
        db.commit()
        return
    rate = await get_usdkrw() if _currency(sym.market) == "USD" else None
    _fill(db, order.id, price, rate)


def _fill(db: Session, order_id: int, fill_price: Decimal, rate: Decimal | None) -> bool:
    """전량 체결 + 자산/현금 정산. 체결했으면 True.

    먼저 PENDING → FILLED 조건부 UPDATE로 주문을 선점한다. 이 UPDATE가 SQLite 쓰기 잠금을 잡으므로
    commit까지 API·체결기의 다른 체결/취소/잔고 변경이 끼어들 수 없다.
    이미 체결·취소된 주문이면 아무것도 하지 않는다. 네트워크 호출(환율)은 호출자가 미리 끝낸다.
    """
    claimed = db.execute(
        update(Order).where(Order.id == order_id, Order.status == "PENDING")
        .values(status="FILLED")
    ).rowcount
    if not claimed:
        db.rollback()
        return False
    db.expire_all()  # 잠금 이후의 최신 잔고·보유를 다시 읽는다
    order = db.get(Order, order_id)
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
                krw_needed = quantize_money(shortfall_usd * rate * (Decimal("1") + Decimal("0.01")))
                if user.cash_krw < krw_needed:
                    order.status = "REJECTED"
                    order.reject_reason = "insufficient KRW for FX"
                    db.commit()
                    return False
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
                return False
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
            return False
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
    return True


# --- 매처 (Worker 1초 틱) ------------------------------------------

async def match_pending_orders(db: Session) -> int:
    """대기 중 주문 처리.

    - PENDING MARKET: 장이 열렸으면 현재가에 체결 (장 마감 중 들어온 시장가 → 개장 시 시가)
    - PENDING LIMIT: 가격 조건 충족 시 현재가에 체결 (매수는 지정가 이하, 매도는 지정가 이상)
    - PENDING SCHEDULED: scheduled_at 도래 시 시장가로 전환
    주문 하나의 오류가 회차 전체를 멈추지 않도록 주문별로 격리한다.
    """
    pending = db.query(Order).filter(Order.status == "PENDING").all()
    filled = 0
    for o in pending:
        try:
            if await _match_one(db, o):
                filled += 1
        except Exception as e:
            db.rollback()
            logger.exception("matcher order {} error: {}", o.id, e)
            if isinstance(e, ArithmeticError):
                # 계산 자체가 불가능한 주문(자릿수 초과 등)은 다음 틱에도 똑같이 실패 → 거절 처리
                db.execute(
                    update(Order).where(Order.id == o.id, Order.status == "PENDING")
                    .values(status="REJECTED", reject_reason="calculation error")
                )
                db.commit()
    return filled


async def _match_one(db: Session, o: Order) -> bool:
    sym = db.get(Symbol, o.symbol_id)
    if not sym:
        return False
    if o.order_type == "SCHEDULED" and not (o.scheduled_at and o.scheduled_at <= datetime.utcnow()):
        return False
    if not is_market_open(sym.market):
        return False
    price = await _current_price(sym, db)
    if price is None:
        return False
    if o.order_type == "LIMIT" and not (
        (o.side == "BUY" and price <= o.limit_price)
        or (o.side == "SELL" and price >= o.limit_price)
    ):
        return False
    rate = await get_usdkrw() if _currency(sym.market) == "USD" else None
    return _fill(db, o.id, price, rate)


def cancel_order(db: Session, *, user: User, order_id: int) -> Order:
    o = db.get(Order, order_id)
    if not o or o.user_id != user.id:
        raise OrderError("order not found")
    # 조건부 UPDATE: 체결기가 먼저 체결했으면 취소되지 않는다 (취소한 주문이 체결되는 경합 방지)
    n = db.execute(
        update(Order).where(Order.id == order_id, Order.status == "PENDING")
        .values(status="CANCELLED")
    ).rowcount
    db.commit()
    db.refresh(o)
    if not n:
        raise OrderError(f"cannot cancel: status={o.status}")
    return o
