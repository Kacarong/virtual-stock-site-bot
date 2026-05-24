"""DB 모델 — 전체 스키마 (Stage 1에서 모두 생성, 사용은 단계별로 늘림)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# 금액/수량은 Decimal(20,8) — 코인 소수점 대응
MONEY = Numeric(20, 8)


class User(Base):
    """사용자 = Discord 계정."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    cash_krw: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    cash_usd: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    holdings: Mapped[list[Holding]] = relationship(back_populates="user", cascade="all, delete-orphan")
    orders: Mapped[list[Order]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Symbol(Base):
    """거래 가능한 종목 마스터."""

    __tablename__ = "symbols"
    __table_args__ = (UniqueConstraint("market", "code", name="uq_market_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), index=True)  # 005930, AAPL, KRW-BTC
    name: Mapped[str] = mapped_column(String(200))
    market: Mapped[str] = mapped_column(String(16), index=True)  # KRX / NASDAQ / NYSE / UPBIT
    asset_type: Mapped[str] = mapped_column(String(16))  # STOCK / ETF / CRYPTO
    currency: Mapped[str] = mapped_column(String(8))  # KRW / USD
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Price(Base):
    """최신가 캐시 (심볼당 1행 upsert)."""

    __tablename__ = "prices"

    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), primary_key=True)
    price: Mapped[Decimal] = mapped_column(MONEY)
    prev_close: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class Watchlist(Base):
    """관심종목."""

    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "symbol_id", name="uq_watch_user_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Holding(Base):
    """보유 종목."""

    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("user_id", "symbol_id", name="uq_holding_user_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), index=True)
    qty: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    avg_cost: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))  # 매수단가 (해당 통화)

    user: Mapped[User] = relationship(back_populates="holdings")
    symbol: Mapped[Symbol] = relationship()


class Order(Base):
    """주문."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id"), index=True)

    side: Mapped[str] = mapped_column(String(8))   # BUY / SELL
    order_type: Mapped[str] = mapped_column(String(16))  # MARKET / LIMIT / SCHEDULED
    qty: Mapped[Decimal] = mapped_column(MONEY)
    limit_price: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), default="PENDING", index=True
    )  # PENDING / FILLED / PARTIAL / CANCELLED / REJECTED
    filled_qty: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    avg_fill_price: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="orders")
    symbol: Mapped[Symbol] = relationship()
    trades: Mapped[list[Trade]] = relationship(back_populates="order", cascade="all, delete-orphan")


class Trade(Base):
    """체결 (주문 1건이 여러 체결로 나뉠 수 있음)."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    price: Mapped[Decimal] = mapped_column(MONEY)
    qty: Mapped[Decimal] = mapped_column(MONEY)
    fee: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    executed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    order: Mapped[Order] = relationship(back_populates="trades")


class CashLedger(Base):
    """현금 입출금 원장 (가입지급/체결결제/관리자조정 등 모두 기록)."""

    __tablename__ = "cash_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    currency: Mapped[str] = mapped_column(String(8))  # KRW / USD
    amount: Mapped[Decimal] = mapped_column(MONEY)  # 양수=입금, 음수=출금
    reason: Mapped[str] = mapped_column(String(32))  # INITIAL / TRADE / ADMIN / FEE / TAX / FX
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # order_id 등
    memo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class MarketCalendar(Base):
    """시장별 영업일/장 운영시간."""

    __tablename__ = "market_calendar"
    __table_args__ = (UniqueConstraint("market", "date", name="uq_cal_market_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    open_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM (해당시장 로컬)
    close_time: Mapped[str | None] = mapped_column(String(5), nullable=True)


Index("ix_price_ts", Price.ts)
Index("ix_order_status_type", Order.status, Order.order_type)
# 검색·자동분류에서 자주 쓰임 (is_active 필터링)
Index("ix_symbol_active_market", Symbol.is_active, Symbol.market)
# 사용자별 주문 시간순 조회
Index("ix_order_user_created", Order.user_id, Order.created_at)
# 주문 매칭 루프에서 PENDING 후보 빠르게
Index("ix_order_symbol_status", Order.symbol_id, Order.status)
