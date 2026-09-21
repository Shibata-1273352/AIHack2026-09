// OTel 風タイムライン（M-15 簡易版）: 案件の全スパンをガントレーン表示。
// ツール実測・LLM判断・状態遷移・検証を1本の時間軸で追える（審査項目「自律性」「信頼性」の証拠）。
// ヘッダ右の KPI チップ列（LLM回数・トークン・コスト・ツール回数・経過秒）がコスパの実測値。

import type { Bundle, Span } from "../types";
import { useElapsed } from "./Chrome";

const KIND_COLOR: Record<string, string> = {
  tool: "#1f5fbf",
  verifier: "#1f8a5b",
  llm: "#7c3aed",
  state: "#8a94a0",
  approval: "#b9770e",
  internal: "#5d6773",
};
const KIND_LABEL: Record<string, string> = {
  tool: "ツール実測", verifier: "独立検証器", llm: "LLM/VLM", state: "状態遷移",
  approval: "承認（人間）", internal: "内部処理",
};

function KpiChips({ bundle }: { bundle: Bundle }) {
  const runs = bundle.model_runs.filter(r => r.resolved_model && !["mock", "fallback_to_mock"].includes(r.outcome));
  const tokens = runs.reduce((a, r) => a + (r.input_tokens ?? 0) + (r.output_tokens ?? 0), 0);
  const cost = runs.reduce((a, r) => a + (r.cost_usd ?? 0), 0);
  const elapsed = useElapsed(bundle.incident);
  const items = [
    `LLM ${runs.length}回`,
    `tok ${tokens.toLocaleString()}`,
    `$${cost.toFixed(4)}`,
    `tool ${bundle.evidence.length}回`,
    `経過 ${elapsed}`,
  ];
  return (
    <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
      {items.map((t) => (
        <span key={t} style={{
          fontFamily: "var(--mono)", fontSize: 10.5, fontWeight: 600,
          color: "var(--text-muted)", background: "var(--bg-subtle)",
          border: "1px solid var(--border-subtle)", borderRadius: 6,
          padding: "2px 8px", whiteSpace: "nowrap",
        }}>{t}</span>
      ))}
    </span>
  );
}

export function TimelineCard({ bundle, style }: { bundle: Bundle; style?: React.CSSProperties }) {
  const end = bundle.incident?.status_history.find(h => ["SERVICE_RESTORED", "RESOLVED", "NEEDS_HUMAN", "CANCELLED"].includes(h.status));
  const endMs = end ? new Date(end.at).getTime() + 999 : Infinity;
  const spans = bundle.spans.filter(s => s.start_ms <= endMs);
  const empty = !bundle.incident || spans.length === 0;
  const t0 = empty ? 0 : Math.min(...spans.map((s) => s.start_ms));
  const t1 = empty ? 1000 : Math.max(...spans.map((s) => s.end_ms), t0 + 1000);
  const total = t1 - t0;
  const lanes: (keyof typeof KIND_COLOR)[] = ["state", "llm", "tool", "verifier", "approval", "internal"];
  const byLane: Record<string, Span[]> = {};
  for (const s of spans) (byLane[s.kind] ??= []).push(s);
  const usedLanes = lanes.filter((k) => byLane[k]?.length);

  return (
    <section className="card" style={{ minWidth: 0, minHeight: 0, gap: 8, ...style }}>
      <div className="card-head" style={{ flex: "none" }}>
        <h2>実行タイムライン（OTelスパン）</h2>
        {bundle.incident && (
          <span className="card-note" style={{ fontFamily: "var(--mono)", marginLeft: 10 }}>
            trace={bundle.incident.id} · {spans.length} spans · {(total / 1000).toFixed(1)}s
          </span>
        )}
        <KpiChips bundle={bundle} />
      </div>
      {empty ? (
        <div style={{ fontSize: 12, color: "var(--text-faint)" }}>
          調査開始で LLM 判断・ツール実測・承認・検証のスパンがここへ並びます。
        </div>
      ) : (
        <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 4, overflow: "hidden", justifyContent: "center" }}>
          {usedLanes.map((kind) => (
            <div key={kind} style={{ display: "grid", gridTemplateColumns: "90px 1fr", gap: 10, alignItems: "center" }}>
              <div style={{ fontSize: 10, color: "var(--text-muted)", textAlign: "right", whiteSpace: "nowrap" }}>
                {KIND_LABEL[kind]} {byLane[kind].length}
              </div>
              <div style={{ position: "relative", height: 16, background: "var(--bg-faint)", borderRadius: 5 }}>
                {byLane[kind].map((s) => {
                  const left = ((s.start_ms - t0) / total) * 100;
                  const width = Math.max(0.6, ((s.end_ms - s.start_ms) / total) * 100);
                  return (
                    <div key={s.id} title={`${s.name} (${s.duration_ms}ms)${s.status === "error" ? " · エラー" : ""}`}
                      style={{
                        position: "absolute", left: `${left}%`, width: `${width}%`,
                        top: 3, height: 10, borderRadius: 3,
                        background: s.status === "error" ? "#c73a2b" : KIND_COLOR[kind],
                        opacity: 0.85, minWidth: 3,
                      }} />
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
