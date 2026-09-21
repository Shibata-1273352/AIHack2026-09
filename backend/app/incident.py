"""案件の状態機械（§10.1）。遷移ごとにスパン記録と SSE イベントを発行する。"""

from __future__ import annotations

import time
from typing import Any

from . import db, events, otel

STATES = [
    "RECEIVED", "INVESTIGATING", "VALIDATING_PLAN", "AWAITING_APPROVAL",
    "APPLYING", "VERIFYING", "SERVICE_RESTORED", "RESOLVED",
    "ROLLING_BACK", "NEEDS_HUMAN", "CANCELLED",
]

STATE_LABELS = {
    "RECEIVED": "受付済み",
    "INVESTIGATING": "調査中",
    "VALIDATING_PLAN": "修正案を事前検証中",
    "AWAITING_APPROVAL": "承認待ち",
    "APPLYING": "変更を適用中",
    "VERIFYING": "復旧を検証中",
    "SERVICE_RESTORED": "業務復旧（残存課題あり）",
    "RESOLVED": "解決済み",
    "ROLLING_BACK": "復元中",
    "NEEDS_HUMAN": "担当者の対応待ち",
    "CANCELLED": "中止",
}


def create(symptom: str, site: str, business: str,
           reporter: str, mode: str) -> dict[str, Any]:
    inc = {
        "id": db.new_id("inc"),
        "created_at": db.now_iso(),
        "symptom": symptom,
        "site": site,
        "business": business,
        "reporter": reporter,
        "status": "RECEIVED",
        "status_label": STATE_LABELS["RECEIVED"],
        "status_history": [{"status": "RECEIVED", "at": db.now_iso()}],
        "current_activity": "案件を受け付けました",
        "current_activity_tech": "",   # 技術層（技術詳細モーダル側で表示する）
        "mode": mode,  # llm | scripted | scripted_fallback
        "route_label": None,
        "route_detail": None,          # 技術層（方式名・候補列など）
        "residual_issues": [],
        "graph_status": {"nodes": {}, "links": {}},
        "success_criteria": "受注画面(HTTPS)の3回連続成功と、禁止通信(telnet)の遮断維持",
        "allowed_scope": "拠点GW・経路ノードの読取、r2転送ACLの承認済み修正のみ",
        "business_status": "unknown",
        "started_ms": int(time.time() * 1000),
    }
    db.save_incident(inc)
    events.publish("incident", {"incident": inc})
    return inc


def get(incident_id: str) -> dict[str, Any]:
    inc = db.load_incident(incident_id)
    if inc is None:
        raise KeyError(incident_id)
    return inc


def _save_publish(inc: dict[str, Any]) -> None:
    db.save_incident(inc)
    events.publish("incident", {"incident": inc})


def transition(incident_id: str, new_status: str, note: str = "", *,
               activity: str | None = None) -> dict[str, Any]:
    """状態遷移。

    二層テキスト（画面は平易・技術詳細は技術層）:
    - `activity` … 画面見出しに出す平易な一文。省略時は STATE_LABELS（既に平易）。
    - `note`     … 技術層。状態履歴と current_activity_tech に残す。
      例外クラス名・要件ID・生の設定値はこちらへ入れる（画面見出しには出さない）。
    """
    inc = get(incident_id)
    old = inc["status"]
    if new_status not in STATES:
        raise ValueError(f"unknown status {new_status}")
    inc["status"] = new_status
    inc["status_label"] = STATE_LABELS[new_status]
    inc["status_history"].append(
        {"status": new_status, "at": db.now_iso(), "note": note})
    inc["current_activity"] = activity or STATE_LABELS[new_status]
    inc["current_activity_tech"] = note
    _save_publish(inc)
    otel.record_span(incident_id, f"状態遷移 {old}→{new_status}", "state",
                     int(time.time() * 1000) - 1, int(time.time() * 1000),
                     {"from": old, "to": new_status, "note": note})
    return inc


def set_activity(incident_id: str, text: str, tech: str = "") -> None:
    inc = get(incident_id)
    inc["current_activity"] = text
    inc["current_activity_tech"] = tech
    _save_publish(inc)


def set_fields(incident_id: str, **fields: Any) -> dict[str, Any]:
    inc = get(incident_id)
    inc.update(fields)
    _save_publish(inc)
    return inc


def add_residual_issue(incident_id: str, title: str, detail: str,
                       assignee: str, action: str) -> None:
    inc = get(incident_id)
    inc["residual_issues"].append({
        "title": title, "detail": detail,
        "assignee": assignee, "action": action, "at": db.now_iso(),
    })
    _save_publish(inc)


def node_status(incident_id: str, node: str, status: str,
                label: str = "") -> None:
    """構成図ノードの状態（unknown/probing/ok/bad/fixed）。実イベント連動（M-13）。"""
    inc = get(incident_id)
    inc["graph_status"]["nodes"][node] = {"status": status, "label": label}
    db.save_incident(inc)
    events.publish("node_status", {"incident_id": incident_id,
                                   "node": node, "status": status, "label": label})


def link_status(incident_id: str, link: str, status: str,
                label: str = "") -> None:
    """リンク状態（normal/active/down/blocked/restored）。"""
    inc = get(incident_id)
    inc["graph_status"]["links"][link] = {"status": status, "label": label}
    db.save_incident(inc)
    events.publish("link_status", {"incident_id": incident_id,
                                   "link": link, "status": status, "label": label})
