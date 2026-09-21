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

from . import db, events, incident, otel, vlm, wording
from .approval import create_request, plan_hash
from .config import settings
from .llm.gateway import BudgetExceeded, gateway
from .tools import ToolBelt, ToolLimitExceeded


def publish_step(incident_id: str, title: str, detail: str = "", *,
                 tech_title: str | None = None,
                 tech_detail: str | None = None) -> dict[str, Any]:
    """調査ログの1行（二層テキスト）。

    `title`/`detail` が画面に出る平易層、`tech_*` が技術詳細モーダル側の技術層。
    `tech_*` 省略時は UI が平易層へフォールバックするため、移行途中でも壊れない。

    なお publish_step の文字列は LLM の入力に一切使われない（履歴は tools.py の
    evidence summary のみ）。表示文言の変更は推論挙動に影響しない。
    """
    step = db.add_record(incident_id, "step", {
        "title": title, "detail": detail,
        "tech_title": tech_title, "tech_detail": tech_detail,
    })
    events.publish("agent_step", {"incident_id": incident_id, "step": step})
    incident.set_activity(incident_id, title, tech_title or "")
    return step


def add_hypothesis(incident_id: str, text: str, status: str,
                   evidence_ids: list[str], next_check: str = "",
                   *, plain: str | None = None) -> dict[str, Any]:
    h = db.add_record(incident_id, "hypothesis", {
        "text": text, "status": status,  # open | supported | rejected
        "text_plain": plain,             # 画面の平易層（None なら text を表示）
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
                            "導入済みの拠点設定を参照して調査を開始",
                            activity="登録済みの拠点情報をもとに調査を始めます")
        if mode == "llm":
            try:
                _investigate_llm(incident_id, tools)
                return
            except (BudgetExceeded, ToolLimitExceeded) as exc:
                publish_step(incident_id, "決められた手順に切り替えます",
                             "あらかじめ決めた実行の上限に達したためです",
                             tech_title="実行上限に到達（判断10 / 読取20 / 費用上限）",
                             tech_detail=f"{exc} — scripted モードへフォールバック")
            except Exception as exc:  # noqa: BLE001
                publish_step(
                    incident_id, "決められた手順に切り替えます",
                    "AIによる調査を続けられなかったため、あらかじめ決めた手順で調査します",
                    tech_title="LLM調査が失敗（自動フォールバック）",
                    tech_detail=f"{type(exc).__name__}: {str(exc)[:200]} — scripted モードで継続")
            incident.set_fields(incident_id, mode="scripted_fallback",
                                route_label="決められた手順で調べています",
                                route_detail="scripted（LLMフォールバック）")
            _investigate_scripted(incident_id, tools)
        else:
            incident.set_fields(incident_id,
                                route_label="決められた手順で調べています",
                                route_detail="scripted（決定木）")
            _investigate_scripted(incident_id, tools)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        incident.transition(
            incident_id, "NEEDS_HUMAN",
            f"調査処理が失敗しました: {type(exc).__name__}: {str(exc)[:200]}",
            activity="担当者の判断が必要です（調査を最後まで進められませんでした）")
    finally:
        tools.close()


# ================================================================ scripted 決定木

def _investigate_scripted(incident_id: str, tools: ToolBelt) -> None:
    pause = 0.6  # UI が追える最小の間

    # ---- 1. 業務影響の確認（申告の再現） ----
    publish_step(incident_id, "業務通信を実測し、申告のとおりか確かめます",
                 "拠点の業務端末から受注画面へ実際に接続します",
                 tech_title="業務テストで申告内容を確認",
                 tech_detail="test_business: t-client → https://order.example.com/ ×3（独立検証器）")
    incident.node_status(incident_id, "client", "probing", "検査中")
    biz = tools.test_business()
    incident.node_status(incident_id, "client", "ok", "端末は正常")
    business_ok = biz["result"]["pass"]
    incident.set_fields(incident_id,
                        business_status="ok" if business_ok else "down")
    time.sleep(pause)

    # ---- 2. 構成図の読取（VLM） ----
    publish_step(incident_id, "構成図をAIが読み取り、登録済みの機器一覧と照合します",
                 "図から読んだ情報は、実測で裏付けるまで確定として扱いません",
                 tech_title="構成図をVLMで構造化し登録機器表と照合",
                 tech_detail="vlm_read_topology（vision + json_schema） → 登録機器表との機械照合")
    vlm.read_topology(incident_id)
    time.sleep(pause)

    # ---- 3. 拠点GWの観測 ----
    publish_step(incident_id,
                 wording.plain_observe("gw", ["link", "route", "failover"]),
                 tech_title="拠点GWを観測（リンク・経路・冗長化制御）",
                 tech_detail="observe_node gw [link, route, failover]")
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
            "対向側 r1 のリンク状態を確認して両端で裏付ける",
            plain="主回線が切れている（拠点ルータ側で断線を検知）")
    else:
        incident.link_status(incident_id, "gw-r1", "normal")
        h1 = None
    if active_path == "r2":
        incident.link_status(incident_id, "gw-r2", "active", "予備経路使用中")
        publish_step(incident_id,
                     "機器はすでに予備回線へ自動で切り替わっていました",
                     "切り替わっているのに業務は止まったまま。原因は1つではないと考え、調査を続けます",
                     tech_title="冗長化制御は既に予備経路(r2)へ切替済み",
                     tech_detail="failover state: active_path=r2（AIの操作ではなく登録済みの冗長化制御）")
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
            publish_step(incident_id, "異常は見つかりませんでした",
                         "業務通信は正常で、回線にも異常はありません。必要のない変更は提案しません",
                         tech_title="障害は確認されませんでした",
                         tech_detail="T-01: 業務テスト合格・リンク正常 → 変更提案なし")
            incident.transition(incident_id, "RESOLVED",
                                "業務通信の正常を確認。変更は行いません",
                                activity="業務通信は正常でした。変更は行いません")
        return

    # ---- 4. 主経路ノード r1 の観測（障害Aの両端確認） ----
    publish_step(incident_id, "主回線ルータを確認し、断線を両端から裏付けます",
                 tech_title="主経路ノードr1を観測（障害Aの両端を裏付け）",
                 tech_detail="observe_node r1 [link]")
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
        publish_step(incident_id, "原因1を特定：主回線が切れています（両端で確認）",
                     "ただし予備回線へ切り替え済みなので、これだけでは業務が止まっている理由を説明できません",
                     tech_title="障害Aを特定: 主回線リンク断（両端で確認）",
                     tech_detail="gw eth-r1 / r1 eth-gw ともに operstate != UP")
    time.sleep(pause)

    # ---- 5. 予備経路の疎通検査 ----
    publish_step(incident_id, "予備回線の通信を、層に分けて試験します",
                 "相手まで届くのか、業務の通信そのものが通るのかを分けて確かめます",
                 tech_title="予備経路(r2)の疎通を層別に検査",
                 tech_detail="L3到達性(ICMP) と TCP:443/HTTPS を切り分け")
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
            "r2 の転送ACLを確認する",
            plain="予備回線で、業務通信だけが止められている（通信ルールの誤りの疑い）")
        publish_step(incident_id,
                     "相手までは届くのに、業務の通信だけが止められています",
                     "通信ルールの誤りに絞り込みました",
                     tech_title="L3は到達するがTCP:443のみ失敗 → ACL疑いに絞り込み",
                     tech_detail="ping OK（client→10.0.3.2 / gw→10.0.5.2） / TCP:443 NG")
    else:
        h2 = add_hypothesis(incident_id, "予備経路の異常（層別未確定）", "open",
                            [p1["evidence"]["id"], p2["evidence"]["id"]],
                            "r2 の設定を確認する",
                            plain="予備回線に異常がある（どの層かは未確定）")
    time.sleep(pause)

    # ---- 6. r2 の ACL 観測（障害B特定） ----
    publish_step(incident_id, wording.plain_observe("r2", ["link", "nft"]),
                 tech_title="予備経路ノードr2の転送ACLを観測",
                 tech_detail="observe_node r2 [link, nft]")
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
            "原因2を特定：予備回線ルータに、業務通信だけを止める誤ったルールが1件ありました",
            "これが、予備回線へ切り替わったのに業務が使えない理由です",
            tech_title="障害Bを特定: r2転送ACLに業務HTTPSを遮断する誤設定ルール",
            tech_detail=f"該当ルール: {bad_rule_line.split('# handle')[0].strip()}")
    else:
        incident.transition(
            incident_id, "NEEDS_HUMAN",
            "予備経路の遮断原因を特定できませんでした。証拠を添えて引き継ぎます",
            activity="担当者の判断が必要です（予備回線が止まっている理由を特定できませんでした）")
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
        "title_plain": "予備回線ルータから、業務通信を止めているルールを1件だけ削除します",
        "body": plan_body,
        "diff": f"- {rule_disp}",
        "diff_plain": "予備回線ルータから、業務通信を止めている1つのルールを削除します",
        "impact": ("拠点(10.0.1.0/24)から受注サービス(10.0.100.10:443)への"
                   "HTTPS通信が予備経路で許可されます。他のルール"
                   "（POLICY-DENY-TELNET等）は変更しません"),
        "impact_plain": ("拠点の業務端末から受注サーバへの業務通信が、予備回線で"
                         "通るようになります。止めるべき通信のルールなど、"
                         "ほかの設定は一切変更しません"),
        "rollback": "適用前に保存した r2 のルールセットへ復元します（登録済み復元操作）",
        "rollback_plain": "うまくいかないときは、適用前に保存した設定へ自動で戻します",
        "preconditions": [
            "対象ルール(BAD-ACL-443)が r2 に存在すること",
            "業務テストが不合格のままであること",
            "冗長化制御が予備経路(r2)を使用中であること",
        ],
        "preconditions_plain": [
            "削除対象のルールが、いまも予備回線ルータにあること",
            "業務がまだ使えないままであること",
            "いま使われているのが予備回線であること",
        ],
        "status": "draft",
        "validation": None,
    })
    events.publish("plan", {"incident_id": incident_id, "plan": plan})

    incident.transition(incident_id, "VALIDATING_PLAN",
                        "検証用環境（対象環境の複製）で修正案を事前検証中",
                        activity="本番そっくりの複製環境をつくり、そこで修正案を試しています")
    publish_step(incident_id, "本番と同じ複製環境をつくり、そこで修正を試します",
                 "複製が本番と同じだと確認できなければ、承認待ちへは進みません",
                 tech_title="検証用環境を複製し一致判定 → 修正案を適用して業務・回帰テスト",
                 tech_detail="§7.4: clone_to_verify → compare_envs → delete_rule → business/forbidden テスト")
    val = tools.validate_plan(plan_body)
    result = val["result"]

    if not result.get("verified"):
        plan["status"] = "validation_failed"
        plan["validation"] = {
            "verified": False, "reason": result.get("reason"),
            "message": result.get("message")}
        db.update_record(plan["id"], plan)
        events.publish("plan", {"incident_id": incident_id, "plan": plan})
        incident.transition(
            incident_id, "NEEDS_HUMAN",
            f"事前検証が不合格のため適用しません: {result.get('message', '')}",
            activity="担当者の判断が必要です（複製環境での確認に合格しなかったため、本番は変更していません）")
        return

    plan["status"] = "validated"
    # 複製環境の手順・変更前後のルールセット全文も保持する（S6: 差別化の核を捨てない）
    plan["validation"] = {
        "verified": True,
        "clone_match": result["clone_match"],
        "pre": {"business": result["clone_tests_pre"]["business"]["pass"],
                "forbidden": result["clone_tests_pre"]["forbidden"]["pass"]},
        "post": {"business": result["clone_tests_post"]["business"]["pass"],
                 "forbidden": result["clone_tests_post"]["forbidden"]["pass"]},
        "applied_in_verify": result.get("applied_in_verify"),
        "diff": result.get("diff"),
        "clone_steps": (result.get("clone") or {}).get("steps"),
        "evidence_id": val["evidence"]["id"],
    }
    db.update_record(plan["id"], plan)
    events.publish("plan", {"incident_id": incident_id, "plan": plan})

    ap = create_request(incident_id, plan)
    incident.transition(
        incident_id, "AWAITING_APPROVAL",
        f"事前検証合格。iPadで承認してください（期限 {ap['expires_at']}）",
        activity=f"複製環境での確認に合格しました。承認をお願いします（{ap['expires_at'][11:19]} まで）")
    publish_step(incident_id, "人の承認を待っています",
                 "変更する場所・実際に流す差分・影響・事前検証の結果・戻し方を承認端末に表示しています",
                 tech_title="承認待ち（AWAITING_APPROVAL）",
                 tech_detail=f"plan {plan['id']}-v{plan['version']} hash={h[:8]} / 期限 {ap['expires_at']}")


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
    incident.set_fields(incident_id, route_label="AIが考えながら調べています",
                        route_detail="OrcaRouter（段階別モデル選択）")
    history: list[dict[str, str]] = []

    # 業務テストと構成図読取は案件受付の定型処理として先に実行
    publish_step(incident_id, "業務通信を実測し、申告のとおりか確かめます",
                 "拠点の業務端末から受注画面へ実際に接続します",
                 tech_title="業務テストで申告内容を確認",
                 tech_detail="test_business: t-client → https://order.example.com/ ×3（独立検証器）")
    biz = tools.test_business()
    business_ok = biz["result"]["pass"]
    incident.set_fields(incident_id,
                        business_status="ok" if business_ok else "down")
    history.append({"tool": "test_business", "summary": biz["evidence"]["summary"]})

    publish_step(incident_id, "構成図をAIが読み取り、登録済みの機器一覧と照合します",
                 "図から読んだ情報は、実測で裏付けるまで確定として扱いません",
                 tech_title="構成図をVLMで構造化し登録機器表と照合",
                 tech_detail="vlm_read_topology（vision + json_schema） → 登録機器表との機械照合")
    topo = vlm.read_topology(incident_id)
    history.append({"tool": "vlm_read_topology",
                    "summary": json.dumps({"source":topo["source"],
                        "nodes":topo["mapped_nodes"], "links":topo["mapped_links"],
                        "comparison":topo["comparison"]}, ensure_ascii=False)})

    proposed: dict[str, Any] | None = None
    # 仮説は本文で同定し、同じ内容を繰り返し提示されても1件として扱う。
    # 各ステップで得た証拠をその仮説へ紐付け、決着したら状態を更新する。
    seen_hypotheses: dict[str, dict[str, Any]] = {}
    current_h: dict[str, Any] | None = None

    for step_no in range(1, 11):  # 判断10ステップ上限（N-04）
        user = _render_history(history)
        resp = gateway.call(incident_id, f"decide-{step_no:02d}", "decide",
                            system=LLM_SYSTEM, user=user,
                            json_schema=DECIDE_SCHEMA,
                            data_class="external_allowed")  # 観測サマリのみ送信（§8）
        if not resp.parsed or not resp.schema_ok:
            raise RuntimeError(f"構造化出力の取得に失敗 (outcome={resp.outcome})")
        d = resp.parsed
        # 画面は「何をするのか」を平易に、技術層に生の action/ノードIDを残す
        if d["action"] == "observe_node":
            plain_title = wording.plain_observe(d["node"] or "gw",
                                                d["aspects"] or ["link", "route"])
        else:
            plain_title = wording.plain_action(d["action"])
        publish_step(incident_id,
                     f"AIの判断{step_no}：{plain_title}",
                     d.get("reason", ""),
                     tech_title=f"decide-{step_no:02d}: {d['action']}",
                     tech_detail=f"node={d['node'] or '-'} aspects={d['aspects']} "
                                 f"src={d['src'] or '-'} dst={d['dst'] or '-'} "
                                 f"kind={d['kind'] or '-'} port={d['port'] or '-'} "
                                 f"rule_comment={d['rule_comment'] or '-'}")
        statement = (d.get("hypothesis_update") or "").strip()
        if statement:
            current_h = seen_hypotheses.get(statement)
            if current_h is None:
                current_h = add_hypothesis(incident_id, statement, "open", [], "")
                seen_hypotheses[statement] = current_h

        res: dict[str, Any] | None = None
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
            # 修正案に到達した＝直近の仮説が証拠で支持された
            if current_h is not None:
                update_hypothesis(incident_id, current_h, "supported", [],
                                  f"修正案の事前検証で確認（{d.get('rule_comment', '')}）")
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
                                        "業務通信の正常を確認。変更は行いません",
                                        activity="業務通信は正常でした。変更は行いません")
                return
            history.append({"tool": "conclude_no_change(却下)",
                            "summary": "業務テストは不合格のまま。調査を継続してください"})

        # 観測で得た証拠を、いま検証中の仮説へ紐付ける（根拠の追跡可能性）
        if current_h is not None and res is not None:
            update_hypothesis(incident_id, current_h, current_h["status"],
                              [res["evidence"]["id"]])

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

def open_handoff(incident_id: str, ap: dict[str, Any]) -> dict[str, Any]:
    """却下を起点に引き継ぎレコードを起票する（M-12 / §14.3）。

    却下は失敗ではなく正常な安全動作なので、そこから次へ進める道をデータとして残す。
    証拠・仮説・計画への参照を持つので、担当交代後も再入力なしで引き継げる。
    """
    plan = db.get_record(ap.get("plan_id", "")) or {}
    rec = db.add_record(incident_id, "handoff", {
        "trigger": "approval_rejected",
        "status": "open",                     # open | accepted | held
        "rejected_by": ap.get("approver"),
        "rejected_at": ap.get("decided_at"),
        "reason": ap.get("reason", ""),       # 人間向けの記録・表示のみ
        "plan_id": ap.get("plan_id"),
        "plan_version": ap.get("plan_version"),
        "plan_hash": ap.get("plan_hash"),
        "plan_title": plan.get("title_plain") or plan.get("title"),
        "evidence_ids": [e["id"] for e in db.list_records(incident_id, "evidence")],
        "hypothesis_ids": [h["id"] for h in db.list_records(incident_id, "hypothesis")],
        "candidates": ["ネットワーク運用担当（一次対応）", "回線事業者の保守窓口"],
        "residual": "承認しなかったため、対象環境は変更していません",
        "notes": [],
    })
    events.publish("handoff", {"incident_id": incident_id, "handoff": rec})
    return rec


def on_approval_decided(incident_id: str, ap: dict[str, Any]) -> None:
    if ap["decision"] == "rejected":
        open_handoff(incident_id, ap)
        incident.transition(
            incident_id, "NEEDS_HUMAN",
            f"承認者({ap['approver']})が却下しました。計画の見直しが必要です",
            activity="担当者の判断が必要です（対象環境は変更していません）")
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
            incident.transition(
                incident_id, "NEEDS_HUMAN",
                "承認対象の計画が検証済み状態ではありません",
                activity="担当者の判断が必要です（承認対象の計画が検証済みではありません）")
            return

        # ---- 適用直前の前提再観測（30秒鮮度、§10.4） ----
        incident.transition(incident_id, "APPLYING",
                            "適用直前の前提を再観測しています（鮮度30秒）",
                            activity="適用の直前に、前提が変わっていないか確認しています")
        publish_step(incident_id, "適用の直前に、前提が変わっていないか確認します",
                     "対象のルールがまだあるか／業務は止まったままか／使っている経路は同じか",
                     tech_title="前提の再観測（鮮度30秒、§10.4）",
                     tech_detail="対象ルールの存在・業務不通・使用経路が承認時と同じか確認")
        r2obs = tools.observe_node("r2", ["nft"])
        nft_text = (r2obs["result"]["observations"]["nft"]["raw"] or {}) \
            .get("stdout", "")
        rule_present = plan["body"]["rule_comment"] in nft_text
        biz_now = tools.test_business()
        business_still_down = not biz_now["result"]["pass"]

        if not rule_present:
            incident.transition(
                incident_id, "NEEDS_HUMAN",
                "前提変化: 対象ルールが既に存在しません。古い計画は適用せず停止します（T-20）",
                activity="担当者の判断が必要です（削除対象のルールが既に無いため、古い計画は適用せず止めました）")
            return
        if not business_still_down:
            publish_step(incident_id,
                         "業務はすでに回復していました。変更は行わず、確認だけ進めます",
                         tech_title="T-20: 前提変化のため適用をスキップ",
                         tech_detail="業務テストが合格したため apply をスキップし VERIFYING へ")
            incident.transition(incident_id, "VERIFYING",
                                "変更なしで独立検証を実行中",
                                activity="何も変更せずに、利用者と同じ通信で確認しています")
            _final_verify(incident_id, tools, applied_change=False)
            return

        # ---- 適用（冪等キー=計画ハッシュ、M-10） ----
        publish_step(incident_id, "承認された1件だけを、本番に適用します",
                     "同じ変更が二重に適用されない仕組みで実行します",
                     tech_title="承認された差分のみを対象環境へ適用",
                     tech_detail=f"計画 v{plan['version']} hash={plan['hash'][:8]}… / "
                                 f"冪等キー(idempotency_key)で二重適用を防止")
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
                            "独立検証器で業務テストと回帰テストを実行中",
                            activity="利用者と同じ通信で、復旧したかを確認しています")
        _final_verify(incident_id, tools, applied_change=True,
                      execution_id=apply_res["result"]["execution_id"])
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        incident.transition(
            incident_id, "NEEDS_HUMAN",
            f"適用処理が失敗しました: {type(exc).__name__}: {str(exc)[:200]}",
            activity="担当者の判断が必要です（適用処理を最後まで完了できませんでした）")
    finally:
        tools.close()


def _final_verify(incident_id: str, tools: ToolBelt, applied_change: bool,
                  execution_id: str | None = None) -> None:
    publish_step(incident_id,
                 "利用者と同じ通信で、業務が使えるかを3回続けて確認します",
                 "あわせて、止めるべき通信が止まったままかも確認します",
                 tech_title="業務テスト（3回連続）と禁止通信テストを実行",
                 tech_detail="独立検証器: test_business ×3 / test_forbidden(telnet:23)")
    biz = tools.test_business()
    forb = tools.test_forbidden()
    if biz["result"]["pass"] and forb["result"]["pass"]:
        incident.set_fields(incident_id, business_status="ok")
        _finish_restored_with_residual(incident_id, tools,
                                       applied_change=applied_change)
    else:
        if applied_change and execution_id:
            incident.transition(incident_id, "ROLLING_BACK",
                                "検証不合格のため登録済みの復元を実行します",
                                activity="確認に合格しなかったため、適用前の状態へ戻しています")
            tools.rollback_plan(execution_id)
        incident.transition(
            incident_id, "NEEDS_HUMAN",
            "適用後検証が不合格でした。復元を実施し、未復旧として引き継ぎます",
            activity="担当者の判断が必要です（確認に合格しなかったため元に戻しました。業務は未復旧です）")


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
            "主回線の断線が未復旧",
            "業務は予備回線で暫定的に復旧しています。主回線は物理的な断線のため、"
            "ソフトウェアの操作では直せません",
            "回線事業者の保守窓口（担当候補）",
            "現地保守の手配と回線の試験を依頼します。直り次第、機器が自動で主回線へ戻ります")
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
    incident.transition(incident_id, "SERVICE_RESTORED", note,
                        activity="業務が復旧しました"
                        + ("（主回線の対応は継続中です）" if r1_down else ""))
    publish_step(
        incident_id,
        "業務が復旧しました",
        ("承認された修正を適用した結果、" if applied_change else "機器の自動切替により、")
        + "業務通信が3回続けて成功し、止めるべき通信は止まったままであることを確認しました"
        + ("。主回線の断線は、担当部署へ引き継ぐ課題として記録済みです" if r1_down else ""),
        tech_title="SERVICE_RESTORED: 業務通信は回復",
        tech_detail=("applied_change=%s / business 3/3 pass / forbidden blocked%s"
                     % (applied_change,
                        " / residual: 主回線リンク断" if r1_down else "")))
