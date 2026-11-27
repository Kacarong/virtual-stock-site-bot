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
_BACKFILL_RETRY = 300.0
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
        self.latest_task: asyncio.Task | None = None
        self.ready = False  # 30일 백필 완료
        self.backfill_ts = 0.0
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
    if rows:
        _ingest(st, rows)
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
        raw: list[dict] = []
        before = None
        done = False
        for _ in range(_MAX_PAGES):
            rows = await _toss.fetch_candles(code, "1m", count=200, before=before)
            if not rows:
                done = bool(raw)  # 첫 페이지부터 비면 실패로 보고 나중에 다시
                break
            raw = rows + raw
            if rows[0]["time"] <= cutoff or len(rows) < 200:
                done = True
                break
            before = rows[0]["time"]
        if raw:
            _ingest(st, raw)
        st.ready = done


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
    return bool(st and st.ready)


async def bars(code: str, interval: str) -> tuple[list[dict], bool]:
    """(봉 목록, 30일 백필 완료 여부). interval='1m'|'5m'|'1h'.

    백필 전에는 최신 200분치만 들어 있으므로 호출측이 다른 소스와 합쳐 쓴다.
    """
    st = _store(code)
    await _refresh_latest(code, st)
    _spawn_backfill(code, st)
    if interval == "1m":
        return [st.m1[t] for t in sorted(st.m1)], st.ready
    m5 = [st.m5[t] for t in sorted(st.m5)]
    if interval == "5m":
        return m5, st.ready
    return bucket_minutes(m5, 3600), st.ready
