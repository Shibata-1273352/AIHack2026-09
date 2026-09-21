"""NetWalker シミュレータ制御API (:9000)。

- /agent/*  … 診断エージェントに許可された読取・検査・計画操作（型付き、ホワイトリスト）
- /admin/*  … 障害注入・初期化・正解参照（エージェントからは不可視。バックエンドの
              デモ運転席だけが呼ぶ）

設計原則:
- LLM が生成した任意コマンドは実行しない。操作は全て型と範囲を検証した
  アダプタ経由（要件 §10.3）。
- 修正操作のホワイトリスト: node=r2 / table=fw / chain=forward の nft ルール削除のみ。
  comment が POLICY-* のルール削除・flush・policy 変更は拒否する（M-18）。
- 正解情報（注入状態）は /admin/ground_truth のみが返す。/agent/* は実観測だけを返す。
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="netwalker-sim-ctl")

RUN = Path("/run/netwalker")
OPT = Path("/opt/netwalker")
CERT = "/etc/netwalker/certs/server.crt"

NODES = ("client", "gw", "r1", "r2", "srv")
ENV_PREFIX = {"target": "t-", "verify": "v-"}

# probe の宛先ホワイトリスト（登録済み対象のみ、§10.3）
PROBE_DSTS = {
    "order.example.com", "10.0.100.10",
    "10.0.1.1", "10.0.2.2", "10.0.3.2", "10.0.4.2", "10.0.5.2",
    "10.0.4.1", "10.0.5.1",
}
PROBE_PORTS = {443, 23, 80}

EXEC_DB = RUN / "executions.json"


# ---------------------------------------------------------------- utilities

def sh(cmd: list[str], timeout: float = 5.0, input_text: str | None = None) -> dict[str, Any]:
    """コマンド実行の共通ラッパ。生出力を証拠としてそのまま返す（N-04: 1ツール5秒）。"""
    started = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, input=input_text)
        return {
            "cmd": " ".join(cmd),
            "rc": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr,
            "ms": int((time.time() - started) * 1000),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    except subprocess.TimeoutExpired:
        return {
            "cmd": " ".join(cmd), "rc": -1, "stdout": "", "stderr": "timeout",
            "ms": int((time.time() - started) * 1000),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }


def nsx(prefix: str, node: str, *args: str) -> list[str]:
    return ["ip", "netns", "exec", f"{prefix}{node}", *args]


def env_prefix(env: str) -> str:
    if env not in ENV_PREFIX:
        raise HTTPException(422, f"env must be target|verify, got {env}")
    return ENV_PREFIX[env]


def check_node(node: str) -> str:
    if node not in NODES:
        raise HTTPException(422, f"unknown node: {node}")
    return node


def load_execs() -> dict[str, Any]:
    if EXEC_DB.exists():
        return json.loads(EXEC_DB.read_text())
    return {}


def save_execs(d: dict[str, Any]) -> None:
    EXEC_DB.write_text(json.dumps(d, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- observations

def obs_link(prefix: str, node: str) -> dict[str, Any]:
    # tunl0/gre0 などカーネル既定のデバイスは検査対象外（eth-* のみが登録リンク）
    raw = sh(["ip", "-n", f"{prefix}{node}", "-br", "link", "show"])
    raw["stdout"] = "\n".join(
        ln for ln in raw["stdout"].splitlines()
        if ln.startswith("eth-") or ln.startswith("lo"))
    js = sh(["ip", "-n", f"{prefix}{node}", "-j", "link", "show"])
    parsed = []
    try:
        for it in json.loads(js["stdout"] or "[]"):
            name = it.get("ifname") or ""
            if not (name.startswith("eth-") or name == "lo"):
                continue
            parsed.append({
                "ifname": name,
                "operstate": it.get("operstate"),
                "admin_up": "UP" in (it.get("flags") or []),
            })
    except json.JSONDecodeError:
        pass
    return {"raw": raw, "parsed": parsed}


def obs_route(prefix: str, node: str) -> dict[str, Any]:
    raw = sh(["ip", "-n", f"{prefix}{node}", "route", "show"])
    return {"raw": raw, "parsed": sorted(raw["stdout"].strip().splitlines())}


def obs_addr(prefix: str, node: str) -> dict[str, Any]:
    raw = sh(["ip", "-n", f"{prefix}{node}", "-br", "addr", "show"])
    return {"raw": raw}


def obs_nft(prefix: str, node: str) -> dict[str, Any]:
    if node not in ("r1", "r2"):
        return {"raw": None, "note": "nft は経路ノード(r1/r2)のみ"}
    raw = sh(nsx(prefix, node, "nft", "-a", "list", "ruleset"))
    return {"raw": raw}


def obs_listen(prefix: str, node: str) -> dict[str, Any]:
    raw = sh(nsx(prefix, node, "ss", "-tln"))
    return {"raw": raw}


def obs_failover(prefix: str, node: str) -> dict[str, Any]:
    """登録済み冗長化制御の状態（対象環境のみ、gw で観測可能とする）。"""
    if prefix != "t-" or node != "gw":
        return {"raw": None, "note": "冗長化制御は対象環境の gw のみ"}
    f = RUN / "t-failover.json"
    log = RUN / "t-failover.log"
    return {
        "state": json.loads(f.read_text()) if f.exists() else None,
        "log_tail": log.read_text().splitlines()[-10:] if log.exists() else [],
    }


ASPECTS = {
    "link": obs_link,
    "route": obs_route,
    "addr": obs_addr,
    "nft": obs_nft,
    "listen": obs_listen,
    "failover": obs_failover,
}


class ObserveReq(BaseModel):
    env: Literal["target", "verify"] = "target"
    node: str
    aspects: list[str] = Field(default_factory=lambda: ["link", "route"])


@app.post("/agent/observe_node")
def observe_node(req: ObserveReq) -> dict[str, Any]:
    prefix = env_prefix(req.env)
    node = check_node(req.node)
    out: dict[str, Any] = {"env": req.env, "node": node,
                           "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    results = {}
    for a in req.aspects:
        if a not in ASPECTS:
            raise HTTPException(422, f"unknown aspect: {a}")
        results[a] = ASPECTS[a](prefix, node)
    out["observations"] = results
    return out


class ProbeReq(BaseModel):
    env: Literal["target", "verify"] = "target"
    src: Literal["client", "gw"] = "client"
    dst: str
    kind: Literal["ping", "tcp", "https"]
    port: int | None = None


@app.post("/agent/probe_path")
def probe_path(req: ProbeReq) -> dict[str, Any]:
    prefix = env_prefix(req.env)
    if req.dst not in PROBE_DSTS:
        raise HTTPException(422, f"宛先が許可範囲外です: {req.dst}")
    if req.port is not None and req.port not in PROBE_PORTS:
        raise HTTPException(422, f"ポートが許可範囲外です: {req.port}")

    if req.kind == "ping":
        r = sh(nsx(prefix, req.src, "ping", "-c", "2", "-W", "1", req.dst), timeout=5)
        ok = r["rc"] == 0
    elif req.kind == "tcp":
        port = req.port or 443
        code = (
            "import socket,sys\n"
            "s=socket.socket()\n"
            "s.settimeout(2)\n"
            f"rc=s.connect_ex(('{req.dst}',{port}))\n"
            "print('CONNECTED' if rc==0 else f'FAILED errno={rc}')\n"
            "sys.exit(0 if rc==0 else 1)\n"
        )
        r = sh(nsx(prefix, req.src, "python3", "-c", code), timeout=5)
        ok = r["rc"] == 0
    else:  # https
        r = sh(nsx(prefix, req.src, "curl", "-sS", "--max-time", "3",
                   "--cacert", CERT, "-o", "/dev/null",
                   "-w", "%{http_code} %{time_total}s",
                   f"https://{req.dst}/"), timeout=5)
        ok = r["rc"] == 0 and r["stdout"].startswith("200")

    return {"env": req.env, "src": req.src, "dst": req.dst, "kind": req.kind,
            "port": req.port, "ok": ok, "raw": r}


# ---------------------------------------------------------------- tests (独立検証器)

def run_business_test(prefix: str) -> dict[str, Any]:
    """業務テスト: client から HTTPS で受注画面を3回取得。全て 200+マーカーで合格。"""
    attempts = []
    for i in range(3):
        r = sh(nsx(prefix, "client", "curl", "-sS", "--max-time", "3",
                   "--connect-timeout", "1",
                   "--cacert", CERT, "-w", "\n%{http_code} %{time_total}",
                   "https://order.example.com/"), timeout=5)
        body, _, tail = r["stdout"].rpartition("\n")
        http_code = tail.split(" ")[0] if tail else ""
        ok = r["rc"] == 0 and http_code == "200" and "NETWALKER-ORDER-OK" in body
        attempts.append({
            "attempt": i + 1, "ok": ok, "http_code": http_code,
            "ms": r["ms"], "at": r["at"],
            "error": r["stderr"].strip() or None,
            "body_excerpt": body[:200],
        })
    passed = all(a["ok"] for a in attempts)
    return {"test": "business_https", "target": "https://order.example.com/",
            "pass": passed, "attempts": attempts,
            "criteria": "3回連続で HTTP 200 かつ NETWALKER-ORDER-OK を含む"}


def run_forbidden_test(prefix: str) -> dict[str, Any]:
    """禁止通信テスト: telnet(23) が遮断されていることを確認。接続できたら不合格。"""
    code = (
        "import socket\n"
        "s=socket.socket()\n"
        "s.settimeout(1.5)\n"
        "rc=s.connect_ex(('10.0.100.10',23))\n"
        "print('CONNECTED' if rc==0 else f'BLOCKED errno={rc}')\n"
    )
    r = sh(nsx(prefix, "client", "python3", "-c", code), timeout=5)
    blocked = "CONNECTED" not in r["stdout"]
    return {"test": "forbidden_telnet", "target": "10.0.100.10:23",
            "pass": blocked, "raw": r,
            "criteria": "telnet(23) への接続がタイムアウト/拒否されること（遮断維持）"}


class TestReq(BaseModel):
    env: Literal["target", "verify"] = "target"


@app.post("/agent/test/business")
def test_business(req: TestReq) -> dict[str, Any]:
    return run_business_test(env_prefix(req.env))


@app.post("/agent/test/forbidden")
def test_forbidden(req: TestReq) -> dict[str, Any]:
    return run_forbidden_test(env_prefix(req.env))


# ---------------------------------------------------------------- plan (修正案)

class Plan(BaseModel):
    action: Literal["delete_nft_rule"]
    node: str
    table: str
    chain: str
    rule_comment: str


def check_plan(plan: Plan) -> None:
    """修正のホワイトリスト（M-18）。ここを通らない変更は実行しない。"""
    if plan.node != "r2":
        raise HTTPException(403, f"変更が許可されているのは r2 のみです: {plan.node}")
    if plan.table != "fw" or plan.chain != "forward":
        raise HTTPException(403, "変更が許可されているのは table=fw chain=forward のみです")
    if plan.rule_comment.startswith("POLICY-"):
        raise HTTPException(403,
                            "POLICY-* ルールの削除は禁止です（正当な遮断ポリシーの全面解除に相当）")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", plan.rule_comment):
        raise HTTPException(422, "rule_comment の形式が不正です")


def find_rule(prefix: str, plan: Plan) -> dict[str, Any] | None:
    """comment でルールを特定し handle と原文を返す。"""
    r = sh(nsx(prefix, plan.node, "nft", "-a", "list", "chain",
               "inet", plan.table, plan.chain))
    if r["rc"] != 0:
        raise HTTPException(500, f"nft 参照に失敗: {r['stderr']}")
    for line in r["stdout"].splitlines():
        if f'comment "{plan.rule_comment}"' in line:
            m = re.search(r"# handle (\d+)", line)
            if m:
                return {"handle": int(m.group(1)), "text": line.strip()}
    return None


def delete_rule(prefix: str, plan: Plan) -> dict[str, Any]:
    rule = find_rule(prefix, plan)
    if rule is None:
        raise HTTPException(404,
                            f"comment={plan.rule_comment} のルールが {plan.node} に存在しません")
    pre = sh(nsx(prefix, plan.node, "nft", "list", "ruleset"))
    r = sh(nsx(prefix, plan.node, "nft", "delete", "rule", "inet",
               plan.table, plan.chain, "handle", str(rule["handle"])))
    if r["rc"] != 0:
        raise HTTPException(500, f"ルール削除に失敗: {r['stderr']}")
    post = sh(nsx(prefix, plan.node, "nft", "list", "ruleset"))
    return {"deleted_rule": rule["text"], "pre_ruleset": pre["stdout"],
            "post_ruleset": post["stdout"], "raw": r}


# ---------------------------------------------------------------- clone & compare

def collect_state(prefix: str) -> dict[str, Any]:
    """正規化した環境状態（一致判定・diff 用）。"""
    state: dict[str, Any] = {"links": {}, "routes": {}, "nft": {}, "listen": {}}
    for node in NODES:
        js = sh(["ip", "-n", f"{prefix}{node}", "-j", "link", "show"])
        links = {}
        try:
            for it in json.loads(js["stdout"] or "[]"):
                name = it.get("ifname") or ""
                if not name.startswith("eth-"):
                    continue
                links[name] = {
                    "admin_up": "UP" in (it.get("flags") or []),
                    "operstate": it.get("operstate"),
                }
        except json.JSONDecodeError:
            pass
        state["links"][node] = links
        rt = sh(["ip", "-n", f"{prefix}{node}", "route", "show"])
        state["routes"][node] = sorted(rt["stdout"].strip().splitlines())
    for node in ("r1", "r2"):
        nf = sh(nsx(prefix, node, "nft", "list", "ruleset"))
        state["nft"][node] = nf["stdout"].strip()
    ssout = sh(nsx(prefix, "srv", "ss", "-tln"))
    ports = sorted(re.findall(r":(\d+)\s", ssout["stdout"]))
    state["listen"]["srv"] = ports
    return state


def clone_to_verify() -> dict[str, Any]:
    """対象環境の状態を検証用環境へリプレイする（§7.4）。

    アドレス・ifname は t-/v- で共通設計のため、リンク状態・経路・nft を
    そのまま再適用できる。冗長化制御デーモンは動かさない（経路は静的リプレイ）。
    """
    steps: list[dict[str, Any]] = []
    r = sh(["bash", str(OPT / "topo.sh"), "create", "v-"], timeout=30)
    steps.append({"step": "topo_create", "rc": r["rc"], "stderr": r["stderr"][-500:]})
    if r["rc"] != 0:
        raise HTTPException(500, f"検証用環境の作成に失敗: {r['stderr']}")

    tgt = collect_state("t-")

    # 1) リンク admin down のリプレイ
    for node, links in tgt["links"].items():
        for ifname, st in links.items():
            if not st["admin_up"]:
                sh(["ip", "-n", f"v-{node}", "link", "set", ifname, "down"])
                steps.append({"step": f"link_down v-{node}/{ifname}"})

    # 2) 経路のリプレイ（gw の サービス経路 / srv の戻り経路）
    for node in ("gw", "srv"):
        for line in tgt["routes"][node]:
            parts = line.split()
            if not parts:
                continue
            r = sh(["ip", "-n", f"v-{node}", "route", "replace", *parts])
            if r["rc"] != 0:
                steps.append({"step": f"route_replace v-{node}: {line}", "rc": r["rc"]})

    # 3) nft ルールセットのリプレイ
    for node in ("r1", "r2"):
        ruleset = tgt["nft"][node]
        sh(nsx("v-", node, "nft", "flush", "ruleset"))
        r = sh(nsx("v-", node, "nft", "-f", "-"), input_text=ruleset + "\n")
        steps.append({"step": f"nft_replay v-{node}", "rc": r["rc"],
                      "stderr": r["stderr"][-300:]})

    # 4) サービス起動
    r = sh(["bash", str(OPT / "start-services.sh"), "v-"], timeout=30)
    steps.append({"step": "services", "rc": r["rc"], "stderr": r["stderr"][-500:]})
    return {"steps": steps}


def compare_envs() -> dict[str, Any]:
    """対象環境と検証用環境の一致判定（正規化JSON比較、§7.4）。"""
    t = collect_state("t-")
    v = collect_state("v-")
    mismatches: list[str] = []

    for node in NODES:
        for ifname, st in t["links"].get(node, {}).items():
            vst = v["links"].get(node, {}).get(ifname)
            if vst is None:
                mismatches.append(f"links: {node}/{ifname} が検証用環境に存在しない")
            elif (st["admin_up"], st["operstate"]) != (vst["admin_up"], vst["operstate"]):
                mismatches.append(
                    f"links: {node}/{ifname} 状態不一致 target={st} verify={vst}")
        if t["routes"].get(node) != v["routes"].get(node):
            mismatches.append(f"routes: {node} の経路が不一致")
    for node in ("r1", "r2"):
        if t["nft"][node] != v["nft"][node]:
            mismatches.append(f"nft: {node} のルールセットが不一致")
    if t["listen"]["srv"] != v["listen"]["srv"]:
        mismatches.append(
            f"listen: srv のリスニングポート不一致 target={t['listen']['srv']} verify={v['listen']['srv']}")

    # 通信テストの結果も一致条件に含める（§7.4 3.）
    checks = {
        "business_target": run_business_test("t-")["pass"],
        "business_verify": run_business_test("v-")["pass"],
        "forbidden_target": run_forbidden_test("t-")["pass"],
        "forbidden_verify": run_forbidden_test("v-")["pass"],
    }
    if checks["business_target"] != checks["business_verify"]:
        mismatches.append("tests: 業務テストの結果が対象環境と検証用環境で不一致")
    if checks["forbidden_target"] != checks["forbidden_verify"]:
        mismatches.append("tests: 禁止通信テストの結果が不一致")

    return {"match": not mismatches, "mismatches": mismatches,
            "tests": checks, "target": t, "verify": v}


class ValidateReq(BaseModel):
    plan: Plan


@app.post("/agent/plan/validate")
def plan_validate(req: ValidateReq) -> dict[str, Any]:
    """検証用環境を複製→一致確認→修正適用→業務・回帰テスト（§7.4）。"""
    check_plan(req.plan)
    # 対象環境に該当ルールが実在することを先に確認
    rule = find_rule("t-", req.plan)
    if rule is None:
        raise HTTPException(404, "対象のルールが対象環境に存在しません")

    clone = clone_to_verify()
    cmp_before = compare_envs()
    if not cmp_before["match"]:
        return {"verified": False, "reason": "clone_mismatch",
                "clone": clone, "compare": {
                    "match": False, "mismatches": cmp_before["mismatches"]},
                "message": "検証用環境が対象環境と一致しないため検証を中止しました"}

    # 修正前のテスト結果は一致判定で実測済みのものを使う（重複実行しない）
    pre_business = {"pass": cmp_before["tests"]["business_verify"],
                    "note": "一致判定時に実測（対象環境と同一の結果）"}
    pre_forbidden = {"pass": cmp_before["tests"]["forbidden_verify"],
                     "note": "一致判定時に実測"}

    result = delete_rule("v-", req.plan)

    post_business = run_business_test("v-")
    post_forbidden = run_forbidden_test("v-")

    verified = (post_business["pass"] and post_forbidden["pass"])
    return {
        "verified": verified,
        "clone_match": True,
        "clone_tests_pre": {"business": pre_business, "forbidden": pre_forbidden},
        "applied_in_verify": {"deleted_rule": result["deleted_rule"]},
        "diff": {"pre": result["pre_ruleset"], "post": result["post_ruleset"]},
        "clone_tests_post": {"business": post_business, "forbidden": post_forbidden},
        "message": ("検証用環境で業務テスト合格・禁止通信の遮断維持を確認"
                    if verified else "検証用環境でのテストが不合格です"),
    }


class ApplyReq(BaseModel):
    plan: Plan
    idempotency_key: str


@app.post("/agent/plan/apply")
def plan_apply(req: ApplyReq) -> dict[str, Any]:
    """対象環境への適用。冪等キーで二重適用を防ぎ、適用前状態を永続化する（M-10）。"""
    check_plan(req.plan)
    execs = load_execs()
    if req.idempotency_key in execs:
        prev = execs[req.idempotency_key]
        return {**prev, "idempotent_replay": True}

    result = delete_rule("t-", req.plan)
    record = {
        "execution_id": str(uuid.uuid4())[:8],
        "idempotency_key": req.idempotency_key,
        "plan": req.plan.model_dump(),
        "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "deleted_rule": result["deleted_rule"],
        "pre_ruleset": result["pre_ruleset"],
        "post_ruleset": result["post_ruleset"],
        "rolled_back": False,
    }
    execs[req.idempotency_key] = record
    save_execs(execs)
    return record


class RollbackReq(BaseModel):
    execution_id: str


@app.post("/agent/plan/rollback")
def plan_rollback(req: RollbackReq) -> dict[str, Any]:
    """適用前状態への復元（保存済み ruleset の再ロード）。"""
    execs = load_execs()
    target = None
    for rec in execs.values():
        if rec["execution_id"] == req.execution_id:
            target = rec
            break
    if target is None:
        raise HTTPException(404, "execution_id が見つかりません")
    node = target["plan"]["node"]
    sh(nsx("t-", node, "nft", "flush", "ruleset"))
    r = sh(nsx("t-", node, "nft", "-f", "-"), input_text=target["pre_ruleset"] + "\n")
    if r["rc"] != 0:
        raise HTTPException(500, f"復元に失敗: {r['stderr']}")
    target["rolled_back"] = True
    save_execs(execs)
    return {"execution_id": req.execution_id, "restored": True,
            "ruleset": sh(nsx("t-", node, "nft", "list", "ruleset"))["stdout"]}


# ---------------------------------------------------------------- admin (注入・初期化)

@app.post("/admin/inject/fault_a")
def inject_fault_a() -> dict[str, Any]:
    """障害A: 主回線リンク断（r1 側を落とす → gw 側は LOWERLAYERDOWN に見える）。"""
    r = sh(["ip", "-n", "t-r1", "link", "set", "eth-gw", "down"])
    if r["rc"] != 0:
        raise HTTPException(500, r["stderr"])
    return {"injected": "fault_a", "detail": "t-r1 eth-gw down（主回線リンク断）"}


@app.post("/admin/inject/fault_b")
def inject_fault_b() -> dict[str, Any]:
    """障害B: 予備経路 r2 の ACL 誤設定（拠点→受注サービスの HTTPS を遮断）。"""
    cur = sh(nsx("t-", "r2", "nft", "list", "chain", "inet", "fw", "forward"))
    if "BAD-ACL-443" in cur["stdout"]:
        return {"injected": "fault_b", "detail": "既に注入済み"}
    r = sh(nsx("t-", "r2", "nft", "insert", "rule", "inet", "fw", "forward",
               "ip", "saddr", "10.0.1.0/24", "ip", "daddr", "10.0.100.10",
               "tcp", "dport", "443", "drop", "comment", "BAD-ACL-443"))
    if r["rc"] != 0:
        raise HTTPException(500, r["stderr"])
    return {"injected": "fault_b",
            "detail": "t-r2 nft forward に BAD-ACL-443 (HTTPS drop) を追加"}


@app.post("/admin/reset")
def admin_reset() -> dict[str, Any]:
    r = sh(["bash", str(OPT / "reset.sh")], timeout=60)
    if r["rc"] != 0:
        raise HTTPException(500, f"reset failed: {r['stderr']}")
    if EXEC_DB.exists():
        EXEC_DB.unlink()
    return {"reset": True, "log": r["stdout"].splitlines()[-5:]}


@app.post("/admin/verify_env/create")
def admin_verify_create() -> dict[str, Any]:
    return clone_to_verify()


@app.get("/admin/compare")
def admin_compare() -> dict[str, Any]:
    return compare_envs()


@app.get("/admin/pulse")
def admin_pulse() -> dict[str, Any]:
    """軽量テレメトリ（UI のライブ演出用）。/agent/* ではないためエージェント不可視（§7.3）。

    curl 1回 + failover 状態ファイル読取のみ。2秒周期ポーリングに耐える軽さに保つ。
    """
    r = sh(nsx("t-", "client", "curl", "-s", "-o", "/dev/null",
               "--connect-timeout", "0.5", "--max-time", "1.5",
               "--cacert", CERT, "-w", "%{http_code}",
               "https://order.example.com/"), timeout=3)
    business_ok = r["rc"] == 0 and r["stdout"].strip() == "200"
    fstate = RUN / "t-failover.json"
    state = None
    if fstate.exists():
        try:
            state = json.loads(fstate.read_text())
        except json.JSONDecodeError:
            state = None
    return {
        "business_ok": business_ok,
        "active_path": (state or {}).get("active_path", "r1"),
        "primary_link_up": (state or {}).get("primary_link_up"),
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


@app.get("/admin/ground_truth")
def ground_truth() -> dict[str, Any]:
    """正解情報（評価系のみ参照。診断エージェントへは渡さない）。"""
    js = sh(["ip", "-n", "t-r1", "-j", "link", "show", "eth-gw"])
    fault_a = False
    try:
        it = json.loads(js["stdout"])[0]
        fault_a = "UP" not in (it.get("flags") or [])
    except (json.JSONDecodeError, IndexError):
        pass
    nft = sh(nsx("t-", "r2", "nft", "list", "chain", "inet", "fw", "forward"))
    fault_b = "BAD-ACL-443" in nft["stdout"]
    fstate = RUN / "t-failover.json"
    failover = json.loads(fstate.read_text()) if fstate.exists() else None
    return {"fault_a_active": fault_a, "fault_b_active": fault_b,
            "failover": failover,
            "business": run_business_test("t-")["pass"]}


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    ns = sh(["ip", "netns", "list"])
    have_t = all(f"t-{n}" in ns["stdout"] for n in NODES)
    return {"ok": have_t, "netns": ns["stdout"].splitlines(),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
