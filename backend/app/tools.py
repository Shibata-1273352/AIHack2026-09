"""シミュレータ制御API (/agent/*) への型付きプロキシ。

- 全呼出を Evidence（証拠ID・時刻・生結果）として保存し、SSE で配信する
- 読取ツールの回数上限を数える（N-04: 読取20回）
- エージェント（LLM）はこのクラス経由でしか環境に触れない。/admin/* は呼べない
"""

from __future__ import annotations

from typing import Any

import httpx

from . import db, events, otel
from .config import settings


class ToolLimitExceeded(Exception):
    pass


class ToolBelt:
    READ_LIMIT = 20  # N-04

    def __init__(self, incident_id: str) -> None:
        self.incident_id = incident_id
        self.read_calls = 0
        self._client = httpx.Client(base_url=settings.sim_url, timeout=90)

    # ------------------------------------------------------------ internals

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._client.post(path, json=payload)
        if r.status_code >= 400:
            detail = r.json().get("detail", r.text) if r.headers.get(
                "content-type", "").startswith("application/json") else r.text
            raise RuntimeError(f"{path}: {detail}")
        return r.json()

    def _evidence(self, tool: str, params: dict[str, Any], summary: str,
                  result: dict[str, Any]) -> dict[str, Any]:
        ev = db.add_record(self.incident_id, "evidence", {
            "tool": tool, "params": params, "summary": summary,
            "result": result, "data_class": "external_allowed",
        })
        events.publish("evidence", {"incident_id": self.incident_id, "evidence": ev})
        return ev

    def _count_read(self) -> None:
        self.read_calls += 1
        if self.read_calls > self.READ_LIMIT:
            raise ToolLimitExceeded(
                f"読取ツールの回数上限({self.READ_LIMIT})に達しました")

    # ------------------------------------------------------------ read tools

    def observe_node(self, node: str, aspects: list[str],
                     env: str = "target") -> dict[str, Any]:
        self._count_read()
        with otel.span(self.incident_id, f"observe_node {node} {','.join(aspects)}",
                       "tool", {"node": node, "aspects": aspects}):
            res = self._post("/agent/observe_node",
                             {"env": env, "node": node, "aspects": aspects})
        summary = self._summarize_observe(node, res)
        ev = self._evidence("observe_node", {"node": node, "aspects": aspects, "env": env},
                            summary, res)
        return {"evidence": ev, "result": res}

    def probe_path(self, src: str, dst: str, kind: str,
                   port: int | None = None, env: str = "target") -> dict[str, Any]:
        self._count_read()
        label = f"probe {kind} {src}→{dst}" + (f":{port}" if port else "")
        with otel.span(self.incident_id, label, "tool",
                       {"src": src, "dst": dst, "kind": kind}):
            res = self._post("/agent/probe_path",
                             {"env": env, "src": src, "dst": dst,
                              "kind": kind, "port": port})
        ok = "成功" if res["ok"] else "失敗"
        ev = self._evidence("probe_path",
                            {"src": src, "dst": dst, "kind": kind, "port": port},
                            f"{label} → {ok}", res)
        return {"evidence": ev, "result": res}

    def test_business(self, env: str = "target") -> dict[str, Any]:
        self._count_read()
        with otel.span(self.incident_id, f"業務テスト({env})", "verifier", {"env": env}):
            res = self._post("/agent/test/business", {"env": env})
        verdict = "合格(3回連続成功)" if res["pass"] else "不合格"
        ev = self._evidence("test_business", {"env": env},
                            f"業務テスト(HTTPS受注画面×3) → {verdict}", res)
        events.publish("business", {"incident_id": self.incident_id,
                                    "env": env, "pass": res["pass"],
                                    "attempts": res["attempts"]})
        return {"evidence": ev, "result": res}

    def test_forbidden(self, env: str = "target") -> dict[str, Any]:
        self._count_read()
        with otel.span(self.incident_id, f"禁止通信テスト({env})", "verifier", {"env": env}):
            res = self._post("/agent/test/forbidden", {"env": env})
        verdict = "遮断維持(合格)" if res["pass"] else "遮断されていない(不合格)"
        ev = self._evidence("test_forbidden", {"env": env},
                            f"禁止通信テスト(telnet:23) → {verdict}", res)
        return {"evidence": ev, "result": res}

    # ------------------------------------------------------------ plan tools

    def validate_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        with otel.span(self.incident_id, "検証用環境で事前検証", "tool",
                       {"plan": plan}):
            res = self._post("/agent/plan/validate", {"plan": plan})
        verdict = "合格" if res.get("verified") else f"不合格({res.get('reason','')})"
        ev = self._evidence("validate_plan", {"plan": plan},
                            f"事前検証（複製→一致判定→修正→業務/回帰テスト） → {verdict}", res)
        return {"evidence": ev, "result": res}

    def apply_plan(self, plan: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        with otel.span(self.incident_id, "対象環境へ適用", "tool",
                       {"idempotency_key": idempotency_key}):
            res = self._post("/agent/plan/apply",
                             {"plan": plan, "idempotency_key": idempotency_key})
        ev = self._evidence("apply_plan",
                            {"plan": plan, "idempotency_key": idempotency_key},
                            f"適用完了 execution_id={res['execution_id']}"
                            + ("（冪等再生）" if res.get("idempotent_replay") else ""),
                            res)
        return {"evidence": ev, "result": res}

    def rollback_plan(self, execution_id: str) -> dict[str, Any]:
        with otel.span(self.incident_id, "復元(rollback)", "tool",
                       {"execution_id": execution_id}):
            res = self._post("/agent/plan/rollback", {"execution_id": execution_id})
        ev = self._evidence("rollback_plan", {"execution_id": execution_id},
                            "適用前状態への復元を実行", res)
        return {"evidence": ev, "result": res}

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _summarize_observe(node: str, res: dict[str, Any]) -> str:
        parts = [f"{node} を観測:"]
        obs = res.get("observations", {})
        if "link" in obs and obs["link"].get("parsed"):
            downs = [f"{i['ifname']}={i['operstate']}"
                     for i in obs["link"]["parsed"]
                     if i["ifname"] != "lo" and i["operstate"] != "UP"]
            parts.append("リンク異常 " + ", ".join(downs) if downs else "リンク全て UP")
        if "failover" in obs and obs["failover"].get("state"):
            parts.append(f"冗長化制御: 使用経路={obs['failover']['state']['active_path']}")
        if "nft" in obs and obs["nft"].get("raw"):
            txt = obs["nft"]["raw"].get("stdout", "")
            n_rules = txt.count("comment")
            parts.append(f"ACLルール {n_rules} 件")
        return " ".join(parts)

    def close(self) -> None:
        self._client.close()
