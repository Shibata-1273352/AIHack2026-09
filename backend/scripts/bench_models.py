#!/usr/bin/env python3
"""候補モデルを実タスクで検証する（安い＝良い、ではないので必ず実測する）。

同じ入力で 2 タスクを回し、合否・実請求額・レイテンシを表に出す:
  decide … 観測履歴 → 次の行動（json_schema 構造化出力）
  vlm    … 構成図PNG → ノード/リンクのグラフJSON（vision + 構造化出力）

結果は docs/evaluation/models.md に書き出す。合格したものだけを
route_policy.yaml の候補列と画面の選択肢に載せること。

使い方:
  cd backend && uv run python scripts/bench_models.py            # 既定の候補
  cd backend && uv run python scripts/bench_models.py --only decide
  cd backend && uv run python scripts/bench_models.py --models z-ai/glm-5.3-flash,openai/gpt-5.4-nano
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.agent import DECIDE_SCHEMA, LLM_SYSTEM  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm.orcarouter import GuardrailBlocked, OrcaRouterClient  # noqa: E402
from app.llm.route_policy import ResolvedProfile, policy  # noqa: E402
from app.vlm import GRAPH_SCHEMA, SYSTEM_PROMPT as VLM_SYSTEM  # noqa: E402

OUT = BACKEND.parent / "docs" / "evaluation" / "models.md"

CANDIDATES = [
    "orcarouter/auto",
    "orcarouter/fusion-flash",
    "orcarouter/fusion-mini",
    "orcarouter/free",
    "z-ai/glm-5.3-flash",
    "z-ai/glm-5.3-flash-free",
    "qwen/qwen3.8-flash",
    "deepseek/deepseek-v4.1-flash",
    "deepseek/deepseek-v4-flash-free",
    "openai/gpt-5.4-nano",
    "minimax/minimax-m3",
    "google/gemini-3.8-flash",
    "tencent/hy3-free",
    "openai/gpt-4o-mini",
    "openai/gpt-5",
]

DECIDE_USER = (
    "これまでの観測結果（時系列）:\n"
    "1. [test_business] 業務テスト(HTTPS受注画面×3) → 不合格\n"
    "2. [vlm_read_topology] ノード5・リンク5を抽出、登録機器表と全件一致\n"
    "\n次の行動を JSON で1つだけ選んでください。"
)


@dataclass
class Row:
    model: str
    task: str
    ok: bool
    note: str
    resolved: str | None
    latency_ms: int | None
    cost_usd: float | None
    cost_source: str


def profile_for(task: str, model: str) -> ResolvedProfile:
    base = policy.resolve(task)
    base.routes = [model]
    base.timeout_seconds = 90
    return base


def run_one(client: OrcaRouterClient, model: str, task: str) -> Row:
    if task == "decide":
        system, user, schema = LLM_SYSTEM, DECIDE_USER, DECIDE_SCHEMA
    else:
        png = settings.assets_dir / "topology-diagram.png"
        if not png.exists():
            return Row(model, task, False, "構成図PNGが無い", None, None, None, "-")
        b64 = base64.b64encode(png.read_bytes()).decode()
        system = VLM_SYSTEM
        user = [
            {"type": "text", "text": "この構成図からノードとリンクを抽出してください。"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]
        schema = GRAPH_SCHEMA

    prof = profile_for(task, model)
    try:
        resp = client.complete(prof, system=system, user=user, json_schema=schema)
    except GuardrailBlocked as exc:
        return Row(model, task, False, f"ガードレール遮断: {exc}", None, None, None, "-")
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status_code", None)
        return Row(model, task, False, f"{type(exc).__name__}"
                   + (f"({status})" if status else ""), None, None, None, "-")

    ok = bool(resp.parsed) and resp.schema_ok
    note = "構造化出力OK" if ok else f"スキーマ不適合 (outcome={resp.outcome})"
    if ok and task == "vlm":
        n = len(resp.parsed.get("nodes", []))
        l = len(resp.parsed.get("links", []))
        note = f"機器{n}・接続{l}"
        ok = n >= 5 and l >= 5

    cost, source = resp.cost_usd, "推定(単価表)"
    if resp.request_id:
        time.sleep(1.0)
        data = client.fetch_actual_cost(resp.request_id, retries=4, delay=1.5)
        if data and data.get("total_cost") is not None:
            cost, source = data["total_cost"], "実請求額"
    if cost is None:
        cost = prof.estimate_cost_usd(resp.resolved_model, resp.input_tokens,
                                      resp.output_tokens, route=resp.route)
        source = "推定(単価表)" if cost is not None else "未取得"
    return Row(model, task, ok, note, resp.resolved_model, resp.latency_ms, cost, source)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--only", default="", choices=["", "decide", "vlm"])
    args = ap.parse_args()

    if not settings.has_api_key:
        print("ORCAROUTER_API_KEY が未設定です（実測できません）", file=sys.stderr)
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()] or CANDIDATES
    tasks = [args.only] if args.only else ["decide", "vlm"]
    client = OrcaRouterClient(
        base_url=settings.orcarouter_base_url,
        api_key=settings.orcarouter_api_key.get_secret_value(), timeout=90)

    rows: list[Row] = []
    for m in models:
        for t in tasks:
            r = run_one(client, m, t)
            rows.append(r)
            print(f"{'OK ' if r.ok else 'NG '} {m:34s} {t:7s} "
                  f"{(r.resolved or '-'):26s} {str(r.latency_ms or '-'):>7s}ms "
                  f"{('$%.6f' % r.cost_usd) if r.cost_usd is not None else '-':>12s} "
                  f"{r.cost_source:10s} {r.note}")

    write_report(rows, tasks)
    print(f"\n→ {OUT}")
    return 0


def write_report(rows: list[Row], tasks: list[str]) -> None:
    by_model: dict[str, dict[str, Row]] = {}
    for r in rows:
        by_model.setdefault(r.model, {})[r.task] = r

    lines = [
        "# 候補モデルの実タスク検証",
        "",
        f"実測日時: {time.strftime('%Y-%m-%d %H:%M:%S')} / "
        f"policy `{policy.version}` / 実行: `backend/scripts/bench_models.py`",
        "",
        "同一入力で2タスクを実行し、**構造化出力に本当に対応しているか**と",
        "**実請求額**（OrcaRouter `GET /v1/generation` の `total_cost`）を実測した。",
        "単価が安いことは採用理由にならないので、合否は実タスクの結果で決めている。",
        "合格したものだけを `route_policy.yaml` の候補列と画面の選択肢に載せる。",
        "",
        "| モデル | decide（判断） | vlm（構成図読取） | 解決されたモデル | 実費 decide | 実費 vlm | 遅延 decide |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, per in by_model.items():
        d, v = per.get("decide"), per.get("vlm")

        def cell(r: Row | None) -> str:
            if r is None:
                return "—"
            return ("✅ " if r.ok else "❌ ") + r.note

        def cost(r: Row | None) -> str:
            if r is None or r.cost_usd is None:
                return "—"
            return f"${r.cost_usd:.6f}<br><small>{r.cost_source}</small>"

        resolved = (d.resolved if d else None) or (v.resolved if v else None) or "—"
        lines.append(
            f"| `{model}` | {cell(d)} | {cell(v)} | `{resolved}` | "
            f"{cost(d)} | {cost(v)} | {(str(d.latency_ms) + 'ms') if d and d.latency_ms else '—'} |")

    passed_decide = [m for m, per in by_model.items() if per.get("decide") and per["decide"].ok]
    passed_vlm = [m for m, per in by_model.items() if per.get("vlm") and per["vlm"].ok]
    lines += [
        "",
        "## 判定",
        "",
        f"- decide（構造化出力）合格: {', '.join('`%s`' % m for m in passed_decide) or 'なし'}",
        f"- vlm（vision + 構造化出力）合格: {', '.join('`%s`' % m for m in passed_vlm) or 'なし'}",
        "",
        "不合格のモデルは候補列にも選択UIにも載せない。構造化出力に非対応のモデルは",
        "400 を返し、400 は再試行不可なので調査がその場で落ちるため。",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
