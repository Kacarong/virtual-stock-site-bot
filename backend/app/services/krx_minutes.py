"""국내 분봉 저장소 — Toss 1분봉 하나로 1분/5분/1시간봉을 만든다.

yfinance 국내 분봉은 ~20분 늦고, 매일 15:00~15:30(동시호가 포함)이 빠지며, 거래량이 KRX 단독이라
Toss(KRX+넥스트레이드 통합)와 섞으면 이어지는 지점에서 거래량 막대가 한 단계 튄다.
그래서 종목별로 Toss 1분봉을 과거로 페이지를 넘겨 30일치 받아 두고(백필, 한 번),
이후엔 최신 1페이지(200분)만 다시 받아 덮는다.

- 1분봉: 최근 7일치, 5분봉: 최근 30일치 보관 (1시간봉은 5분봉을 묶어 만든다)
- 넥스트레이드 프리/애프터마켓 봉은 버리고 KRX 정규장(09:00~15:30, 15:30봉=종가 동시호가)만 남긴다.
  사이트 현재가가 KRX 가격이라 차트도 같은 시간대만 보여준다. 늦게 여는 날(수능일 10:00~16:30)은
  그날 첫 봉 시각으로 알아낸다.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .sources import toss as _toss

_KST = ZoneInfo("Asia/Seoul")
_M1_KEEP = 7 * 86400
_M5_KEEP = 30 * 86400
_MAX_PAGES = 120  # 30일 ≈ 21거래일 × 720분 ≈ 76페이지
_LATEST_TTL = 2.0  # 최신 페이지 재조회 간격(초) — 같은 종목을 여러 요청이 봐도 Toss 호출은 이 간격으로 1번
_BACKFILL_RETRY = 60.0
_MAX_CODES = 200

# 백필은 페이지 수십 개를 연달아 부르므로 전체에서 하나씩만 돌려 현재가 조회 몫을 남긴다
_backfill_sem = asyncio.Semaphore(1)


class _Store:
    def __init__(self) -> None:
        self.m1: dict[int, dict] = {}
        self.m5: dict[int, dict] = {}
        self.known: set[str] = set()  # 첫 봉을 확인한 날
        self.late: set[str] = set()  # 10:00에 연 날
        self.latest_ts = 0.0
        # 백필 구간부터 끊김 없이 이어 받은 마지막 1분봉 시각(정규장 필터 전). 최신 조회는 여기까지
        # 과거로 이어 받아 공백을 메우고, 이어졌을 때만 이 값을 앞으로 당긴다.
        self.newest_raw = 0
        self.gap = False  # newest_raw 이후 아직 못 이은 구간이 있음
        self.latest_task: asyncio.Task | None = None
        self.ready = False  # 30일 백필 완료
        self.backfill_ts = 0.0
        self.bf_raw: list[dict] = []  # 백필 도중 실패하면 받은 데까지 보관했다가 이어 받는다
        self.used = 0.0


_stores: dict[str, _Store] = {}


def bucket_minutes(rows: list[dict], sec: int) -> list[dict]:
    """시간 오름차순 봉을 sec 간격 봉으로 묶는다. 시작이 잘린 첫 봉(입력 범위 밖에서 시작)은 버린다."""
    out: list[dict] = []
    for r in rows:
        t = r["time"] - r["time"] % sec
        if out and out[-1]["time"] == t:
            g = out[-1]
            g["high"] = max(g["high"], r["high"])
            g["low"] = min(g["low"], r["low"])
            g["close"] = r["close"]
            g["volume"] = (g.get("volume") or 0) + (r.get("volume") or 0)
        else:
            out.append({**r, "time": t})
    if out and rows and out[0]["time"] < rows[0]["time"]:
        out = out[1:]
    return out


def _kst(t: int) -> datetime:
    return datetime.fromtimestamp(t, _KST)


def _regular(st: _Store, raw: list[dict]) -> list[dict]:
    """KRX 정규장 봉만. 날짜가 바뀐 뒤 첫 봉이면 그날 시작 시각을 기록한다
    (입력의 맨 앞 날짜는 앞부분이 잘렸을 수 있어 판단하지 않는다)."""
    out: list[dict] = []
    prev = None
    for r in raw:
        dt = _kst(r["time"])
        day = dt.strftime("%Y-%m-%d")
        if prev is not None and day != prev and day not in st.known:
            st.known.add(day)
            if dt.hour >= 10:
                st.late.add(day)
        prev = day
        m = (dt.hour - (10 if day in st.late else 9)) * 60 + dt.minute
        if 0 <= m <= 390:
            out.append(r)
    return out


def _ingest(st: _Store, raw: list[dict]) -> None:
    rows = _regular(st, raw)
    if not rows:
        return
    now = time.time()
    for r in rows:
        st.m1[r["time"]] = r
    st.m1 = {t: r for t, r in st.m1.items() if t >= now - _M1_KEEP}
    # 새로 들어온 구간의 5분봉을 다시 만든다 (첫 5분 칸의 앞부분은 보관 중인 1분봉으로 채움)
    start = rows[0]["time"] - rows[0]["time"] % 300
    src = {t: r for t, r in st.m1.items() if t >= start}
    src.update((r["time"], r) for r in rows)
    for b in bucket_minutes([src[t] for t in sorted(src)], 300):
        st.m5[b["time"]] = b
    st.m5 = {t: r for t, r in st.m5.items() if t >= now - _M5_KEEP}


async def _fetch_latest(code: str, st: _Store) -> None:
    rows = await _toss.fetch_candles(code, "1m", count=200)
    if not rows:
        return
    # 최신 200분 앞쪽에 못 받은 구간이 있으면(한동안 아무도 안 봤거나 백필이 막 끝난 경우)
    # newest_raw까지 과거로 이어 받는다. 백필 완료 여부와 상관없이 항상.
    linked = True
    if st.newest_raw:
        for _ in range(_MAX_PAGES):
            if rows[0]["time"] <= st.newest_raw:
                break
            more = await _toss.fetch_candles(
                code, "1m", count=200, before=rows[0]["time"], strict=True
            )
            if not more:
                linked = False  # 실패·빈 응답 → 이번엔 못 이음, 다음 조회 때 다시
                break
            rows = more + rows
        else:
            # 30일 넘게 비었다 → 처음부터 다시 백필
            st.ready = False
            st.bf_raw = []
            st.backfill_ts = 0.0
            st.newest_raw = 0
    _ingest(st, rows)
    # (위에서 await하는 사이 백필이 끝나 newest_raw가 바뀌었을 수 있으므로 지금 값으로 다시 확인)
    if linked and (not st.newest_raw or rows[0]["time"] <= st.newest_raw):
        st.newest_raw = max(st.newest_raw, rows[-1]["time"])
        st.gap = False
    else:
        st.gap = True
    st.latest_ts = time.time()


async def _refresh_latest(code: str, st: _Store) -> None:
    if time.time() - st.latest_ts < _LATEST_TTL:
        return
    if not st.latest_task or st.latest_task.done():
        st.latest_task = asyncio.ensure_future(_fetch_latest(code, st))
    # shield: 호출측이 타임아웃으로 취소돼도 다른 요청이 같이 기다리는 조회는 계속
    await asyncio.shield(st.latest_task)


async def _backfill(code: str, st: _Store) -> None:
    async with _backfill_sem:
        cutoff = time.time() - _M5_KEEP
        raw = st.bf_raw  # 앞서 실패했으면 거기서부터 이어 받는다
        done = False
        for _ in range(_MAX_PAGES):
            before = raw[0]["time"] if raw else None
            rows = await _toss.fetch_candles(code, "1m", count=200, before=before, strict=True)
            if rows is None:
                break  # 조회 실패 → 받은 데까지 보관, _BACKFILL_RETRY 뒤 이어서
            if rows and before is not None:
                rows = [r for r in rows if r["time"] < before]
            raw = rows + raw
            if not rows or rows[0]["time"] <= cutoff or len(rows) < 200:
                done = bool(raw)  # 정상 응답인데 더 과거가 없음(신규 상장 등) = 끝
                break
        if not done:
            st.bf_raw = raw
            return
        st.bf_raw = []
        # 다 받은 뒤 한 번에 넣는다 (중간에 넣으면 이어 받는 경계의 5분봉이 반쪽으로 남음)
        _ingest(st, raw)
        # 백필은 시작 시점까지만 받았으므로, 이어 받은 기준을 백필의 마지막 봉으로 되돌리고
        # 다음 최신 조회(바로 하도록 latest_ts=0)가 거기서 지금까지 이어 받게 한다.
        # 이어지기 전까지는 gap=True라 완료로 보지 않는다.
        st.newest_raw = raw[-1]["time"]
        st.gap = True
        st.latest_ts = 0.0
        st.ready = True


def _spawn_backfill(code: str, st: _Store) -> None:
    if st.ready or time.time() - st.backfill_ts < _BACKFILL_RETRY:
        return
    st.backfill_ts = time.time()
    asyncio.ensure_future(_backfill(code, st))


def _store(code: str) -> _Store:
    st = _stores.get(code)
    if st is None:
        if len(_stores) >= _MAX_CODES:
            _stores.pop(min(_stores, key=lambda c: _stores[c].used), None)
        st = _stores[code] = _Store()
    st.used = time.time()
    return st


def is_ready(code: str) -> bool:
    st = _stores.get(code)
    return bool(st and st.ready and not st.gap)


async def bars(code: str, interval: str) -> tuple[list[dict], bool]:
    """(봉 목록, 30일 백필 완료 여부). interval='1m'|'5m'|'1h'.

    백필 전에는 최신 200분치만 들어 있으므로 호출측이 다른 소스와 합쳐 쓴다.
    """
    st = _store(code)
    await _refresh_latest(code, st)
    _spawn_backfill(code, st)
    if interval == "1m":
        return [st.m1[t] for t in sorted(st.m1)], st.ready and not st.gap
    m5 = [st.m5[t] for t in sorted(st.m5)]
    if interval == "5m":
        return m5, st.ready and not st.gap
    return bucket_minutes(m5, 3600), st.ready and not st.gap
