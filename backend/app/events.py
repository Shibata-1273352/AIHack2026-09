"""SSE イベント配信。

OrcaRouter の応答はストリームしない（1バイト送出後は fallback 不可のため）。
ブラウザへ流すのはサーバ生成の型付きイベントのみ。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

_subscribers: list[asyncio.Queue] = []
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    if q in _subscribers:
        _subscribers.remove(q)


def publish(event_type: str, data: dict[str, Any]) -> None:
    """どのスレッドからでも呼べる。UIへ届ける型付きイベント。"""
    payload = {"type": event_type, **data}
    for q in list(_subscribers):
        try:
            if _loop and _loop.is_running():
                _loop.call_soon_threadsafe(q.put_nowait, payload)
            else:
                q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def sse_format(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
