"""承認管理（M-09）。計画の版・ハッシュ・期限に紐付け、サーバ側で全て検証する。

- 承認済みのみ適用（未承認・失効・却下・ハッシュ不一致は拒否 = T-06/T-07）
- 誤って連打しても適用は一回（冪等キー + 決定済み承認の再利用）
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from . import db, events
from .config import settings


def plan_hash(plan_body: dict[str, Any]) -> str:
    canon = json.dumps(plan_body, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def create_request(incident_id: str, plan_record: dict[str, Any]) -> dict[str, Any]:
    """検証合格済みの計画に対する承認依頼を作成する。"""
    expires = time.time() + settings.approval_ttl_seconds
    ap = db.add_record(incident_id, "approval", {
        "plan_id": plan_record["id"],
        "plan_version": plan_record["version"],
        "plan_hash": plan_record["hash"],
        "decision": "pending",
        "approver": None,
        "decided_at": None,
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(expires)),
        "expires_epoch": expires,
    })
    events.publish("approval", {"incident_id": incident_id, "approval": ap})
    return ap


def pending_approval(incident_id: str) -> dict[str, Any] | None:
    for ap in reversed(db.list_records(incident_id, "approval")):
        if ap["decision"] == "pending":
            return ap
    return None


def decide(incident_id: str, plan_id: str, plan_hash_from_client: str,
           decision: str, approver: str) -> dict[str, Any]:
    """iPad からの承認/却下。全条件をサーバ側で照合する（§10.4）。"""
    ap = pending_approval(incident_id)
    if ap is None:
        raise PermissionError("有効な承認依頼がありません（既に決定済みか、依頼前です）")
    if ap["plan_id"] != plan_id:
        raise PermissionError("承認対象の計画が現在の依頼と一致しません（古い画面からの承認を拒否）")
    if ap["plan_hash"] != plan_hash_from_client:
        raise PermissionError("計画ハッシュが一致しません。最新の計画を再取得してください")
    if time.time() > ap["expires_epoch"]:
        ap["decision"] = "expired"
        db.update_record(ap["id"], ap)
        events.publish("approval", {"incident_id": incident_id, "approval": ap})
        raise PermissionError("承認期限が切れています。再検証・再承認が必要です")
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be approve|reject")
    if not approver or not approver.strip():
        raise PermissionError("承認者が未指定です")

    ap["decision"] = "approved" if decision == "approve" else "rejected"
    ap["approver"] = approver.strip()
    ap["decided_at"] = db.now_iso()
    db.update_record(ap["id"], ap)
    events.publish("approval", {"incident_id": incident_id, "approval": ap})

    # 承認待ちの区間をスパンとして記録（タイムラインで人間の判断時間が見える）
    from . import otel
    import datetime as _dt
    start_ms = int(_dt.datetime.fromisoformat(ap["at"]).timestamp() * 1000)
    otel.record_span(incident_id, f"承認待ち → {ap['decision']} ({ap['approver']})",
                     "approval", start_ms, int(time.time() * 1000),
                     {"plan_id": ap["plan_id"], "decision": ap["decision"]})
    return ap
