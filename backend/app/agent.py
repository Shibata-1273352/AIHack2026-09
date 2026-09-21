"""調査エージェント。

2モード:
- llm:      OrcaRouter の json_schema 構造化出力で「次の行動」を選択するループ。
            ネイティブ tool-calling ではなく、サーバが型付きツールを実行する
            （tsumugi で実証済みのパターン）。上限: 判断10 / 読取20（N-04）。
- scripted: 決定木。LLM 失敗時の自動フォールバック先でもある。
            どちらのモードでも同じ型付きツール・同じ証拠記録・同じ承認фローを通る。

正解ラベル（注入状態）はエージェントへ渡さない（§7.3）。観測だけから調べる。
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from typing import Any

from . import db, events, incident, otel, vlm
from .approval import create_request, plan_hash
from .config import settings
from .llm.gateway import BudgetExceeded, gateway
from .tools import ToolBelt, ToolLimitExceeded


def publish_step(incident_id: str, title: str, detail: str = "") -> dict[str, Any]:
    step = db.add_record(incident_id, "step", {"title": title, "detail": detail})
    events.publish("agent_step", {"incident_id": incident_id, "step": step})
    incident.set_activity(incident_id, title)
    return step


def add_hypothesis(incident_id: str, text: str, status: str,
                   evidence_ids: list[str], next_check: str = "") -> dict[str, Any]:
    h = db.add_record(incident_id, "hypothesis", {
        "text": text, "status": status,  # open | supported | rejected
        "evidence_ids": evidence_ids, "next_check": next_check,
    })
    events.publish("hypothesis", {"incident_id": incident_id, "hypothesis": h})
    return h


def update_hypothesis(incident_id: str, h: dict[str, Any], status: str,
                      evidence_ids: list[str] | None = None,
                      next_check: str | None = None) -> None:
    h["status"] = status
    if evidence_ids:
        h["evidence_ids"] = list({*h["evidence_ids"], *evidence_ids})
    if next_check is not None:
        h["next_check"] = next_check
    db.update_record(h["id"], h)
    events.publish("hypothesis", {"incident_id": incident_id, "hypothesis": h})


# ================================================================ 起動口

def start_investigation(incident_id: str) -> None:
    """案件受付後の調査開始（別スレッドで実行）。"""
    from . import runtime
    runtime.workers.add(incident_id)
    t = threading.Thread(target=runtime.run_worker,
                         args=(incident_id, _run_investigation, incident_id), daemon=True)
    t.start()


def _run_investigation(incident_id: str) -> None:
    inc = incident.get(incident_id)
    mode = inc["mode"]
    tools = ToolBelt(incident_id)
    try:
        incident.transition(incident_id, "INVESTIGATING",
                            "導入済みの拠点設定を参照して調査を開始")
        if mode == "llm":
            try:
                _investigate_llm(incident_id, tools)
                return
            except (BudgetExceeded, ToolLimitExceeded) as exc:
                publish_step(incident_id, "実行上限に到達",
                             f"{exc} — scripted モードへフォールバックします")
            except Exception as exc:  # noqa: BLE001
                publish_step(
                    incident_id, "LLM調査が失敗（自動フォールバック）",
                    f"{type(exc).__name__}: {str(exc)[:200]} — scripted モードで継続します")
            incident.set_fields(incident_id, mode="scripted_fallback",
                                route_label="scripted（LLMフォールバック）")
            _investigate_scripted(incident_id, tools)
        else:
            incident.set_fields(incident_id, route_label="scripted（決定木）")
            _investigate_scripted(incident_id, tools)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        incident.transition(incident_id, "NEEDS_HUMAN",
                            f"調査処理が失敗しました: {type(exc).__name__}: {str(exc)[:200]}")
    finally:
        tools.close()


# ================================================================ scripted 決定木

def _investigate_scripted(incident_id: str, tools: ToolBelt) -> None:
    pause = 0.6  # UI が追える最小の間

    # ---- 1. 業務影響の確認（申告の再現） ----
    publish_step(incident_id, "業務テストで申告内容を確認",
                 "拠点クライアントから受注画面(HTTPS)へ実アクセスします")
    incident.node_status(incident_id, "client", "probing", "検査中")
    biz = tools.test_business()
    incident.node_status(incident_id, "client", "ok", "端末は正常")
    business_ok = biz["result"]["pass"]
    incident.set_fields(incident_id,
                        business_status="ok" if business_ok else "down")
    time.sleep(pause)

    # ---- 2. 構成図の読取（VLM） ----
    publish_step(incident_id, "構成図をVLMで構造化し登録機器表と照合",
                 "図由来の情報は実測で裏付けるまで確定扱いにしません")
    vlm.read_topology(incident_id)
    time.sleep(pause)

    # ---- 3. 拠点GWの観測 ----
    publish_step(incident_id, "拠点GWを観測（リンク・経路・冗長化制御）")
    incident.node_status(incident_id, "gw", "probing", "調査中")
    gw = tools.observe_node("gw", ["link", "route", "failover"])
    gw_links = gw["result"]["observations"]["link"]["parsed"]
    r1_link_down = any(i["ifname"] == "eth-r1" and i["operstate"] != "UP"
                       for i in gw_links)
    fo = gw["result"]["observations"]["failover"].get("state") or {}
    active_path = fo.get("active_path", "r1")
    incident.node_status(incident_id, "gw", "ok", "GW自体は正常")

    if r1_link_down:
        incident.link_status(incident_id, "gw-r1", "down", "リンク断")
        h1 = add_hypothesis(
            incident_id,
            "障害A: 主回線リンク断（gw eth-r1 が LOWERLAYERDOWN）",
            "open", [gw["evidence"]["id"]],
            "対向側 r1 のリンク状態を確認して両端で裏付ける")
    else:
        incident.link_status(incident_id, "gw-r1", "normal")
        h1 = None
    if active_path == "r2":
        incident.link_status(incident_id, "gw-r2", "active", "予備経路使用中")
        publish_step(incident_id,
                     "冗長化制御は既に予備経路(r2)へ切替済み",
                     "切替済みなのに業務が再開しない → 単一原因では説明できず、追加調査へ")
    time.sleep(pause)

    # ---- 業務が生きている場合の分岐（T-01 / T-02） ----
    if business_ok:
        if r1_link_down and h1:
            r1 = tools.observe_node("r1", ["link"])
            update_hypothesis(incident_id, h1, "supported",
                              [r1["evidence"]["id"]], "")
            incident.node_status(incident_id, "r1", "bad", "リンク断")
            _finish_restored_with_residual(incident_id, tools,
                                           applied_change=False)
        else:
            publish_step(incident_id, "障害は確認されませんでした",
                         "業務テスト合格・リンク正常。不要な変更は提案しません（T-01）")
            incident.transition(incident_id, "RESOLVED",
                                "業務通信の正常を確認。変更は行いません")
        return

    # ---- 4. 主経路ノード r1 の観測（障害Aの両端確認） ----
    publish_step(incident_id, "主経路ノードr1を観測（障害Aの両端を裏付け）")
    incident.node_status(incident_id, "r1", "probing", "調査中")
    r1 = tools.observe_node("r1", ["link"])
    r1_links = r1["result"]["observations"]["link"]["parsed"]
    r1_down = any(i["ifname"] == "eth-gw" and
                  (not i["admin_up"] or i["operstate"] != "UP")
                  for i in r1_links)
    if r1_down and h1:
        update_hypothesis(incident_id, h1, "supported", [r1["evidence"]["id"]],
                          "")
        incident.node_status(incident_id, "r1", "bad", "リンク断（障害A確定）")
        publish_step(incident_id, "障害Aを特定: 主回線リンク断（両端で確認）",
                     "しかし予備経路へ切替済みのため、これだけでは業務不通を説明できません")
    time.sleep(pause)

    # ---- 5. 予備経路の疎通検査 ----
    publish_step(incident_id, "予備経路(r2)の疎通を層別に検査",
                 "L3到達性とTCP/HTTPSを切り分けます")
    incident.node_status(incident_id, "srv", "probing", "到達性検査中")
    incident.node_status(incident_id, "r2", "probing", "調査中")
    p1 = tools.probe_path("client", "10.0.3.2", "ping")
    p2 = tools.probe_path("client", "10.0.100.10", "tcp", port=443)
    p3 = tools.probe_path("gw", "10.0.5.2", "ping")
    incident.node_status(incident_id, "srv", "unknown", "到達不可（原因を調査中）")
    l3_ok = p1["result"]["ok"] and p3["result"]["ok"]
    tcp_ng = not p2["result"]["ok"]
    if l3_ok and tcp_ng:
        h2 = add_hypothesis(
            incident_id,
            "障害B: 予備経路上で業務通信(HTTPS/443)だけが遮断されている（ACL誤設定の疑い）",
            "open",
            [p1["evidence"]["id"], p2["evidence"]["id"], p3["evidence"]["id"]],
            "r2 の転送ACLを確認する")
        publish_step(incident_id,
                     "L3は到達するがTCP:443のみ失敗 → ACL疑いに絞り込み")
    else:
        h2 = add_hypothesis(incident_id, "予備経路の異常（層別未確定）", "open",
                            [p1["evidence"]["id"], p2["evidence"]["id"]],
                            "r2 の設定を確認する")
    time.sleep(pause)

    # ---- 6. r2 の ACL 観測（障害B特定） ----
    publish_step(incident_id, "予備経路ノードr2の転送ACLを観測")
    r2 = tools.observe_node("r2", ["link", "nft"])
    nft_text = (r2["result"]["observations"]["nft"]["raw"] or {}).get("stdout", "")
    bad_rule_line = next(
        (ln.strip() for ln in nft_text.splitlines() if "BAD-ACL-443" in ln), None)
    if bad_rule_line:
        update_hypothesis(incident_id, h2, "supported", [r2["evidence"]["id"]], "")
        incident.node_status(incident_id, "r2", "bad", "ACL誤設定を発見")
        incident.link_status(incident_id, "gw-r2", "blocked", "HTTPS遮断")
        publish_step(
            incident_id,
            "障害Bを特定: r2転送ACLに業務HTTPSを遮断する誤設定ルール",
            f"該当ルール: {bad_rule_line.split('# handle')[0].strip()}")
    else:
        incident.transition(
            incident_id, "NEEDS_HUMAN",
            "予備経路の遮断原因を特定できませんでした。証拠を添えて引き継ぎます")
        return
    time.sleep(pause)

    # ---- 7-8. 修正案の作成と事前検証 ----
    _compose_and_validate_plan(incident_id, tools, "BAD-ACL-443", bad_rule_line)


def _compose_and_validate_plan(incident_id: str, tools: ToolBelt,
                               rule_comment: str,
                               rule_line: str | None) -> None:
    """修正案の作成 → 検証用環境での事前検証 → 承認依頼（scripted/llm 共通）。"""
    plan_body = {
        "action": "delete_nft_rule",
        "node": "r2",
        "table": "fw",
        "chain": "forward",
        "rule_comment": rule_comment,
    }
    h = plan_hash(plan_body)
    rule_disp = (rule_line or "").split("# handle")[0].strip()
    plan = db.add_record(incident_id, "plan", {
        "version": 1,
        "hash": h,
        "title": "予備経路r2の誤設定ACLルールを1件削除",
        "body": plan_body,
        "diff": f"- {rule_disp}",
        "impact": ("拠点(10.0.1.0/24)から受注サービス(10.0.100.10:443)への"
                   "HTTPS通信が予備経路で許可されます。他のルール"
                   "（POLICY-DENY-TELNET等）は変更しません"),
        "rollback": "適用前に保存した r2 のルールセットへ復元します（登録済み復元操作）",
        "preconditions": [
            "対象ルール(BAD-ACL-443)が r2 に存在すること",
            "業務テストが不合格のままであること",
            "冗長化制御が予備経路(r2)を使用中であること",
        ],
        "status": "draft",
        "validation": None,
    })
    events.publish("plan", {"incident_id": incident_id, "plan": plan})

    incident.transition(incident_id, "VALIDATING_PLAN",
                        "検証用環境（対象環境の複製）で修正案を事前検証中")
    publish_step(incident_id, "検証用環境を複製し一致判定 → 修正案を適用して業務・回帰テスト",
                 "一致しない場合は承認待ちへ進みません（§7.4）")
    val = tools.validate_plan(plan_body)
    result = val["result"]

    if not result.get("verified"):
        plan["status"] = "validation_failed"
        plan["validation"] = {
            "verified": False, "reason": result.get("reason"),
            "message": result.get("message")}
        db.update_record(plan["id"], plan)
        events.publish("plan", {"incident_id": incident_id, "plan": plan})
        incident.transition(incident_id, "NEEDS_HUMAN",
                            f"事前検証が不合格のため適用しません: {result.get('message', '')}")
        return

    plan["status"] = "validated"
    plan["validation"] = {
        "verified": True,
        "clone_match": result["clone_match"],
        "pre": {"business": result["clone_tests_pre"]["business"]["pass"],
                "forbidden": result["clone_tests_pre"]["forbidden"]["pass"]},
        "post": {"business": result["clone_tests_post"]["business"]["pass"],
                 "forbidden": result["clone_tests_post"]["forbidden"]["pass"]},
        "evidence_id": val["evidence"]["id"],
    }
    db.update_record(plan["id"], plan)
    events.publish("plan", {"incident_id": incident_id, "plan": plan})

    ap = create_request(incident_id, plan)
    incident.transition(
        incident_id, "AWAITING_APPROVAL",
        f"事前検証合格。iPadで承認してください（期限 {ap['expires_at']}）")
    publish_step(incident_id, "承認待ち",
                 "変更対象・差分・影響・事前検証・復元条件を承認端末に表示中")


# ================================================================ llm モード

DECIDE_SCHEMA = {
    "title": "next_action",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string",
                   "enum": ["observe_node", "probe_path", "test_business",
                            "test_forbidden", "propose_fix",
                            "conclude_no_change"]},
        "node": {"type": "string",
                 "enum": ["client", "gw", "r1", "r2", "srv", ""]},
        "aspects": {"type": "array",
                    "items": {"type": "string",
                              "enum": ["link", "route", "addr", "nft",
                                       "listen", "failover"]}},
        "src": {"type": "string", "enum": ["client", "gw", ""]},
        "dst": {"type": "string"},
        "kind": {"type": "string", "enum": ["ping", "tcp", "https", ""]},
        "port": {"type": "integer"},
        "rule_comment": {"type": "string"},
        "reason": {"type": "string"},
        "hypothesis_update": {"type": "string"},
    },
    "required": ["action", "node", "aspects", "src", "dst", "kind", "port",
                 "rule_comment", "reason", "hypothesis_update"],
}

LLM_SYSTEM = """あなたはネットワーク障害の調査エージェントです。
拠点の業務（受注画面 https://order.example.com/ = 10.0.100.10:443）が使えないという申告を調査します。

構成（登録機器表より）:
- client(業務端末 10.0.1.10) — gw(拠点GW) — r1(主回線経路) — srv(受注サービス)
- gw — r2(予備回線経路) — srv という予備経路がある
- gw には冗長化制御があり、主回線リンク断を検知すると予備経路へ自動切替する
- r1/r2 は転送ACL(nftables table=fw chain=forward)を持つ
- srv では 10.0.100.10 にHTTPS(443)と、ポリシーで遮断済みのtelnet(23)が動いている

使えるツール（読取上限20回、判断上限10回）:
- observe_node: node と aspects(link/route/addr/nft/listen/failover) を指定。failover は gw のみ
- probe_path: src(client/gw), dst(10.0.100.10 / 10.0.2.2 / 10.0.3.2 / 10.0.4.2 / 10.0.5.2 / order.example.com), kind(ping/tcp/https), port(443/23/80)
- test_business: 業務テスト（独立検証器がHTTPSを3回実行）
- test_forbidden: 禁止通信テスト（telnet遮断の維持確認）
- propose_fix: 原因のACLルールを特定できたら rule_comment と node を指定して修正案を提出
  （許可されている変更は r2 の table=fw chain=forward のルール削除のみ。POLICY-* は正当なルールで削除禁止）
- conclude_no_change: 業務が正常で変更不要と判断した場合

原則:
- 証拠に基づいて段階的に絞り込む。観測していないことを断定しない
- 複数の要因がありうる。1つ見つけても業務不通が説明しきれなければ調査を続ける
- reason は日本語で簡潔に（画面に表示されます）
- 使わないパラメータは "" または 0 を入れる
"""


def _investigate_llm(incident_id: str, tools: ToolBelt) -> None:
    incident.set_fields(incident_id, route_label="OrcaRouter（段階別モデル選択）")
    history: list[dict[str, str]] = []

    # 業務テストと構成図読取は案件受付の定型処理として先に実行
    publish_step(incident_id, "業務テストで申告内容を確認",
                 "拠点クライアントから受注画面(HTTPS)へ実アクセスします")
    biz = tools.test_business()
    business_ok = biz["result"]["pass"]
    incident.set_fields(incident_id,
                        business_status="ok" if business_ok else "down")
    history.append({"tool": "test_business", "summary": biz["evidence"]["summary"]})

    publish_step(incident_id, "構成図をVLMで構造化し登録機器表と照合")
    topo = vlm.read_topology(incident_id)
    history.append({"tool": "vlm_read_topology",
                    "summary": json.dumps({"source":topo["source"],
                        "nodes":topo["mapped_nodes"], "links":topo["mapped_links"],
                        "comparison":topo["comparison"]}, ensure_ascii=False)})

    proposed: dict[str, Any] | None = None
    for step_no in range(1, 11):  # 判断10ステップ上限（N-04）
        user = _render_history(history)
        resp = gateway.call(incident_id, f"decide-{step_no:02d}", "decide",
                            system=LLM_SYSTEM, user=user,
                            json_schema=DECIDE_SCHEMA,
                            data_class="external_allowed")  # 観測サマリのみ送信（§8）
        if not resp.parsed or not resp.schema_ok:
            raise RuntimeError(f"構造化出力の取得に失敗 (outcome={resp.outcome})")
        d = resp.parsed
        publish_step(incident_id,
                     f"AI判断{step_no}: {d['action']}",
                     d.get("reason", ""))
        if d.get("hypothesis_update"):
            add_hypothesis(incident_id, d["hypothesis_update"], "open", [], "")

        if d["action"] == "observe_node":
            node = d["node"] or "gw"
            aspects = d["aspects"] or ["link", "route"]
            incident.node_status(incident_id, node, "probing", "調査中")
            res = tools.observe_node(node, aspects)
            _emit_graph_from_observation(incident_id, node, res["result"])
            history.append({"tool": f"observe_node {node} {aspects}",
                            "summary": res["evidence"]["summary"],
                            "detail": _observe_detail(res["result"])})
        elif d["action"] == "probe_path":
            res = tools.probe_path(d["src"] or "client", d["dst"] or "10.0.100.10",
                                   d["kind"] or "ping",
                                   port=(d["port"] or None))
            history.append({"tool": "probe_path",
                            "summary": res["evidence"]["summary"]})
        elif d["action"] == "test_business":
            res = tools.test_business()
            incident.set_fields(
                incident_id,
                business_status="ok" if res["result"]["pass"] else "down")
            history.append({"tool": "test_business",
                            "summary": res["evidence"]["summary"]})
        elif d["action"] == "test_forbidden":
            res = tools.test_forbidden()
            history.append({"tool": "test_forbidden",
                            "summary": res["evidence"]["summary"]})
        elif d["action"] == "propose_fix":
            proposed = d
            break
        elif d["action"] == "conclude_no_change":
            # サーバ側で裏取り: 業務テストが本当に合格しているか（成功の捏造防止）
            check = tools.test_business()
            if check["result"]["pass"]:
                gwobs = tools.observe_node("gw", ["link", "failover"])
                fo = gwobs["result"]["observations"]["failover"].get("state") or {}
                links = gwobs["result"]["observations"]["link"]["parsed"]
                r1_down = any(i["ifname"] == "eth-r1" and i["operstate"] != "UP"
                              for i in links)
                if r1_down or fo.get("active_path") == "r2":
                    _finish_restored_with_residual(incident_id, tools,
                                                   applied_change=False)
                else:
                    incident.transition(incident_id, "RESOLVED",
                                        "業務通信の正常を確認。変更は行いません")
                return
            history.append({"tool": "conclude_no_change(却下)",
                            "summary": "業務テストは不合格のまま。調査を継続してください"})

    if proposed is None:
        raise RuntimeError("判断ステップ上限までに修正案へ到達しませんでした")

    # 提案されたルールの実在確認（LLM出力を鵜呑みにしない）
    node = proposed["node"] or "r2"
    r2obs = tools.observe_node(node, ["nft"])
    nft_text = (r2obs["result"]["observations"]["nft"]["raw"] or {}).get("stdout", "")
    comment = proposed["rule_comment"].strip().strip('"')
    rule_line = next((ln.strip() for ln in nft_text.splitlines()
                      if f'comment "{comment}"' in ln), None)
    if rule_line is None:
        raise RuntimeError(f"提案されたルール({comment})が {node} に存在しません")
    _compose_and_validate_plan(incident_id, tools, comment, rule_line)


def _render_history(history: list[dict[str, str]]) -> str:
    lines = ["これまでの観測結果（時系列）:"]
    for i, h in enumerate(history, 1):
        lines.append(f"{i}. [{h['tool']}] {h['summary']}")
        if h.get("detail"):
            lines.append(f"   詳細: {h['detail']}")
    lines.append("\n次の行動を JSON で1つだけ選んでください。")
    return "\n".join(lines)


def _observe_detail(result: dict[str, Any]) -> str:
    parts = []
    obs = result.get("observations", {})
    if "link" in obs:
        for i in obs["link"].get("parsed", []):
            if i["ifname"] != "lo":
                parts.append(f"{i['ifname']}:{i['operstate']}"
                             + ("" if i["admin_up"] else "(admin down)"))
    if "nft" in obs and obs["nft"].get("raw"):
        txt = obs["nft"]["raw"].get("stdout", "")
        rules = [ln.strip() for ln in txt.splitlines() if "comment" in ln]
        parts.extend(rules[:6])
    if "failover" in obs and obs["failover"].get("state"):
        st = obs["failover"]["state"]
        parts.append(f"冗長化制御: active={st['active_path']}")
    if "route" in obs:
        parts.extend(obs["route"].get("parsed", [])[:6])
    return " / ".join(parts)[:800]


def _emit_graph_from_observation(incident_id: str, node: str,
                                 result: dict[str, Any]) -> None:
    obs = result.get("observations", {})
    downs = [i for i in obs.get("link", {}).get("parsed", [])
             if i["ifname"] != "lo" and i["operstate"] != "UP"]
    nft_bad = "BAD-" in ((obs.get("nft", {}).get("raw") or {}).get("stdout", ""))
    if nft_bad:
        incident.node_status(incident_id, node, "bad", "ACL誤設定を発見")
    elif downs:
        incident.node_status(incident_id, node, "bad", "リンク異常")
        for i in downs:
            m = {"eth-r1": "gw-r1", "eth-r2": "gw-r2", "eth-gw": None,
                 "eth-srv": None}
            link = m.get(i["ifname"])
            if node == "r1" and i["ifname"] == "eth-gw":
                link = "gw-r1"
            if node == "r2" and i["ifname"] == "eth-gw":
                link = "gw-r2"
            if link:
                incident.link_status(incident_id, link, "down", "リンク断")
    else:
        incident.node_status(incident_id, node, "ok", "異常なし")
    fo = obs.get("failover", {}).get("state") or {}
    if fo.get("active_path") == "r2":
        incident.link_status(incident_id, "gw-r2", "active", "予備経路使用中")


# ================================================================ 承認後の継続

def on_approval_decided(incident_id: str, ap: dict[str, Any]) -> None:
    if ap["decision"] == "rejected":
        incident.transition(
            incident_id, "NEEDS_HUMAN",
            f"承認者({ap['approver']})が却下しました。計画の見直しが必要です")
        return
    from . import runtime
    runtime.workers.add(incident_id)
    t = threading.Thread(target=runtime.run_worker, args=(incident_id, _apply_and_verify, incident_id, ap),
                         daemon=True)
    t.start()


def _apply_and_verify(incident_id: str, ap: dict[str, Any]) -> None:
    tools = ToolBelt(incident_id)
    try:
        plan = db.get_record(ap["plan_id"])
        if plan is None or plan.get("status") != "validated":
            incident.transition(incident_id, "NEEDS_HUMAN",
                                "承認対象の計画が検証済み状態ではありません")
            return

        # ---- 適用直前の前提再観測（30秒鮮度、§10.4） ----
        incident.transition(incident_id, "APPLYING",
                            "適用直前の前提を再観測しています（鮮度30秒）")
        publish_step(incident_id, "前提の再観測",
                     "対象ルールの存在・業務不通・使用経路が承認時と同じか確認")
        r2obs = tools.observe_node("r2", ["nft"])
        nft_text = (r2obs["result"]["observations"]["nft"]["raw"] or {}) \
            .get("stdout", "")
        rule_present = plan["body"]["rule_comment"] in nft_text
        biz_now = tools.test_business()
        business_still_down = not biz_now["result"]["pass"]

        if not rule_present:
            incident.transition(
                incident_id, "NEEDS_HUMAN",
                "前提変化: 対象ルールが既に存在しません。古い計画は適用せず停止します（T-20）")
            return
        if not business_still_down:
            publish_step(incident_id,
                         "業務が既に回復しています。変更を適用せず検証へ進みます（T-20）")
            incident.transition(incident_id, "VERIFYING",
                                "変更なしで独立検証を実行中")
            _final_verify(incident_id, tools, applied_change=False)
            return

        # ---- 適用（冪等キー=計画ハッシュ、M-10） ----
        publish_step(incident_id, "承認された差分のみを対象環境へ適用",
                     f"計画 v{plan['version']} hash={plan['hash'][:8]}… / 冪等キーで二重適用を防止")
        apply_res = tools.apply_plan(plan["body"], idempotency_key=plan["hash"])
        execution = db.add_record(incident_id, "execution", {
            "plan_id": plan["id"],
            "execution_id": apply_res["result"]["execution_id"],
            "idempotency_key": plan["hash"],
            "deleted_rule": apply_res["result"].get("deleted_rule"),
            "approver": ap["approver"],
        })
        events.publish("execution", {"incident_id": incident_id,
                                     "execution": execution})
        incident.node_status(incident_id, "r2", "fixed", "修正適用済み")
        incident.link_status(incident_id, "gw-r2", "restored", "遮断解除")

        # ---- 独立検証（M-11） ----
        incident.transition(incident_id, "VERIFYING",
                            "独立検証器で業務テストと回帰テストを実行中")
        _final_verify(incident_id, tools, applied_change=True,
                      execution_id=apply_res["result"]["execution_id"])
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        incident.transition(incident_id, "NEEDS_HUMAN",
                            f"適用処理が失敗しました: {type(exc).__name__}: {str(exc)[:200]}")
    finally:
        tools.close()


def _final_verify(incident_id: str, tools: ToolBelt, applied_change: bool,
                  execution_id: str | None = None) -> None:
    publish_step(incident_id, "業務テスト（3回連続）と禁止通信テストを実行")
    biz = tools.test_business()
    forb = tools.test_forbidden()
    if biz["result"]["pass"] and forb["result"]["pass"]:
        incident.set_fields(incident_id, business_status="ok")
        _finish_restored_with_residual(incident_id, tools,
                                       applied_change=applied_change)
    else:
        if applied_change and execution_id:
            incident.transition(incident_id, "ROLLING_BACK",
                                "検証不合格のため登録済みの復元を実行します")
            tools.rollback_plan(execution_id)
        incident.transition(
            incident_id, "NEEDS_HUMAN",
            "適用後検証が不合格でした。復元を実施し、未復旧として引き継ぎます")


def _finish_restored_with_residual(incident_id: str, tools: ToolBelt,
                                   applied_change: bool) -> None:
    """SERVICE_RESTORED。主回線断が残っていれば残存課題として登録する（§10.1）。"""
    r1 = tools.observe_node("r1", ["link"])
    r1_links = r1["result"]["observations"]["link"]["parsed"]
    r1_down = any(i["ifname"] == "eth-gw" and
                  (not i["admin_up"] or i["operstate"] != "UP")
                  for i in r1_links)
    if r1_down:
        incident.add_residual_issue(
            incident_id,
            "主回線リンク断（障害A）が未復旧",
            "業務は予備経路(r2)で暫定復旧。主回線は物理断相当のためソフトウェアでは修復できません",
            "回線事業者保守窓口（担当候補）",
            "現地保守の手配と回線試験を依頼。復旧後に冗長化制御が自動で主回線へ復帰します")
        note = "業務復旧・主回線の対応継続（暫定復旧として継続管理）"
        incident.node_status(incident_id, "r1", "bad", "残存課題（主回線断）")
    else:
        note = "業務復旧を確認"

    # 構成図: 復旧した業務経路を実イベントとして表示（M-13）
    incident.node_status(incident_id, "srv", "ok", "業務OK")
    incident.node_status(incident_id, "client", "ok", "端末は正常")
    incident.link_status(incident_id, "client-gw", "active", "業務通信")
    if r1_down:
        incident.link_status(incident_id, "gw-r2", "restored", "予備経路で復旧")
        incident.link_status(incident_id, "r2-srv", "ok", "業務通信")
    else:
        incident.link_status(incident_id, "gw-r1", "ok", "主回線")
        incident.link_status(incident_id, "r1-srv", "ok", "業務通信")
    incident.transition(incident_id, "SERVICE_RESTORED", note)
    publish_step(
        incident_id,
        "SERVICE_RESTORED: 業務通信は回復",
        ("承認された修正の適用により" if applied_change else "冗長化制御の切替により")
        + "業務テスト3回連続成功・禁止通信の遮断維持を確認"
        + ("。主回線断は残存課題として記録済み" if r1_down else ""))
