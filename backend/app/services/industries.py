"""종류별 종목 카테고리.

업종/테마 기준 큐레이션 — 한국/미국/코인 종목을 같이 묶어
"종류별 종목" 화면에 노출.
"""
from __future__ import annotations

import asyncio
import time
from typing import Iterable

from loguru import logger

from ..db import SessionLocal
from ..models import Price, Symbol
from .sources import kis as _kis
from .sources import stooq as _stooq
from .sources import upbit as _upbit
from .sources.kr_seeds import KR_SEEDS
from .sources.us_seeds import US_SEEDS

# (category_key, label, [(market, code), ...])
INDUSTRY_GROUPS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "semiconductor",
        "반도체",
        [
            ("KRX", "005930"),  # 삼성전자
            ("KRX", "000660"),  # SK하이닉스
            ("KRX", "042700"),  # 한미반도체
            ("KRX", "034220"),  # LG디스플레이
            ("KRX", "009150"),  # 삼성전기
            ("KRX", "011070"),  # LG이노텍
            ("NASDAQ", "NVDA"),
            ("NASDAQ", "AMD"),
            ("NASDAQ", "INTC"),
            ("NASDAQ", "QCOM"),
            ("NASDAQ", "MU"),
            ("NASDAQ", "AVGO"),
            ("NASDAQ", "AMAT"),
            ("NASDAQ", "LRCX"),
            ("NASDAQ", "KLAC"),
            ("NASDAQ", "ASML"),
            ("NYSE", "TSM"),
            ("NASDAQ", "ARM"),
        ],
    ),
    (
        "tech_software",
        "기술/소프트웨어",
        [
            ("KRX", "035420"),  # NAVER
            ("KRX", "035720"),  # 카카오
            ("KRX", "018260"),  # 삼성SDS
            ("NASDAQ", "AAPL"),
            ("NASDAQ", "MSFT"),
            ("NASDAQ", "GOOGL"),
            ("NASDAQ", "META"),
            ("NASDAQ", "AMZN"),
            ("NYSE", "ORCL"),
            ("NYSE", "CRM"),
            ("NASDAQ", "ADBE"),
            ("NYSE", "PLTR"),
            ("NASDAQ", "NOW"),
            ("NASDAQ", "INTU"),
        ],
    ),
    (
        "auto",
        "자동차",
        [
            ("KRX", "005380"),  # 현대차
            ("KRX", "000270"),  # 기아
            ("KRX", "012330"),  # 현대모비스
            ("NASDAQ", "TSLA"),
            ("NYSE", "F"),
            ("NYSE", "GM"),
            ("NASDAQ", "RIVN"),
            ("NASDAQ", "LCID"),
            ("NYSE", "NIO"),
            ("NYSE", "XPEV"),
            ("NASDAQ", "LI"),
        ],
    ),
    (
        "pharma",
        "의약/바이오",
        [
            ("KRX", "207940"),  # 삼성바이오로직스
            ("KRX", "068270"),  # 셀트리온
            ("KRX", "128940"),  # 한미약품
            ("KRX", "000100"),  # 유한양행
            ("NYSE", "LLY"),
            ("NYSE", "UNH"),
            ("NYSE", "JNJ"),
            ("NYSE", "PFE"),
            ("NYSE", "ABBV"),
            ("NYSE", "MRK"),
            ("NYSE", "NVO"),
            ("NASDAQ", "MRNA"),
        ],
    ),
    (
        "airline",
        "항공/방산",
        [
            ("KRX", "003490"),  # 대한항공
            ("KRX", "020560"),  # 아시아나항공
            ("KRX", "180640"),  # 한진칼
            ("KRX", "012450"),  # 한화에어로스페이스
            ("KRX", "047810"),  # 한국항공우주
            ("KRX", "272210"),  # 한화시스템
            ("KRX", "079550"),  # LIG넥스원
            ("NYSE", "BA"),
            ("NYSE", "DAL"),
            ("NASDAQ", "UAL"),
            ("NASDAQ", "AAL"),
        ],
    ),
    (
        "finance",
        "금융",
        [
            ("KRX", "105560"),  # KB금융
            ("KRX", "055550"),  # 신한지주
            ("KRX", "086790"),  # 하나금융
            ("KRX", "316140"),  # 우리금융
            ("KRX", "024110"),  # 기업은행
            ("KRX", "000810"),  # 삼성화재
            ("KRX", "032830"),  # 삼성생명
            ("NYSE", "JPM"),
            ("NYSE", "BAC"),
            ("NYSE", "WFC"),
            ("NYSE", "GS"),
            ("NYSE", "MS"),
            ("NYSE", "V"),
            ("NYSE", "MA"),
            ("NYSE", "BRK-B"),
        ],
    ),
    (
        "energy",
        "에너지/소재",
        [
            ("KRX", "096770"),  # SK이노베이션
            ("KRX", "010950"),  # S-Oil
            ("KRX", "015760"),  # 한국전력
            ("KRX", "005490"),  # POSCO홀딩스
            ("KRX", "004020"),  # 현대제철
            ("KRX", "010130"),  # 고려아연
            ("NYSE", "XOM"),
            ("NYSE", "CVX"),
            ("NYSE", "COP"),
            ("NYSE", "SLB"),
            ("NYSE", "OXY"),
        ],
    ),
    (
        "consumer",
        "소비/유통",
        [
            ("KRX", "139480"),  # 이마트
            ("KRX", "097950"),  # CJ제일제당
            ("KRX", "271560"),  # 오리온
            ("KRX", "033780"),  # KT&G
            ("NYSE", "WMT"),
            ("NASDAQ", "COST"),
            ("NYSE", "HD"),
            ("NYSE", "TGT"),
            ("NYSE", "NKE"),
            ("NASDAQ", "SBUX"),
            ("NYSE", "MCD"),
            ("NYSE", "DIS"),
            ("NYSE", "KO"),
            ("NASDAQ", "PEP"),
            ("NYSE", "PG"),
        ],
    ),
    (
        "game_entertainment",
        "게임/엔터",
        [
            ("KRX", "259960"),  # 크래프톤
            ("KRX", "251270"),  # 넷마블
            ("KRX", "352820"),  # 하이브
            ("NASDAQ", "EA"),
            ("NASDAQ", "TTWO"),
            ("NASDAQ", "NFLX"),
            ("NYSE", "DIS"),
            ("NYSE", "RBLX"),
            ("NYSE", "SPOT"),
        ],
    ),
    (
        "shipbuilding",
        "조선/중공업",
        [
            ("KRX", "009540"),  # HD한국조선해양
            ("KRX", "329180"),  # HD현대중공업
            ("KRX", "010620"),  # HD현대미포
            ("KRX", "042660"),  # 한화오션
            ("KRX", "267260"),  # HD현대일렉트릭
            ("KRX", "034020"),  # 두산에너빌리티
            ("KRX", "241560"),  # 두산밥캣
            ("KRX", "000150"),  # 두산
        ],
    ),
    (
        "battery_evchem",
        "2차전지/화학",
        [
            ("KRX", "373220"),  # LG에너지솔루션
            ("KRX", "006400"),  # 삼성SDI
            ("KRX", "051910"),  # LG화학
            ("KRX", "003670"),  # 포스코퓨처엠
            ("KRX", "011170"),  # 롯데케미칼
            ("KRX", "009830"),  # 한화솔루션
        ],
    ),
    (
        "crypto",
        "코인",
        [
            ("UPBIT", "KRW-BTC"),
            ("UPBIT", "KRW-ETH"),
            ("UPBIT", "KRW-XRP"),
            ("UPBIT", "KRW-SOL"),
            ("UPBIT", "KRW-DOGE"),
            ("UPBIT", "KRW-ADA"),
            ("UPBIT", "KRW-AVAX"),
            ("UPBIT", "KRW-LINK"),
            ("UPBIT", "KRW-MATIC"),
            ("UPBIT", "KRW-DOT"),
        ],
    ),
]


# 캐시: 60s TTL
_cache: tuple[float, list[dict]] | None = None
_TTL = 60.0
_lock = asyncio.Lock()


def _all_codes() -> list[tuple[str, str]]:
    seen = set()
    out: list[tuple[str, str]] = []
    for _, _, codes in INDUSTRY_GROUPS:
        for mc in codes:
            if mc in seen:
                continue
            seen.add(mc)
            out.append(mc)
    return out


def _name_lookup() -> dict[tuple[str, str], str]:
    """(market, code) → 한글명."""
    out: dict[tuple[str, str], str] = {}
    for c, n, _, _ in KR_SEEDS:
        out[("KRX", c)] = n
    for c, n, m, _ in US_SEEDS:
        out[(m, c)] = n
    return out


async def _fetch_live_quotes(
    krx: list[str], us: list[tuple[str, str]], upbit: list[str]
) -> dict[tuple[str, str], dict]:
    """누락된 종목들에 대해 실시간 가격 batch 조회.

    KRX: Stooq KR 폴백 (가장 빠름) → KIS (있으면)
    US: Stooq → (없으면 yfinance 생략, 인기 워밍업으로 대부분 채워짐)
    UPBIT: 공식 API (빠름)
    """
    out: dict[tuple[str, str], dict] = {}

    async def _krx_path() -> None:
        if not krx:
            return
        try:
            # KIS가 설정돼 있으면 우선 시도
            if _kis._configured():
                try:
                    q = await asyncio.wait_for(_kis.fetch_prices(krx), timeout=8.0)
                    for code, info in q.items():
                        if info:
                            out[("KRX", code)] = info
                except asyncio.TimeoutError:
                    pass
            missing = [c for c in krx if ("KRX", c) not in out]
            if missing:
                q = await asyncio.wait_for(_stooq.fetch_quotes_kr(missing), timeout=10.0)
                for code, info in q.items():
                    if info:
                        out[("KRX", code)] = info
        except Exception as e:
            logger.warning("industries KRX fetch: {}", e)

    async def _us_path() -> None:
        if not us:
            return
        try:
            codes_only = [c for _, c in us]
            q = await asyncio.wait_for(_stooq.fetch_quotes(codes_only), timeout=10.0)
            mkt_by = {c: m for m, c in us}
            for code, info in q.items():
                if info:
                    out[(mkt_by.get(code, "NASDAQ"), code)] = info
        except Exception as e:
            logger.warning("industries US fetch: {}", e)

    async def _upbit_path() -> None:
        if not upbit:
            return
        try:
            q = await asyncio.wait_for(_upbit.fetch_prices(upbit), timeout=6.0)
            for code, info in q.items():
                if info:
                    out[("UPBIT", code)] = info
        except Exception as e:
            logger.warning("industries UPBIT fetch: {}", e)

    await asyncio.gather(_krx_path(), _us_path(), _upbit_path(), return_exceptions=True)
    return out


async def industries() -> list[dict]:
    """업종별 종목 + 현재가. 60s 캐시.

    1) DB Price 있으면 그 값 사용
    2) 누락된 종목은 실시간 batch 조회 후 Price DB에 upsert
    """
    global _cache
    if _cache and (time.time() - _cache[0]) < _TTL:
        return _cache[1]

    async with _lock:
        if _cache and (time.time() - _cache[0]) < _TTL:
            return _cache[1]

        db = SessionLocal()
        try:
            # Symbol + Price 조회
            sym_rows = (
                db.query(Symbol, Price)
                .outerjoin(Price, Price.symbol_id == Symbol.id)
                .filter(Symbol.is_active)
                .all()
            )
            by_mc: dict[tuple[str, str], tuple[Symbol, Price | None]] = {}
            for s, p in sym_rows:
                by_mc[(s.market, s.code)] = (s, p)

            name_by = _name_lookup()
            for s, _ in sym_rows:
                if s.market == "UPBIT":
                    name_by[(s.market, s.code)] = s.name

            # 가격 누락 종목 모으기 → 실시간 조회
            need_krx: list[str] = []
            need_us: list[tuple[str, str]] = []
            need_upbit: list[str] = []
            for _, _, group_codes in INDUSTRY_GROUPS:
                for mkt, code in group_codes:
                    sp = by_mc.get((mkt, code))
                    has_price = sp is not None and sp[1] is not None
                    if has_price:
                        continue
                    if mkt == "KRX" and code not in need_krx:
                        need_krx.append(code)
                    elif mkt in ("NASDAQ", "NYSE", "AMEX") and (mkt, code) not in need_us:
                        need_us.append((mkt, code))
                    elif mkt == "UPBIT" and code not in need_upbit:
                        need_upbit.append(code)
        finally:
            db.close()

        live = await _fetch_live_quotes(need_krx, need_us, need_upbit)

        # 새로 받은 가격을 Price DB에 upsert
        if live:
            db = SessionLocal()
            try:
                from datetime import datetime as _dt
                from decimal import Decimal as _Dec
                for (mkt, code), info in live.items():
                    sym = (
                        db.query(Symbol)
                        .filter(Symbol.market == mkt, Symbol.code == code)
                        .first()
                    )
                    if not sym:
                        # Symbol이 없으면 시드에서 이름 찾아 등록
                        name = _name_lookup().get((mkt, code), code)
                        asset_type = "CRYPTO" if mkt == "UPBIT" else "STOCK"
                        currency = "USD" if mkt in ("NASDAQ", "NYSE", "AMEX") else "KRW"
                        sym = Symbol(
                            code=code, name=name, market=mkt,
                            asset_type=asset_type, currency=currency,
                            is_active=True,
                        )
                        db.add(sym)
                        try:
                            db.flush()
                        except Exception:
                            db.rollback()
                            continue
                    try:
                        price_val = _Dec(str(info["price"]))
                        prev_val = (
                            _Dec(str(info["prev_close"]))
                            if info.get("prev_close")
                            else None
                        )
                    except Exception:
                        continue
                    existing = db.get(Price, sym.id)
                    if existing:
                        existing.price = price_val
                        existing.prev_close = prev_val
                        existing.ts = _dt.utcnow()
                    else:
                        db.add(Price(
                            symbol_id=sym.id, price=price_val,
                            prev_close=prev_val, ts=_dt.utcnow(),
                        ))
                try:
                    db.commit()
                except Exception as e:
                    logger.warning("industries price upsert: {}", e)
                    db.rollback()
            finally:
                db.close()

        # 다시 읽어서 응답 만들기
        db = SessionLocal()
        try:
            sym_rows = (
                db.query(Symbol, Price)
                .outerjoin(Price, Price.symbol_id == Symbol.id)
                .filter(Symbol.is_active)
                .all()
            )
            by_mc = {(s.market, s.code): (s, p) for s, p in sym_rows}
            name_by = _name_lookup()
            for s, _ in sym_rows:
                if s.market == "UPBIT":
                    name_by[(s.market, s.code)] = s.name

            out: list[dict] = []
            for key, label, group_codes in INDUSTRY_GROUPS:
                items: list[dict] = []
                for mkt, code in group_codes:
                    sp = by_mc.get((mkt, code))
                    name = name_by.get((mkt, code), code)
                    if sp:
                        s, p = sp
                        price = float(p.price) if p else None
                        prev = float(p.prev_close) if (p and p.prev_close) else None
                        change_pct = (
                            ((price - prev) / prev * 100)
                            if (price is not None and prev)
                            else None
                        )
                        items.append({
                            "symbol_id": s.id,
                            "market": s.market,
                            "code": s.code,
                            "name": s.name or name,
                            "currency": s.currency,
                            "price": price,
                            "change_pct": change_pct,
                        })
                    else:
                        items.append({
                            "symbol_id": None,
                            "market": mkt,
                            "code": code,
                            "name": name,
                            "currency": "KRW" if mkt in ("KRX", "UPBIT") else "USD",
                            "price": None,
                            "change_pct": None,
                        })
                out.append({"key": key, "label": label, "items": items})
        finally:
            db.close()

        if any(g["items"] for g in out):
            _cache = (time.time(), out)
        return out
