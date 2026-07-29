"""시장별 영업일 / 장 운영시간.

- KRX: pykrx의 휴장일 + 09:00~15:30
- NASDAQ/NYSE: pandas_market_calendars
- UPBIT: 24/7

is_market_open(market) → True/False
is_trading_day(market, date) → True/False
next_open(market) → datetime
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from loguru import logger

KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")

# 시장별 운영시간 (로컬 타임)
HOURS = {
    "KRX":    (time(9, 0),  time(15, 30), KST),
    "NASDAQ": (time(9, 30), time(16, 0),  NY),
    "NYSE":   (time(9, 30), time(16, 0),  NY),
}

# --- Toss 장 운영 세션 (정규장/애프터마켓/데이마켓/프리마켓) ----------
_SESSION_LABEL = {
    "dayMarket": "데이마켓",
    "preMarket": "프리마켓",
    "regularMarket": "정규장",
    "afterMarket": "애프터마켓",
}
_SESSION_PRIORITY = {
    "regularMarket": 0,
    "dayMarket": 1,
    "preMarket": 2,
    "afterMarket": 3,
}
# country('KR'|'US') → (KST 날짜, [(key, start_dt, end_dt)])
_session_cache: dict[str, tuple[str, list]] = {}


def _country_for(market: str) -> str | None:
    if market == "KRX":
        return "KR"
    if market in ("NASDAQ", "NYSE", "AMEX"):
        return "US"
    return None


def _today_kst_str() -> str:
    return datetime.now(tz=KST).strftime("%Y-%m-%d")


async def refresh_sessions(country: str) -> None:
    """Toss에서 오늘 장 운영 세션을 받아 캐시. (하루 단위로 바뀌므로 주기적으로 호출)"""
    from .sources import toss as _toss

    try:
        sess = await _toss.fetch_market_sessions(country)
        if sess:
            _session_cache[country] = (_today_kst_str(), sess)
    except Exception as e:
        logger.debug("session refresh {} failed: {}", country, e)


def _sessions_today(country: str) -> list | None:
    e = _session_cache.get(country)
    if e and e[0] == _today_kst_str():
        return e[1]
    return None


def market_session(market: str, now: datetime | None = None) -> str | None:
    """현재 세션 라벨. 'UPBIT'→'24시간', 세션 중이면 라벨, 장마감이면 '장마감',
    Toss 세션 데이터가 없으면 None(호출측이 폴백)."""
    if market == "UPBIT":
        return "24시간"
    country = _country_for(market)
    if not country:
        return None
    sessions = _sessions_today(country)
    if not sessions:
        return None  # 데이터 없음 → 폴백
    now = now or datetime.now(tz=KST)
    matches = [k for (k, st, et) in sessions if st <= now <= et]
    if not matches:
        return "장마감"
    best = min(matches, key=lambda k: _SESSION_PRIORITY.get(k, 9))
    return _SESSION_LABEL[best]


# --- 휴장일 ----------------------------------------------------------

@lru_cache(maxsize=4)
def _krx_holidays_year(year: int) -> set[str]:
    """pykrx로 KRX 휴장일 추출. 실패 시 빈 set."""
    try:
        from .sources.kis import _patch_requests_for_krx
        _patch_requests_for_krx()
        from pykrx import stock  # type: ignore

        # pykrx는 영업일 리스트를 주므로 전체 일자 차집합으로 휴장일 산출
        days = stock.get_previous_business_days(year=year)  # KRX 영업일
        biz = {d.strftime("%Y-%m-%d") for d in days}
        # 한 해 전체 평일 중 영업일에 없는 = 휴장일 (주말은 제외)
        start = datetime(year, 1, 1)
        end = datetime(year, 12, 31)
        holidays: set[str] = set()
        cur = start
        while cur <= end:
            if cur.weekday() < 5:  # 평일
                ds = cur.strftime("%Y-%m-%d")
                if ds not in biz:
                    holidays.add(ds)
            cur += timedelta(days=1)
        return holidays
    except Exception as e:
        logger.warning("pykrx holiday load failed: {}", e)
        return set()


@lru_cache(maxsize=4)
def _us_holidays_year(year: int) -> set[str]:
    """pandas_market_calendars로 NYSE 휴장일."""
    try:
        import pandas_market_calendars as mcal  # type: ignore

        cal = mcal.get_calendar("NYSE")
        sched = cal.schedule(start_date=f"{year}-01-01", end_date=f"{year}-12-31")
        biz = {d.strftime("%Y-%m-%d") for d in sched.index}
        start = datetime(year, 1, 1)
        end = datetime(year, 12, 31)
        holidays: set[str] = set()
        cur = start
        while cur <= end:
            if cur.weekday() < 5:
                ds = cur.strftime("%Y-%m-%d")
                if ds not in biz:
                    holidays.add(ds)
            cur += timedelta(days=1)
        return holidays
    except Exception as e:
        logger.warning("us holiday load failed: {}", e)
        return set()


def is_trading_day(market: str, day: datetime) -> bool:
    if market == "UPBIT":
        return True
    if day.weekday() >= 5:  # 주말
        return False
    ds = day.strftime("%Y-%m-%d")
    if market == "KRX":
        return ds not in _krx_holidays_year(day.year)
    if market in ("NASDAQ", "NYSE"):
        return ds not in _us_holidays_year(day.year)
    return True


def is_market_open(market: str, now: datetime | None = None) -> bool:
    """거래 가능 시간인지. Toss 세션(정규장·애프터마켓·데이마켓·프리마켓) 기준.

    Toss 세션 데이터가 있으면 그 중 아무 세션에 속하면 거래가능으로 본다.
    데이터가 없으면 기존 하드코딩 정규장 시간으로 폴백.
    """
    if market == "UPBIT":
        return True
    label = market_session(market, now)
    if label is not None:
        return label != "장마감"
    # 폴백: 기존 정규장 하드코딩
    if market not in HOURS:
        return False
    open_t, close_t, tz = HOURS[market]
    now = now or datetime.now(tz=tz)
    local = now.astimezone(tz)
    if not is_trading_day(market, local):
        return False
    return open_t <= local.time() <= close_t


def next_open(market: str, now: datetime | None = None) -> datetime:
    """다음 개장 시각 (해당시장 로컬 → UTC 변환된 aware datetime)."""
    if market == "UPBIT":
        return now or datetime.now(tz=KST)
    open_t, _close_t, tz = HOURS[market]
    now = (now or datetime.now(tz=tz)).astimezone(tz)
    cur = now
    for _ in range(14):  # 최대 2주 탐색
        if is_trading_day(market, cur) and cur.time() < open_t:
            return cur.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)
        # 다음 날 09:00로 이동
        cur = (cur + timedelta(days=1)).replace(
            hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0
        )
        if is_trading_day(market, cur):
            return cur
    return cur  # fallback
