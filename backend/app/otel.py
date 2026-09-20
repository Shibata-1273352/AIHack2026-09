"""OTel 風の簡易スパン記録（M-15 簡易版）。

trace_id = 案件ID。ツール呼出・LLM判断・承認待ち・適用・検証をスパンとして
SQLite へ保存し、UI のタイムライン（ガントレーン）で表示する。
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

from . import db, events


def _now_ms() -> int:
    return int(time.time() * 1000)


def record_span(incident_id: str, name: str, kind: str,
                start_ms: int, end_ms: int,
                attrs: dict[str, Any] | None = None,
                status: str = "ok") -> dict[str, Any]:
    span = db.add_record(incident_id, "span", {
        "name": name, "kind": kind,
        "start_ms": start_ms, "end_ms": end_ms,
        "duration_ms": end_ms - start_ms,
        "attrs": attrs or {}, "status": status,
    })
    events.publish("span", {"incident_id": incident_id, "span": span})
    return span


@contextmanager
def span(incident_id: str, name: str, kind: str = "internal",
         attrs: dict[str, Any] | None = None):
    """with otel.span(...): 実行区間をスパンとして記録する。"""
    start = _now_ms()
    holder: dict[str, Any] = {"attrs": dict(attrs or {})}
    try:
        yield holder
        record_span(incident_id, name, kind, start, _now_ms(),
                    holder["attrs"], "ok")
    except Exception as exc:
        holder["attrs"]["error"] = str(exc)[:300]
        record_span(incident_id, name, kind, start, _now_ms(),
                    holder["attrs"], "error")
        raise
