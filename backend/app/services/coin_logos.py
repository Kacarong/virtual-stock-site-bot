"""코인 로고 URL 맵 (업비트 KRW 마켓 → CoinGecko 250px 로고).

업비트는 고화질 로고를 주지 않는다(BTC/ETH가 64px). CoinGecko의 large 이미지(250px)를
업비트 영문명·심볼로 매칭해 {"KRW-BTC": url} 맵을 만든다.

- 매칭: 영문명이 같은 후보 우선 → 없으면 같은 심볼 중 시가총액 최대.
  업비트가 중복 심볼에 붙이는 꼬리 숫자(META2, GAME2 등)는 떼고도 찾아본다.
- 하루 1회 갱신, /data/coin_logos.json 에 보관해 재시작 직후에도 바로 응답.
- 요청은 절대 CoinGecko를 기다리지 않는다: 있는 맵을 즉시 반환하고 만료 시 백그라운드 갱신.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import httpx
from loguru import logger

from .sources import upbit as _upbit

_CG = "https://api.coingecko.com/api/v3"
_PATH = Path("/data/coin_logos.json")
_TTL = 24 * 3600
_RETRY_AFTER_FAIL = 30 * 60

_state: dict = {"ts": 0.0, "logos": {}, "loaded": False, "last_try": 0.0}
_task: asyncio.Task | None = None


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _load_disk() -> None:
    _state["loaded"] = True
    try:
        if _PATH.exists():
            d = json.loads(_PATH.read_text(encoding="utf-8"))
            _state["ts"] = float(d.get("ts") or 0)
            _state["logos"] = d.get("logos") or {}
    except Exception as e:
        logger.debug("coin logo cache load fail: {}", e)


async def _cg_get(c: httpx.AsyncClient, path: str, params: dict):
    for attempt in range(3):
        r = await c.get(f"{_CG}{path}", params=params)
        if r.status_code == 429 and attempt < 2:
            await asyncio.sleep(20 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()


async def _build() -> dict[str, str]:
    markets = await _upbit.fetch_markets()
    async with httpx.AsyncClient(timeout=30) as c:
        coins = await _cg_get(c, "/coins/list", {})
        by_sym: dict[str, list[dict]] = {}
        for co in coins:
            by_sym.setdefault((co.get("symbol") or "").lower(), []).append(co)

        cands: dict[str, list[dict]] = {}
        for m in markets:
            base = m["market"].split("-", 1)[1].lower()
            syms = [base]
            stripped = base.rstrip("0123456789")
            if stripped and stripped != base:
                syms.append(stripped)
            cands[m["market"]] = [co for s in syms for co in by_sym.get(s, [])]

        ids = sorted({co["id"] for lst in cands.values() for co in lst})
        info: dict[str, dict] = {}
        for i in range(0, len(ids), 250):
            if i:
                await asyncio.sleep(3)  # 무료 API 레이트리밋 여유
            rows = await _cg_get(
                c,
                "/coins/markets",
                {"vs_currency": "usd", "ids": ",".join(ids[i : i + 250]), "per_page": 250},
            )
            for r in rows or []:
                info[r["id"]] = r

    out: dict[str, str] = {}
    for m in markets:
        lst = [info[co["id"]] for co in cands[m["market"]] if co["id"] in info]
        lst = [r for r in lst if r.get("image") and "missing" not in r["image"]]
        if not lst:
            continue
        en = _norm(m.get("english_name"))
        named = [r for r in lst if en and _norm(r.get("name")) == en]
        pick = max(named or lst, key=lambda r: r.get("market_cap") or 0)
        out[m["market"]] = pick["image"]
    return out


async def _refresh() -> None:
    _state["last_try"] = time.time()
    try:
        logos = await _build()
    except Exception as e:
        logger.warning("coin logo refresh failed: {}", e)
        return
    if not logos:
        return
    _state["ts"] = time.time()
    _state["logos"] = logos
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": _state["ts"], "logos": logos}), encoding="utf-8")
        tmp.replace(_PATH)
    except Exception as e:
        logger.debug("coin logo cache save fail: {}", e)
    logger.info("coin logos refreshed: {}", len(logos))


def coin_logos() -> dict[str, str]:
    """현재 맵을 즉시 반환. 만료됐으면 백그라운드 갱신을 한 번만 띄운다."""
    global _task
    if not _state["loaded"]:
        _load_disk()
    now = time.time()
    stale = now - _state["ts"] > _TTL
    if (
        stale
        and now - _state["last_try"] > _RETRY_AFTER_FAIL
        and (_task is None or _task.done())
    ):
        _task = asyncio.create_task(_refresh())
    return _state["logos"]
