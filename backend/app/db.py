"""SQLite 永続化。状態の正本はサーバ側に置く（§9）。

小規模デモなので ORM は使わず、各テーブルは JSON 本体 + 検索用カラムの構成。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any

from .config import settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS archived_incidents (id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS incidents (
  id TEXT PRIMARY KEY, created_at TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  incident_id TEXT,
  kind TEXT,            -- evidence | hypothesis | plan | approval | execution | span | model_run | step
  seq INTEGER,
  created_at TEXT,
  data TEXT
);
CREATE INDEX IF NOT EXISTS idx_records ON records(incident_id, kind, seq);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(settings.data_dir / "netwalker.db",
                                check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def save_incident(inc: dict[str, Any]) -> None:
    with _lock:
        conn().execute(
            "INSERT INTO incidents(id, created_at, data) VALUES(?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (inc["id"], inc.get("created_at", now_iso()),
             json.dumps(inc, ensure_ascii=False)))
        conn().commit()


def load_incident(incident_id: str) -> dict[str, Any] | None:
    row = conn().execute("SELECT data FROM incidents WHERE id=?",
                         (incident_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def latest_incident() -> dict[str, Any] | None:
    row = conn().execute(
        "SELECT data FROM incidents WHERE id NOT IN (SELECT id FROM archived_incidents) "
        "ORDER BY created_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    return json.loads(row["data"]) if row else None


def archive_demo() -> None:
    """Keep historical evidence, but start the next presentation with no active case."""
    with _lock:
        c = conn()
        c.execute("INSERT OR IGNORE INTO archived_incidents SELECT id FROM incidents")
        c.commit()


def add_record(incident_id: str, kind: str, data: dict[str, Any],
               record_id: str | None = None) -> dict[str, Any]:
    rid = record_id or new_id(kind[:2])
    with _lock:
        c = conn()
        row = c.execute(
            "SELECT COALESCE(MAX(seq),0)+1 AS s FROM records WHERE incident_id=? AND kind=?",
            (incident_id, kind)).fetchone()
        seq = row["s"]
        data = {**data, "id": rid, "incident_id": incident_id, "seq": seq}
        data.setdefault("at", now_iso())
        c.execute(
            "INSERT INTO records(id, incident_id, kind, seq, created_at, data) "
            "VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (rid, incident_id, kind, seq, now_iso(),
             json.dumps(data, ensure_ascii=False)))
        c.commit()
    return data


def update_record(record_id: str, data: dict[str, Any]) -> None:
    with _lock:
        conn().execute("UPDATE records SET data=? WHERE id=?",
                       (json.dumps(data, ensure_ascii=False), record_id))
        conn().commit()


def get_record(record_id: str) -> dict[str, Any] | None:
    row = conn().execute("SELECT data FROM records WHERE id=?",
                         (record_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_records(incident_id: str, kind: str | None = None) -> list[dict[str, Any]]:
    if kind:
        rows = conn().execute(
            "SELECT data FROM records WHERE incident_id=? AND kind=? ORDER BY seq",
            (incident_id, kind)).fetchall()
    else:
        rows = conn().execute(
            "SELECT data FROM records WHERE incident_id=? ORDER BY created_at, seq",
            (incident_id,)).fetchall()
    return [json.loads(r["data"]) for r in rows]
