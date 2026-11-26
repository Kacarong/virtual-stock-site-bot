"""시장별 영업일 / 장 운영시간.

- KRX: pykrx의 휴장일 + 09:00~15:30
- NASDAQ/NYSE: pandas_market_calendars
- UPBIT: 24/7

is_market_open(market) → True/False
is_trading_day(market, date) → True/False/None(일정 모름)
next_open(market) → datetime
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
import time as _time
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


async def session_refresh_loop() -> None:
    """세션 캐시 주기 갱신. API와 Worker(체결기·폴러) 둘 다 돌려야 같은 기준으로 장 여부를 판단한다."""
    import asyncio

    while True:
        try:
            await asyncio.gather(refresh_sessions("KR"), refresh_sessions("US"), return_exceptions=True)
        except Exception as e:
            logger.debug("session loop failed: {}", e)
        await asyncio.sleep(600)


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

# (market, year) → (monotonic ts, 결과). 결과가 묻는 날짜(ds)까지 확인돼 있으면 계속 쓰고,
# 실패(None)했거나 확인 범위(last)를 넘는 날짜면 1시간마다 다시 조회한다
# (국내는 pykrx가 '오늘까지'만 주므로 날짜가 지나면 범위를 넘게 된다).
_cal_cache: dict[tuple[str, int], tuple[float, object]] = {}
_CAL_RETRY = 3600.0


def _cached_calendar(market: str, year: int, ds: str, load):
    key = (market, year)
    hit = _cal_cache.get(key)
    if hit and (
        _time.monotonic() - hit[0] < _CAL_RETRY
        or (hit[1] is not None and ds <= hit[1][1])
    ):
        return hit[1]
    val = load(year)
    _cal_cache[key] = (_time.monotonic(), val)
    return val


def _holidays_between(biz: set[str], start: datetime, end: datetime) -> set[str]:
    """start~end 평일 중 영업일 목록에 없는 날 = 휴장일."""
    holidays: set[str] = set()
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            ds = cur.strftime("%Y-%m-%d")
            if ds not in biz:
                holidays.add(ds)
        cur += timedelta(days=1)
    return holidays


def _load_krx_calendar(year: int) -> tuple[set[str], str] | None:
    """pykrx로 KRX (휴장일, 확인된 마지막 날짜). 조회 실패·빈 결과면 None(= 일정 모름)."""
    try:
        from .sources.kis import _patch_requests_for_krx
        _patch_requests_for_krx()
        from pykrx import stock  # type: ignore

        days = stock.get_previous_business_days(year=year)  # KRX 영업일 (오늘까지만 나온다)
        biz = {d.strftime("%Y-%m-%d") for d in days}
    except Exception as e:
        logger.warning("pykrx holiday load failed: {}", e)
        return None
    if not biz:
        logger.warning("pykrx business days empty for {}", year)
        return None
    last = max(biz)
    return _holidays_between(biz, datetime(year, 1, 1), datetime.strptime(last, "%Y-%m-%d")), last


def _load_us_calendar(year: int) -> tuple[set[str], str] | None:
    """pandas_market_calendars로 NYSE (휴장일, 확인된 마지막 날짜). 실패 시 None."""
    try:
        import pandas_market_calendars as mcal  # type: ignore

        cal = mcal.get_calendar("NYSE")
        sched = cal.schedule(start_date=f"{year}-01-01", end_date=f"{year}-12-31")
        biz = {d.strftime("%Y-%m-%d") for d in sched.index}
    except Exception as e:
        logger.warning("us holiday load failed: {}", e)
        return None
    if not biz:
        return None
    return _holidays_between(biz, datetime(year, 1, 1), datetime(year, 12, 31)), f"{year}-12-31"


def is_trading_day(market: str, day: datetime) -> bool | None:
    """영업일이면 True, 휴장일이면 False, 일정을 확인할 수 없으면 None."""
    if market == "UPBIT":
        return True
    if day.weekday() >= 5:  # 주말
        return False
    ds = day.strftime("%Y-%m-%d")
    if market == "KRX":
        cal = _cached_calendar("KRX", day.year, ds, _load_krx_calendar)
    elif market in ("NASDAQ", "NYSE"):
        cal = _cached_calendar("US", day.year, ds, _load_us_calendar)
    else:
        return True
    if cal is None:
        return None
    holidays, last = cal
    if ds > last:
        return None  # 확인된 범위 밖
    return ds not in holidays


def is_market_open(market: str, now: datetime | None = None) -> bool:
    """거래 가능 시간인지. Toss 세션(정규장·애프터마켓·데이마켓·프리마켓) 기준.

    Toss 세션 데이터가 있으면 그 중 아무 세션에 속하면 거래가능으로 본다.
    데이터가 없으면 정규장 시간으로 폴백하되, 영업일인지 확인할 수 없으면 닫힌 것으로 본다
    (공휴일에 체결되지 않도록).
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
    if is_trading_day(market, local) is not True:
        return False
    return open_t <= local.time() <= close_t


def next_open(market: str, now: datetime | None = None) -> datetime:
    """다음 개장 시각 (해당시장 로컬 → UTC 변환된 aware datetime)."""
    if market == "UPBIT":
        return now or datetime.now(tz=KST)
    open_t, _close_t, tz = HOURS[market]
    # Toss 세션이 있으면 그 정규장 시작 시각이 정확 (휴장일 반영)
    sessions = _sessions_today(_country_for(market) or "")
    if sessions:
        ref = now or datetime.now(tz=KST)
        starts = [st for (k, st, _et) in sessions if k == "regularMarket" and st > ref]
        if starts:
            return min(starts).astimezone(tz)
    now = (now or datetime.now(tz=tz)).astimezone(tz)
    cur = now
    for _ in range(14):  # 최대 2주 탐색
        # 일정을 모르면(None) 평일은 개장으로 추정 — 예약 시각 추정용, 실제 체결은 is_market_open이 막는다
        if is_trading_day(market, cur) is not False and cur.time() < open_t:
            return cur.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)
        # 다음 날 09:00로 이동
        cur = (cur + timedelta(days=1)).replace(
            hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0
        )
        if is_trading_day(market, cur) is not False:
            return cur
    return cur  # fallback
