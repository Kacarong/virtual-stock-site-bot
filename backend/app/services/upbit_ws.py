"""Upbit 공개 웹소켓 — 코인 실시간 시세 스트리밍.

서버가 Upbit WS(wss://api.upbit.com/websocket/v1)에 연결해 KRW 마켓 ticker를
구독하고, 최신가를 메모리에 유지하면서 SSE 구독자들에게 변경분을 push한다.
- 인증/비용 없음(공개 데이터).
- 변경분은 400ms 단위로 코얼레싱해서 과도한 push 방지.
"""
from __future__ import annotations

import asyncio
import json

import websockets
from loguru import logger

_URL = "wss://api.upbit.com/websocket/v1"

# code(예: KRW-BTC) → {"price": float, "change_pct": float}
_live: dict[str, dict] = {}
_dirty: set[str] = set()
_subscribers: set[asyncio.Queue] = set()


def all_latest() -> dict[str, dict]:
    return dict(_live)


def latest(code: str) -> dict | None:
    return _live.get(code)


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


async def _flush_loop() -> None:
    """변경된 코인만 모아 400ms마다 구독자들에게 전송."""
    while True:
        await asyncio.sleep(0.4)
        if not _dirty:
            continue
        batch = {c: _live[c] for c in list(_dirty) if c in _live}
        _dirty.clear()
        if not batch:
            continue
        for q in list(_subscribers):
            try:
                q.put_nowait(batch)
            except asyncio.QueueFull:
                pass


async def _krw_markets() -> list[str]:
    from .sources import upbit

    try:
        mk = await upbit.fetch_markets()
        return [m["market"] for m in mk if m.get("market", "").startswith("KRW-")]
    except Exception:
        return []


async def run_upbit_ws() -> None:
    """Upbit WS 연결 루프 (끊기면 자동 재접속). 앱 시작 시 백그라운드 task로 실행."""
    asyncio.create_task(_flush_loop())
    while True:
        try:
            codes = await _krw_markets()
            if not codes:
                await asyncio.sleep(10)
                continue
            async with websockets.connect(
                _URL, ping_interval=30, ping_timeout=20, max_size=2**22
            ) as ws:
                sub = [
                    {"ticket": "papertrade"},
                    {"type": "ticker", "codes": codes},
                    {"format": "DEFAULT"},
                ]
                await ws.send(json.dumps(sub))
                logger.info("upbit ws connected: {} markets", len(codes))
                async for msg in ws:
                    try:
                        if isinstance(msg, (bytes, bytearray)):
                            msg = msg.decode("utf-8")
                        d = json.loads(msg)
                        code = d.get("code")
                        tp = d.get("trade_price")
                        if not code or tp is None:
                            continue
                        scr = d.get("signed_change_rate")
                        _live[code] = {
                            "price": float(tp),
                            "change_pct": float(scr) * 100 if scr is not None else 0.0,
                        }
                        _dirty.add(code)
                    except Exception:
                        continue
        except Exception as e:
            logger.warning("upbit ws error, reconnecting in 5s: {}", e)
            await asyncio.sleep(5)
