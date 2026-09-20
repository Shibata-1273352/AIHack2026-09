"""VLM 構成図読取（M-02）。

構成図PNG → OrcaRouter vision → ノード/リンクJSON → 登録機器表と照合。
- 図から読んだ機器名はそのまま接続先にしない。登録済みIDへ対応付け、
  対応付かないものは「確認待ち」として表示する（§10.2）。
- record モードで golden 保存。live 失敗時は golden へフォールバック。
"""

from __future__ import annotations

import base64
import json
from typing import Any

from . import db, events, otel
from .config import settings
from .llm.gateway import gateway

GRAPH_SCHEMA = {
    "title": "network_graph",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "role": {"type": "string",
                             "enum": ["endpoint", "gateway", "router",
                                      "server", "unknown"]},
                    "zone": {"type": "string"},
                    "annotation": {"type": "string"},
                },
                "required": ["label", "role", "zone", "annotation"],
            },
        },
        "links": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "a": {"type": "string"},
                    "b": {"type": "string"},
                    "label": {"type": "string"},
                    "dashed": {"type": "boolean"},
                },
                "required": ["a", "b", "label", "dashed"],
            },
        },
    },
    "required": ["nodes", "links"],
}

SYSTEM_PROMPT = (
    "あなたはネットワーク構成図の読取器です。渡された構成図画像から、"
    "ノード（機器・サービス）とリンク（配線）を漏れなく抽出し、"
    "指定された JSON スキーマだけで返答してください。"
    "図に描かれていないものを追加してはいけません。"
    "点線のリンクは dashed=true としてください。"
)


def _registered() -> dict[str, Any]:
    return json.loads(
        (settings.assets_dir / "registered_topology.json").read_text(
            encoding="utf-8"))


def _map_label(label: str, registered: dict[str, Any]) -> str | None:
    """図上のラベル → 登録済み機器ID。対応しなければ None（確認待ち）。"""
    norm = label.strip().lower().replace(" ", "").replace("　", "")
    for node in registered["nodes"]:
        for alias in node["aliases"]:
            a = alias.lower().replace(" ", "")
            if a and (a in norm or norm in a):
                return node["id"]
    return None


def read_topology(incident_id: str) -> dict[str, Any]:
    """構成図を読取り、登録機器表と照合した結果を Evidence として返す。"""
    registered = _registered()
    png = settings.assets_dir / "topology-diagram.png"

    extracted: dict[str, Any] | None = None
    source = "vlm"
    run_meta: dict[str, Any] = {}

    with otel.span(incident_id, "VLM構成図読取", "llm") as sp:
        if png.exists():
            b64 = base64.b64encode(png.read_bytes()).decode()
            user_content = [
                {"type": "text",
                 "text": "この構成図からノードとリンクを抽出してください。"},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]
            resp = gateway.call(incident_id, "vlm-topology", "vlm",
                                system=SYSTEM_PROMPT, user=user_content,
                                json_schema=GRAPH_SCHEMA)
            run_meta = {"outcome": resp.outcome, "route": resp.route,
                        "resolved_model": resp.resolved_model,
                        "latency_ms": resp.latency_ms}
            if resp.parsed and resp.schema_ok:
                extracted = resp.parsed
                if resp.outcome in ("mock", "fallback_to_mock"):
                    source = "golden(録画済みVLM応答)"
            sp["attrs"].update(run_meta)

        if extracted is None:
            # VLM不可（画像なし・golden なし・応答不正）→ 登録機器表で継続
            source = "registered_table(VLM未実行)"
            extracted = {
                "nodes": [{"label": n["label"], "role": n["role"],
                           "zone": n["zone"], "annotation": ""}
                          for n in registered["nodes"]],
                "links": [{"a": a["a"], "b": a["b"], "label": "",
                           "dashed": a["kind"] == "backup"}
                          for a in registered["links"]],
            }

    # ---- 登録機器表と照合（M-02/M-03） ----
    mapped_nodes = []
    unmatched: list[str] = []
    for n in extracted["nodes"]:
        rid = _map_label(n["label"], registered)
        mapped_nodes.append({**n, "registered_id": rid})
        if rid is None:
            unmatched.append(n["label"])
    mapped_ids = {m["registered_id"] for m in mapped_nodes if m["registered_id"]}
    missing = [n["id"] for n in registered["nodes"] if n["id"] not in mapped_ids]

    mapped_links = []
    for l in extracted["links"]:
        a = _map_label(l["a"], registered)
        b = _map_label(l["b"], registered)
        mapped_links.append({**l, "a_id": a, "b_id": b})

    comparison = {
        "matched_nodes": sorted(mapped_ids),
        "unmatched_labels": unmatched,       # 図にあるが登録に無い → 確認待ち
        "missing_registered": missing,       # 登録にあるが図から読めない → 確認待ち
        "ok": not unmatched and not missing,
    }

    result = {
        "source": source,
        "extracted": extracted,
        "mapped_nodes": mapped_nodes,
        "mapped_links": mapped_links,
        "comparison": comparison,
        "registered_version": registered["version"],
        "model": run_meta,
    }
    ev = db.add_record(incident_id, "evidence", {
        "tool": "vlm_read_topology",
        "params": {"image": "topology-diagram.png"},
        "summary": (f"構成図読取({source}): ノード{len(mapped_nodes)}件・"
                    f"リンク{len(mapped_links)}件を抽出、登録機器表と"
                    + ("全件一致" if comparison["ok"] else
                       f"不一致あり（確認待ち {len(unmatched) + len(missing)}件）")),
        "result": result,
        "data_class": "external_allowed",
    })
    events.publish("evidence", {"incident_id": incident_id, "evidence": ev})
    events.publish("topology", {"incident_id": incident_id, "topology": result})
    return result
