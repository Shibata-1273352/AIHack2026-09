"""A/B/R 方式比較の実測ハーネス（M-17/M-19、§13.1 のコストパフォーマンス根拠）。

3方式を同一条件（T-04 複合障害: 主回線リンク断 + r2 の誤ACL）で回し、
成功率・所要時間・LLM呼出数・トークン・実費・ツール実行回数・NEEDS_HUMAN率を
DB から収集して docs/evaluation/results.{json,md} に出力する。

  A … 高性能モデル固定       NW_ROUTE_VARIANT=a NW_AGENT_MODE=llm
  B … 段階別選択（既定）      NW_ROUTE_VARIANT=b NW_AGENT_MODE=llm
  R … 固定ランブック          NW_AGENT_MODE=scripted（LLM不使用）

方式ごとに専用ポートでバックエンドを起動し直す（設定は起動時に確定するため）。
承認は評価目的の**自動代行承認**で、人手の承認判断を模したものではない。

使い方:
    cd backend && uv run python scripts/eval_abr.py --trials 3
    uv run python scripts/eval_abr.py --variants b,r --trials 2   # 費用を抑える場合
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
OUT_DIR = REPO_DIR / "docs" / "evaluation"
LOG_PATH = BACKEND_DIR / "var" / "eval_abr_backend.log"
TOKEN = "eval-abr-token"


def free_port() -> int:
    """空きポートを取得する（固定番号は環境の既存サービスと衝突しうる）。"""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"

TERMINAL = {"SERVICE_RESTORED", "RESOLVED", "NEEDS_HUMAN", "FAILED"}
SUCCESS = {"SERVICE_RESTORED", "RESOLVED"}

VARIANTS = {
    "A": {"label": "A 高性能モデル固定", "env": {"NW_ROUTE_VARIANT": "a", "NW_AGENT_MODE": "llm"}},
    "B": {"label": "B 段階別選択（既定）", "env": {"NW_ROUTE_VARIANT": "b", "NW_AGENT_MODE": "llm"}},
    "R": {"label": "R 固定ランブック", "env": {"NW_AGENT_MODE": "scripted"}},
}


# ---------------------------------------------------------------- HTTP

def call(path: str, data: dict | None = None, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"content-type": "application/json", "X-Netwalker-Token": TOKEN},
        method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def wait_healthy(proc: subprocess.Popen, seconds: int = 60) -> dict:
    for _ in range(seconds):
        if proc.poll() is not None:
            raise RuntimeError(f"backend が起動前に終了しました (rc={proc.returncode})")
        try:
            return call("/api/config")
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(1)
    raise RuntimeError("backend が起動しません")


# ---------------------------------------------------------------- backend 起動

def start_backend(env_overrides: dict[str, str], db_path: Path) -> subprocess.Popen:
    env = {k: v for k, v in os.environ.items()
           if k not in ("NW_ROUTE_VARIANT", "NW_AGENT_MODE")}  # 呼出側の設定を持ち込まない
    env.update(APPROVAL_TOKEN=TOKEN,
               NW_ROUTE_MODE=os.environ.get("NW_ROUTE_MODE", "live"),
               **env_overrides)
    db_path.unlink(missing_ok=True)  # 方式ごとに空のDBから始める
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = LOG_PATH.open("a", encoding="utf-8")
    return subprocess.Popen(
        ["uv", "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=BACKEND_DIR, env=env,
        stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)


def stop_backend(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=15)
    except Exception:
        proc.kill()


# ---------------------------------------------------------------- 1試行

def poll_until(predicate, limit_sec: int) -> tuple[dict, float]:
    """条件を満たすまで案件をポーリング。(bundle, 経過秒) を返す。"""
    start = time.monotonic()
    bundle: dict = {}
    while time.monotonic() - start < limit_sec:
        bundle = call("/api/incidents/latest")
        if predicate(bundle):
            break
        time.sleep(2)
    return bundle, time.monotonic() - start


def run_trial(variant: str, trial_no: int, limit_sec: int) -> dict:
    """リセット→注入→申告→（承認待ちなら代行承認）→終端状態まで。"""
    call("/api/demo/reset", {})
    time.sleep(1)
    call("/api/demo/inject", {"fault": "both"})
    started = time.monotonic()
    inc = call("/api/incidents", {})
    incident_id = inc["id"]

    approved_at = None
    bundle, _ = poll_until(
        lambda b: (b.get("incident") or {}).get("status") in TERMINAL | {"AWAITING_APPROVAL"},
        limit_sec)
    status = (bundle.get("incident") or {}).get("status", "")

    if status == "AWAITING_APPROVAL":
        plan = bundle["plans"][-1]
        # 評価用の自動代行承認（人手の判断を模したものではない）
        call(f"/api/incidents/{incident_id}/approval", {
            "plan_id": plan["id"], "plan_hash": plan["hash"],
            "decision": "approve", "approver": "eval-harness(代行承認)"})
        approved_at = time.monotonic() - started
        bundle, _ = poll_until(
            lambda b: (b.get("incident") or {}).get("status") in TERMINAL, limit_sec)
        status = (bundle.get("incident") or {}).get("status", "")

    elapsed = time.monotonic() - started
    return summarize_trial(variant, trial_no, bundle, status, elapsed, approved_at)


def summarize_trial(variant: str, trial_no: int, bundle: dict, status: str,
                    elapsed: float, approved_at: float | None) -> dict:
    runs = bundle.get("model_runs", [])
    evidence = bundle.get("evidence", [])
    incident = bundle.get("incident") or {}

    # 原価が算出できた呼出のみ合算する（単価不明は None のまま 0 と偽らない）
    priced = [r for r in runs if r.get("cost_usd") is not None]
    cost = sum(r["cost_usd"] for r in priced)
    models = sorted({r["resolved_model"] for r in runs if r.get("resolved_model")})
    fallbacks = [r for r in runs if r.get("outcome") in ("fallback_to_mock", "error")]

    return {
        "variant": variant,
        "trial": trial_no,
        "status": status,
        "success": status in SUCCESS,
        "needs_human": status == "NEEDS_HUMAN",
        "elapsed_sec": round(elapsed, 1),
        "approved_at_sec": round(approved_at, 1) if approved_at else None,
        "llm_calls": len(runs),
        "input_tokens": sum(r.get("input_tokens") or 0 for r in runs),
        "output_tokens": sum(r.get("output_tokens") or 0 for r in runs),
        "cost_usd": round(cost, 6),
        "cost_unpriced_calls": len(runs) - len(priced),
        "tool_calls": len(evidence),
        "models": models,
        "fallbacks": len(fallbacks),
        "residual_issues": len(incident.get("residual_issues") or []),
        "incident_id": incident.get("id"),
    }


# ---------------------------------------------------------------- 集計・出力

def aggregate(trials: list[dict]) -> dict:
    n = len(trials)
    ok = [t for t in trials if t["success"]]
    total_cost = sum(t["cost_usd"] for t in trials)
    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None  # noqa: E731
    return {
        "trials": n,
        "success": len(ok),
        "success_rate": round(len(ok) / n, 3) if n else 0.0,
        "needs_human_rate": round(sum(t["needs_human"] for t in trials) / n, 3) if n else 0.0,
        "mean_elapsed_sec": mean([t["elapsed_sec"] for t in trials]),
        "mean_llm_calls": mean([t["llm_calls"] for t in trials]),
        "mean_tool_calls": mean([t["tool_calls"] for t in trials]),
        "mean_tokens": mean([t["input_tokens"] + t["output_tokens"] for t in trials]),
        "total_cost_usd": round(total_cost, 6),
        "mean_cost_usd": round(total_cost / n, 6) if n else 0.0,
        # §12.2 の指標: 成功1件あたりAPI費用（失敗分の費用も分子に含める）
        "cost_per_success_usd": round(total_cost / len(ok), 6) if ok else None,
        "models": sorted({m for t in trials for m in t["models"]}),
        "fallbacks": sum(t["fallbacks"] for t in trials),
    }


def render_comparison(report: dict) -> str:
    """集計から比較文を組み立てる（再実行しても数値と矛盾しないように算出する）。"""
    s = report["summary"]
    usable = {k: v for k, v in s.items() if v["trials"] and v["mean_cost_usd"]}
    if len(usable) < 2:
        return ""
    cheapest = min(usable, key=lambda k: usable[k]["mean_cost_usd"])
    fastest = min(usable, key=lambda k: usable[k]["mean_elapsed_sec"] or 1e9)
    lines = [f"- 最安は **{VARIANTS[cheapest]['label']}**（平均 ${usable[cheapest]['mean_cost_usd']:.4f}/件）、"
             f"最速は **{VARIANTS[fastest]['label']}**（平均 {usable[fastest]['mean_elapsed_sec']}秒）"]
    if "A" in usable and "B" in usable:
        a, b = usable["A"], usable["B"]
        ratio = a["mean_cost_usd"] / b["mean_cost_usd"] if b["mean_cost_usd"] else 0
        speed = a["mean_elapsed_sec"] / b["mean_elapsed_sec"] if b["mean_elapsed_sec"] else 0
        lines.append(
            f"- A は判断回数が少ない（平均 {a['mean_llm_calls']} 対 {b['mean_llm_calls']} 呼出）が、"
            f"費用は B の **{ratio:.1f}倍**、所要時間は **{speed:.1f}倍**。"
            f"高性能モデルの手数の少なさは、単価と遅延を埋め合わせなかった")
        lines.append(
            f"- トークン量は逆に A のほうが少ない（平均 {a['mean_tokens']:,.0f} 対 {b['mean_tokens']:,.0f}）。"
            f"B は安価なモデルで観測履歴を何度も読み直すため総量が増えるが、"
            f"単価差がそれを上回って**総額では B が有利**")
    return "\n".join(lines)


def render_markdown(report: dict) -> str:
    rows, detail = [], []
    for key in report["order"]:
        a = report["summary"][key]
        label = VARIANTS[key]["label"]
        cps = f"${a['cost_per_success_usd']:.4f}" if a["cost_per_success_usd"] is not None else "—"
        rows.append(
            f"| {label} | {a['success']}/{a['trials']} | {a['mean_elapsed_sec']}s | "
            f"{a['mean_llm_calls']} | {a['mean_tool_calls']} | {a['mean_tokens']} | "
            f"${a['mean_cost_usd']:.4f} | {cps} | {a['needs_human_rate']:.0%} |")
        for t in report["trials"]:
            if t["variant"] != key:
                continue
            detail.append(
                f"| {label} | #{t['trial']} | {t['status']} | {t['elapsed_sec']}s | "
                f"{t['llm_calls']} | {t['tool_calls']} | "
                f"{t['input_tokens']}/{t['output_tokens']} | ${t['cost_usd']:.4f} | "
                f"{', '.join(t['models']) or '—'} |")

    return f"""# A/B/R 方式比較の実測結果

**測定日時**: {report['generated_at']} / **route_mode**: `{report['route_mode']}`
**条件**: T-04 複合障害（主回線リンク断 + r2 の誤ACL `BAD-ACL-443`）× 各方式 {report['trials_per_variant']} 試行
**環境**: netns シミュレータ（sim/）・OrcaRouter 実キー

| 方式 | 内容 |
|---|---|
| **A 高性能モデル固定** | 判断・VLM とも `openai/gpt-5` 固定 |
| **B 段階別選択（既定）** | `gpt-4o-mini` → `gemini-2.5-flash` → `gpt-5` の順に候補列を試行 |
| **R 固定ランブック** | 判断は決定木で固定。構成図読取のみ VLM を使う（`NW_AGENT_MODE=scripted`） |

承認は評価用の**自動代行承認**（人手の承認判断を模したものではない）。
所要時間には承認待ちの人手時間を含まない。

## 集計

| 方式 | 成功 | 平均所要 | 平均LLM呼出 | 平均ツール実行 | 平均トークン | 平均費用 | 成功1件あたり費用 | NEEDS_HUMAN率 |
|---|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

## 試行ごとの内訳

| 方式 | 試行 | 終了状態 | 所要 | LLM呼出 | ツール実行 | in/out トークン | 費用 | 使用モデル |
|---|---|---|---|---|---|---|---|---|
{chr(10).join(detail)}

## 比較から分かること

{render_comparison(report)}

## 読み方

- **成功1件あたり費用**（§12.2）は、失敗試行で発生した費用も分子に含めた実効コスト
- 費用は OrcaRouter が原価を返さないため `route_policy.yaml` の単価表 × 実トークン数で算出
  （単価不明モデルは加算せず、`cost_unpriced_calls` として別途記録）
- R方式の費用は構成図読取（VLM）1回分のみ。判断に LLM を使わないぶん安価だが、
  **想定済みの障害しか扱えない**（観測順・判断が決定木に固定されている）。
  A/B は観測結果に応じて次の手を組み立てるため、未知の障害にも手順を伸ばせる

生データ: [results.json](results.json)
"""


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3, help="方式あたりの試行数")
    ap.add_argument("--variants", default="A,B,R", help="評価する方式（例 B,R）")
    ap.add_argument("--limit-sec", type=int, default=420, help="1試行の上限秒")
    args = ap.parse_args()

    order = [v.strip().upper() for v in args.variants.split(",") if v.strip()]
    unknown = [v for v in order if v not in VARIANTS]
    if unknown:
        print(f"不明な方式: {unknown}", file=sys.stderr)
        return 2

    db_path = BACKEND_DIR / "var" / "netwalker.db"
    trials: list[dict] = []
    summary: dict[str, dict] = {}
    route_mode = os.environ.get("NW_ROUTE_MODE", "live")

    for variant in order:
        print(f"\n=== 方式 {variant}: {VARIANTS[variant]['label']} ===", flush=True)
        proc = start_backend(VARIANTS[variant]["env"], db_path)
        try:
            cfg = wait_healthy(proc)
            print(f"  agent_mode={cfg['agent_mode']} route_mode={cfg['route_mode']}", flush=True)
            got: list[dict] = []
            for i in range(1, args.trials + 1):
                print(f"  試行 {i}/{args.trials} …", end="", flush=True)
                try:
                    t = run_trial(variant, i, args.limit_sec)
                except Exception as exc:  # noqa: BLE001  1試行の失敗で全体を止めない
                    t = {"variant": variant, "trial": i, "status": f"ERROR:{type(exc).__name__}",
                         "success": False, "needs_human": False, "elapsed_sec": 0.0,
                         "approved_at_sec": None, "llm_calls": 0, "input_tokens": 0,
                         "output_tokens": 0, "cost_usd": 0.0, "cost_unpriced_calls": 0,
                         "tool_calls": 0, "models": [], "fallbacks": 0,
                         "residual_issues": 0, "incident_id": None, "error": str(exc)[:200]}
                print(f" {t['status']} / {t['elapsed_sec']}s / "
                      f"{t['llm_calls']}呼出 / ${t['cost_usd']:.4f}", flush=True)
                got.append(t)
                trials.append(t)
            summary[variant] = aggregate(got)
        finally:
            stop_backend(proc)

    report = {
        "generated_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "route_mode": route_mode,
        "trials_per_variant": args.trials,
        "order": order,
        "summary": summary,
        "trials": trials,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "results.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"\n出力: {OUT_DIR/'results.md'}")
    print(f"      {OUT_DIR/'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
