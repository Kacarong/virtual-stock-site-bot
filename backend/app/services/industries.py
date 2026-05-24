"""종류별 종목 카테고리.

업종/테마 기준 — 큐레이션된 시드 + DB의 모든 활성 종목 이름 키워드로
자동 분류해 카테고리에 흡수.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime as _dt
from decimal import Decimal as _Dec

from loguru import logger

from ..db import SessionLocal
from ..models import Price, Symbol
from .sources import kis as _kis
from .sources import stooq as _stooq
from .sources import upbit as _upbit
from .sources.kr_seeds import KR_SEEDS
from .sources.us_seeds import US_SEEDS


async def _fetch_yf_quotes(codes: list[str]) -> dict[str, dict]:
    """yfinance fast_info로 종목별 현재가/전일종가 일괄 조회.

    스레드풀에서 병렬 실행. 코드 형식:
    - 미국: AAPL, NVDA …
    - 한국: 005930.KS (KOSPI) / 005930.KQ (KOSDAQ)
    """
    if not codes:
        return {}
    # 너무 많으면 yfinance가 느려져 30초 timeout에 잘림 → 상한 적용
    if len(codes) > 60:
        codes = codes[:60]
    from concurrent.futures import ThreadPoolExecutor

    def _one(code: str) -> tuple[str, dict | None]:
        try:
            import yfinance as yf  # type: ignore

            t = yf.Ticker(code)
            fi = t.fast_info
            price = float(fi.last_price or 0)
            prev = float(fi.previous_close or 0)
            if price <= 0:
                return code, None
            return code, {
                "price": _Dec(str(price)),
                "prev_close": _Dec(str(prev)) if prev > 0 else None,
            }
        except Exception:
            return code, None

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=20) as ex:
        tasks = [loop.run_in_executor(ex, _one, c) for c in codes]
        results = await asyncio.gather(*tasks)
    out: dict[str, dict] = {}
    for code, info in results:
        if info:
            out[code] = info
    return out

# (category_key, label, [(market, code), ...])  — 큐레이션 시드 (확정 매핑)
INDUSTRY_GROUPS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "semiconductor",
        "반도체",
        [
            ("KRX", "005930"), ("KRX", "000660"), ("KRX", "042700"),
            ("KRX", "034220"), ("KRX", "009150"), ("KRX", "011070"),
            ("NASDAQ", "NVDA"), ("NASDAQ", "AMD"), ("NASDAQ", "INTC"),
            ("NASDAQ", "QCOM"), ("NASDAQ", "MU"), ("NASDAQ", "AVGO"),
            ("NASDAQ", "AMAT"), ("NASDAQ", "LRCX"), ("NASDAQ", "KLAC"),
            ("NASDAQ", "ASML"), ("NYSE", "TSM"), ("NASDAQ", "ARM"),
        ],
    ),
    (
        "tech_software",
        "기술/소프트웨어",
        [
            ("KRX", "035420"), ("KRX", "035720"), ("KRX", "018260"),
            ("NASDAQ", "AAPL"), ("NASDAQ", "MSFT"), ("NASDAQ", "GOOGL"),
            ("NASDAQ", "META"), ("NASDAQ", "AMZN"), ("NYSE", "ORCL"),
            ("NYSE", "CRM"), ("NASDAQ", "ADBE"), ("NYSE", "PLTR"),
            ("NASDAQ", "NOW"), ("NASDAQ", "INTU"),
        ],
    ),
    (
        "auto",
        "자동차",
        [
            ("KRX", "005380"), ("KRX", "000270"), ("KRX", "012330"),
            ("NASDAQ", "TSLA"), ("NYSE", "F"), ("NYSE", "GM"),
            ("NASDAQ", "RIVN"), ("NASDAQ", "LCID"), ("NYSE", "NIO"),
            ("NYSE", "XPEV"), ("NASDAQ", "LI"),
        ],
    ),
    (
        "pharma",
        "의약/바이오",
        [
            ("KRX", "207940"), ("KRX", "068270"), ("KRX", "128940"),
            ("KRX", "000100"),
            ("NYSE", "LLY"), ("NYSE", "UNH"), ("NYSE", "JNJ"),
            ("NYSE", "PFE"), ("NYSE", "ABBV"), ("NYSE", "MRK"),
            ("NYSE", "NVO"), ("NASDAQ", "MRNA"),
        ],
    ),
    (
        "airline",
        "항공/방산",
        [
            ("KRX", "003490"), ("KRX", "020560"), ("KRX", "180640"),
            ("KRX", "012450"), ("KRX", "047810"), ("KRX", "272210"),
            ("KRX", "079550"),
            ("NYSE", "BA"), ("NYSE", "DAL"), ("NASDAQ", "UAL"),
            ("NASDAQ", "AAL"),
        ],
    ),
    (
        "finance",
        "금융",
        [
            ("KRX", "105560"), ("KRX", "055550"), ("KRX", "086790"),
            ("KRX", "316140"), ("KRX", "024110"), ("KRX", "000810"),
            ("KRX", "032830"),
            ("NYSE", "JPM"), ("NYSE", "BAC"), ("NYSE", "WFC"),
            ("NYSE", "GS"), ("NYSE", "MS"), ("NYSE", "V"),
            ("NYSE", "MA"), ("NYSE", "BRK-B"),
        ],
    ),
    (
        "energy",
        "에너지/소재",
        [
            ("KRX", "096770"), ("KRX", "010950"), ("KRX", "015760"),
            ("KRX", "005490"), ("KRX", "004020"), ("KRX", "010130"),
            ("NYSE", "XOM"), ("NYSE", "CVX"), ("NYSE", "COP"),
            ("NYSE", "SLB"), ("NYSE", "OXY"),
        ],
    ),
    (
        "consumer",
        "소비/유통",
        [
            ("KRX", "139480"), ("KRX", "097950"), ("KRX", "271560"),
            ("KRX", "033780"),
            ("NYSE", "WMT"), ("NASDAQ", "COST"), ("NYSE", "HD"),
            ("NYSE", "TGT"), ("NYSE", "NKE"), ("NASDAQ", "SBUX"),
            ("NYSE", "MCD"), ("NYSE", "DIS"), ("NYSE", "KO"),
            ("NASDAQ", "PEP"), ("NYSE", "PG"),
        ],
    ),
    (
        "game_entertainment",
        "게임/엔터",
        [
            ("KRX", "259960"), ("KRX", "251270"), ("KRX", "352820"),
            ("NASDAQ", "EA"), ("NASDAQ", "TTWO"), ("NASDAQ", "NFLX"),
            ("NYSE", "DIS"), ("NYSE", "RBLX"), ("NYSE", "SPOT"),
        ],
    ),
    (
        "shipbuilding",
        "조선/중공업",
        [
            ("KRX", "009540"), ("KRX", "329180"), ("KRX", "010620"),
            ("KRX", "042660"), ("KRX", "267260"), ("KRX", "034020"),
            ("KRX", "241560"), ("KRX", "000150"),
        ],
    ),
    (
        "battery_evchem",
        "2차전지/화학",
        [
            ("KRX", "373220"), ("KRX", "006400"), ("KRX", "051910"),
            ("KRX", "003670"), ("KRX", "011170"), ("KRX", "009830"),
        ],
    ),
    (
        "crypto",
        "코인",
        [
            ("UPBIT", "KRW-BTC"), ("UPBIT", "KRW-ETH"), ("UPBIT", "KRW-XRP"),
            ("UPBIT", "KRW-SOL"), ("UPBIT", "KRW-DOGE"), ("UPBIT", "KRW-ADA"),
            ("UPBIT", "KRW-AVAX"), ("UPBIT", "KRW-LINK"),
            ("UPBIT", "KRW-DOT"),
        ],
    ),
]


# 자동 분류용 키워드 — KRX/US 종목 이름에 포함된 단어로 매칭
# (대소문자 무시, 부분일치)
NAME_KEYWORDS_KR: dict[str, list[str]] = {
    "semiconductor": [
        "반도체", "디스플레이", "이노텍", "전기", "소자", "솔브레인", "동진쎄미",
        "DB하이텍", "원익", "테스", "유진테크", "리노공업", "심텍", "ISC",
    ],
    "tech_software": [
        "소프트", "테크놀로", "솔루션", "시스템", "정보통신", "네이버", "카카오",
        "엔씨", "더존", "안랩", "한글과컴퓨터", "SDS", "SK텔레콤", "LG유플러스", "KT ",
    ],
    "auto": [
        "자동차", "모비스", "현대차", "기아", "에코프로비엠", "타이어", "성우하이텍",
        "에스엘", "한온시스템", "만도",
    ],
    "pharma": [
        "제약", "바이오", "약품", "헬스케어", "메디", "팜", "녹십자", "유한양행",
        "셀트리온", "보령", "동아에스티", "한미", "광동", "동화", "삼진",
    ],
    "airline": [
        "항공", "에어로", "방위", "방산", "한국항공우주", "넥스원", "한화시스템",
    ],
    "finance": [
        "금융", "은행", "증권", "보험", "캐피탈", "지주", "신한", "KB", "하나금", "우리",
        "삼성생명", "삼성화재", "DB손해", "메리츠",
    ],
    "energy": [
        "에너지", "전력", "가스", "정유", "석유", "POSCO", "포스코", "철강", "현대제철",
        "고려아연", "S-Oil", "SK이노", "한국전력", "한국가스",
    ],
    "consumer": [
        "식품", "유통", "마트", "백화점", "리테일", "주류", "음료", "롯데쇼핑", "이마트",
        "CJ제일제당", "오리온", "농심", "오뚜기", "KT&G", "BGF", "GS리테일", "현대백화점",
        "신세계",
    ],
    "game_entertainment": [
        "게임", "엔터", "미디어", "엠넷", "방송", "크래프톤", "넷마블", "엔씨소프트",
        "위메이드", "펄어비스", "데브시스터즈", "하이브", "JYP", "SM ", "YG",
        "스튜디오드래곤", "콘텐트리",
    ],
    "shipbuilding": [
        "조선", "중공업", "오션", "두산", "현대일렉", "현대미포", "한화오션",
        "한국조선해양", "현대로템",
    ],
    "battery_evchem": [
        "배터리", "화학", "케미칼", "에너지솔루션", "퓨처엠", "에코프로", "엘앤에프",
        "포스코퓨처엠", "LG화학", "삼성SDI", "한화솔루션", "롯데케미칼", "코스모신소재",
    ],
}

NAME_KEYWORDS_US: dict[str, list[str]] = {
    "semiconductor": ["semiconductor", "chip", "fab"],
    "tech_software": ["software", "cloud", "data", "ai "],
    "auto": ["motor", "automotive", "ev "],
    "pharma": ["pharm", "bio", "health", "medic", "therap"],
    "airline": ["airlines", "aero", "boeing", "defense"],
    "finance": ["bank", "financial", "capital", "insurance"],
    "energy": ["energy", "oil", "gas", "petro", "power"],
    "consumer": ["foods", "beverage", "retail", "stores"],
    "game_entertainment": ["games", "entertain", "media", "studios"],
    "shipbuilding": ["ship", "marine"],
    "battery_evchem": ["chem", "battery"],
}


# 캐시
_cache: tuple[float, list[dict]] | None = None
_TTL_FULL = 60.0   # 모든 카테고리 가격이 충분히 채워졌을 때
_TTL_PARTIAL = 15.0  # 가격 비어있는 게 많을 때 → 짧게
_refresh_task: asyncio.Task | None = None  # 백그라운드 갱신 핸들 (중복 spawn 방지)


def _name_lookup() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for c, n, _, _ in KR_SEEDS:
        out[("KRX", c)] = n
    for c, n, m, _ in US_SEEDS:
        out[(m, c)] = n
    return out


def _classify_by_name(name: str, market: str) -> list[str]:
    """이름으로부터 매칭되는 카테고리 키 리스트."""
    if not name:
        return []
    n = name.lower()
    keys: list[str] = []
    table = NAME_KEYWORDS_KR if market == "KRX" else NAME_KEYWORDS_US
    for cat, kws in table.items():
        for kw in kws:
            if kw.lower() in n:
                keys.append(cat)
                break
    return keys


def _build_groups(db) -> dict[str, list[tuple[str, str]]]:
    """카테고리 키 → (market, code) 목록. 시드 + DB 자동 분류 병합."""
    out: dict[str, list[tuple[str, str]]] = {k: [] for k, _, _ in INDUSTRY_GROUPS}
    seen: dict[str, set[tuple[str, str]]] = {k: set() for k in out}

    # 1) 시드 먼저
    for k, _, codes in INDUSTRY_GROUPS:
        for mc in codes:
            if mc not in seen[k]:
                seen[k].add(mc)
                out[k].append(mc)

    # 2) DB 자동 분류 — KRX/NASDAQ/NYSE/AMEX 활성 종목
    syms = (
        db.query(Symbol)
        .filter(Symbol.is_active)
        .filter(Symbol.market.in_(["KRX", "NASDAQ", "NYSE", "AMEX"]))
        .all()
    )
    for s in syms:
        cats = _classify_by_name(s.name or "", s.market)
        for c in cats:
            mc = (s.market, s.code)
            if mc not in seen[c]:
                seen[c].add(mc)
                out[c].append(mc)
    return out


async def _fetch_live_quotes(
    krx: list[str], us: list[tuple[str, str]], upbit: list[str]
) -> dict[tuple[str, str], dict]:
    """누락 종목 실시간 batch 조회. KIS와 Stooq를 race (먼저 성공한 결과 합쳐 사용)."""
    out: dict[tuple[str, str], dict] = {}

    async def _krx_path() -> None:
        if not krx:
            return
        # Stooq는 빠르고 신뢰성 OK — KIS와 동시 호출해서 결과 합치기
        async def via_stooq() -> dict:
            try:
                return await asyncio.wait_for(
                    _stooq.fetch_quotes_kr(krx), timeout=25.0
                )
            except Exception as e:
                logger.debug("industries Stooq KR: {}", e)
                return {}

        async def via_kis() -> dict:
            if not _kis._configured():
                return {}
            try:
                return await asyncio.wait_for(_kis.fetch_prices(krx), timeout=15.0)
            except Exception as e:
                logger.debug("industries KIS: {}", e)
                return {}

        st, ki = await asyncio.gather(via_stooq(), via_kis(), return_exceptions=False)
        # KIS 우선 (한국 실시간) → 빈 자리 Stooq로 채움
        merged: dict[str, dict] = {}
        for code, info in (ki or {}).items():
            if info:
                merged[code] = info
        for code, info in (st or {}).items():
            if info and code not in merged:
                merged[code] = info
        # yfinance 폴백 (Stooq+KIS 둘 다 막힌 환경)
        missing = [c for c in krx if c not in merged]
        if missing:
            try:
                # 한국 종목은 .KS(KOSPI)/.KQ(KOSDAQ) 둘 다 시도 — 어느 쪽 상장인지 모를 때
                # 두 형식 한 번에 yfinance에 던지고 성공한 쪽 채택
                cand: list[str] = []
                for c in missing:
                    cand.append(f"{c}.KS")
                    cand.append(f"{c}.KQ")
                yfres = await asyncio.wait_for(
                    _fetch_yf_quotes(cand), timeout=30.0
                )
                for k, info in yfres.items():
                    code6 = k.split(".")[0]
                    if code6 not in merged and info:
                        merged[code6] = info
            except Exception as e:
                logger.warning("industries KRX yfinance fallback: {}", e)
        for code, info in merged.items():
            out[("KRX", code)] = info

    async def _us_path() -> None:
        if not us:
            return
        codes_only = [c for _, c in us]
        mkt_by = {c: m for m, c in us}
        # 1) Stooq 시도
        try:
            q = await asyncio.wait_for(_stooq.fetch_quotes(codes_only), timeout=25.0)
            for code, info in q.items():
                if info:
                    out[(mkt_by.get(code, "NASDAQ"), code)] = info
        except Exception as e:
            logger.warning("industries Stooq US: {}", e)
        # 2) yfinance 폴백 (Stooq가 막힌 NAS/방화벽 환경 대응)
        missing = [c for c in codes_only if (mkt_by.get(c, "NASDAQ"), c) not in out]
        if missing:
            try:
                q2 = await asyncio.wait_for(
                    _fetch_yf_quotes(missing), timeout=30.0
                )
                for code, info in q2.items():
                    if info:
                        out[(mkt_by.get(code, "NASDAQ"), code)] = info
            except Exception as e:
                logger.warning("industries yfinance fallback: {}", e)

    async def _upbit_path() -> None:
        if not upbit:
            return
        try:
            q = await asyncio.wait_for(_upbit.fetch_prices(upbit), timeout=10.0)
            for code, info in q.items():
                if info:
                    out[("UPBIT", code)] = info
        except Exception as e:
            logger.warning("industries UPBIT fetch: {}", e)

    await asyncio.gather(_krx_path(), _us_path(), _upbit_path(), return_exceptions=True)
    return out


def _upsert_prices(live: dict[tuple[str, str], dict]) -> None:
    if not live:
        return
    db = SessionLocal()
    try:
        name_by = _name_lookup()
        for (mkt, code), info in live.items():
            sym = (
                db.query(Symbol)
                .filter(Symbol.market == mkt, Symbol.code == code)
                .first()
            )
            if not sym:
                name = name_by.get((mkt, code), code)
                asset_type = "CRYPTO" if mkt == "UPBIT" else "STOCK"
                currency = "USD" if mkt in ("NASDAQ", "NYSE", "AMEX") else "KRW"
                sym = Symbol(
                    code=code, name=name, market=mkt,
                    asset_type=asset_type, currency=currency, is_active=True,
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
                    if info.get("prev_close") else None
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


def _build_response_from_db() -> tuple[list[dict], int, int]:
    """현재 DB 상태만으로 응답 구성 (외부 호출 없음, 빠름)."""
    db = SessionLocal()
    try:
        groups_by_key = _build_groups(db)
        sym_rows = (
            db.query(Symbol, Price)
            .outerjoin(Price, Price.symbol_id == Symbol.id)
            .filter(Symbol.is_active)
            .all()
        )
        by_mc = {(s.market, s.code): (s, p) for s, p in sym_rows}
        name_by = _name_lookup()

        out_list: list[dict] = []
        total = 0
        priced = 0
        for key, label, _ in INDUSTRY_GROUPS:
            codes = groups_by_key.get(key, [])
            items: list[dict] = []
            for mkt, code in codes:
                sp = by_mc.get((mkt, code))
                name = name_by.get((mkt, code), code)
                if sp:
                    s, p = sp
                    price = float(p.price) if p else None
                    prev = float(p.prev_close) if (p and p.prev_close) else None
                    change_pct = (
                        ((price - prev) / prev * 100)
                        if (price is not None and prev) else None
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
                    if price is not None:
                        priced += 1
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
                total += 1
            out_list.append({"key": key, "label": label, "items": items})
        return out_list, priced, total
    finally:
        db.close()


async def _refresh_prices() -> None:
    """누락 가격을 외부에서 가져와 DB upsert. 백그라운드에서 도는 무거운 작업."""
    global _cache
    db = SessionLocal()
    try:
        groups_by_key = _build_groups(db)
        sym_rows = (
            db.query(Symbol, Price)
            .outerjoin(Price, Price.symbol_id == Symbol.id)
            .filter(Symbol.is_active)
            .all()
        )
        by_mc = {(s.market, s.code): (s, p) for s, p in sym_rows}
        need_krx: list[str] = []
        need_us: list[tuple[str, str]] = []
        need_upbit: list[str] = []
        for codes in groups_by_key.values():
            for mkt, code in codes:
                sp = by_mc.get((mkt, code))
                if sp and sp[1] is not None:
                    continue
                if mkt == "KRX" and code not in need_krx:
                    need_krx.append(code)
                elif mkt in ("NASDAQ", "NYSE", "AMEX") and (mkt, code) not in need_us:
                    need_us.append((mkt, code))
                elif mkt == "UPBIT" and code not in need_upbit:
                    need_upbit.append(code)
    finally:
        db.close()

    if not (need_krx or need_us or need_upbit):
        logger.debug("industries refresh: 모든 가격이 이미 DB에 있음")
    else:
        try:
            live = await _fetch_live_quotes(need_krx, need_us, need_upbit)
            _upsert_prices(live)
        except Exception as e:
            logger.warning("industries refresh failed: {}", e)

    # 캐시 갱신 (DB에서 최신 결과 재구성)
    out_list, priced, total = _build_response_from_db()
    ratio = (priced / total) if total else 0.0
    ttl_used = _TTL_FULL if ratio >= 0.7 else _TTL_PARTIAL
    _cache = (time.time() - (_TTL_FULL - ttl_used), out_list)
    logger.info(
        "industries refreshed: {}/{} priced ({:.0%}), ttl={}s",
        priced, total, ratio, ttl_used,
    )


def _spawn_refresh() -> None:
    """동일 시점에 중복 spawn 방지."""
    global _refresh_task
    if _refresh_task is not None and not _refresh_task.done():
        return  # 이미 도는 중
    try:
        loop = asyncio.get_running_loop()
        _refresh_task = loop.create_task(_refresh_prices())
    except RuntimeError:
        # 실행 중 루프 없음 (테스트/스크립트) — 폴백
        try:
            _refresh_task = asyncio.ensure_future(_refresh_prices())
        except Exception:
            pass


async def industries() -> list[dict]:
    """업종별 종목 + 현재가 — stale-while-revalidate.

    - 캐시 fresh: 즉시 반환
    - 캐시 stale: 즉시 반환 + 백그라운드 갱신
    - 캐시 없음(cold): DB 스냅샷 즉시 반환 + 백그라운드 갱신
      (가격은 null인 채로 빠르게 응답, 다음 호출에 채워짐)
    """
    global _cache
    if _cache:
        age = time.time() - _cache[0]
        if age < _TTL_FULL:
            return _cache[1]
        # stale → 즉시 반환 + 백그라운드 갱신
        _spawn_refresh()
        return _cache[1]

    # cold → DB 즉시 응답 + 백그라운드 갱신
    out_list, priced, total = _build_response_from_db()
    _cache = (time.time() - _TTL_FULL + _TTL_PARTIAL, out_list)
    _spawn_refresh()
    logger.info(
        "industries cold start: {}/{} priced (background refresh kicked)",
        priced, total,
    )
    return out_list
