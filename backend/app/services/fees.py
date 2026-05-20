"""수수료·세금 계산.

한국 주식:
  매수 수수료 0.015%
  매도 수수료 0.015% + 거래세 0.18% (코스피 기준, 코스닥은 0.18% 동일로 단순화)
미국 주식/ETF:
  매수/매도 수수료 0.25%
  환전 스프레드 1% (KRW↔USD 환산 시)
  ※ 양도세는 실현이익 시점에 별도 표기만 (체결 시점 차감 X) — Stage 4 리포팅에서 처리
코인 (UPBIT 원화마켓):
  매수/매도 0.05%
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# 수수료/세율
FEE_KR_STOCK = Decimal("0.00015")     # 0.015%
TAX_KR_SELL = Decimal("0.0018")       # 0.18%
FEE_US_STOCK = Decimal("0.0025")      # 0.25%
FX_SPREAD = Decimal("0.01")           # 1%
FEE_CRYPTO = Decimal("0.0005")        # 0.05%


@dataclass
class CostBreakdown:
    gross: Decimal     # 체결가 × 수량 (해당 통화)
    fee: Decimal
    tax: Decimal
    net: Decimal       # 매수: gross + fee + tax (출금액) / 매도: gross - fee - tax (수령액)


def quantize_money(d: Decimal, places: int = 8) -> Decimal:
    """소수점 자릿수 표준화."""
    q = Decimal(10) ** -places
    return d.quantize(q)


def calc_cost(*, market: str, side: str, price: Decimal, qty: Decimal) -> CostBreakdown:
    """체결 1건의 비용 계산.

    market: KRX / NASDAQ / NYSE / UPBIT
    side: BUY / SELL
    가격 통화는 호출자가 알고 있다고 가정 (KRX→KRW, US→USD, UPBIT→KRW).
    """
    gross = price * qty
    fee = Decimal("0")
    tax = Decimal("0")

    if market == "KRX":
        fee = gross * FEE_KR_STOCK
        if side == "SELL":
            tax = gross * TAX_KR_SELL
    elif market in ("NASDAQ", "NYSE"):
        fee = gross * FEE_US_STOCK
    elif market == "UPBIT":
        fee = gross * FEE_CRYPTO

    fee = quantize_money(fee)
    tax = quantize_money(tax)

    if side == "BUY":
        net = gross + fee + tax
    else:
        net = gross - fee - tax

    return CostBreakdown(
        gross=quantize_money(gross),
        fee=fee,
        tax=tax,
        net=quantize_money(net),
    )


def fx_buy_usd(krw_amount: Decimal, usd_per_krw: Decimal) -> Decimal:
    """KRW로 USD를 사는 환산 (스프레드 1% 불리하게)."""
    effective_rate = usd_per_krw * (Decimal("1") + FX_SPREAD)
    return quantize_money(krw_amount / effective_rate)


def fx_sell_usd(usd_amount: Decimal, krw_per_usd: Decimal) -> Decimal:
    """USD를 KRW로 바꾸는 환산 (스프레드 1% 불리하게)."""
    effective_rate = krw_per_usd * (Decimal("1") - FX_SPREAD)
    return quantize_money(usd_amount * effective_rate)
