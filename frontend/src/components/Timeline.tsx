// OTel 風タイムライン（M-15 簡易版）: 案件の全スパンをガントレーン表示。
// ツール実測・LLM判断・状態遷移・検証を1本の時間軸で追える（審査項目「自律性」「信頼性」の証拠）。

import type { Bundle, Span } from "../types";

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

export function TimelineCard({ bundle }: { bundle: Bundle }) {
  const spans = bundle.spans;
  if (!bundle.incident || spans.length === 0) return null;
  const t0 = Math.min(...spans.map((s) => s.start_ms));
  const t1 = Math.max(...spans.map((s) => s.end_ms), t0 + 1000);
  const total = t1 - t0;
  const lanes: (keyof typeof KIND_COLOR)[] = ["state", "llm", "tool", "verifier", "approval", "internal"];
  const byLane: Record<string, Span[]> = {};
  for (const s of spans) (byLane[s.kind] ??= []).push(s);

  return (
    <section className="card fadein" style={{ order: 9, gridColumn: "1 / -1" }}>
      <div className="card-head">
        <h2>実行タイムライン（OTelスパン）</h2>
        <span className="card-note" style={{ fontFamily: "var(--mono)" }}>
          trace={bundle.incident.id} · {spans.length} spans · {(total / 1000).toFixed(1)}s
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {lanes.filter((k) => byLane[k]?.length).map((kind) => (
          <div key={kind} style={{ display: "grid", gridTemplateColumns: "90px 1fr", gap: 10, alignItems: "center" }}>
            <div style={{ fontSize: 10.5, color: "var(--text-muted)", textAlign: "right" }}>{KIND_LABEL[kind]}</div>
            <div style={{ position: "relative", height: 22, background: "var(--bg-faint)", borderRadius: 6 }}>
              {byLane[kind].map((s) => {
                const left = ((s.start_ms - t0) / total) * 100;
                const width = Math.max(0.6, ((s.end_ms - s.start_ms) / total) * 100);
                return (
                  <div key={s.id} title={`${s.name} (${s.duration_ms}ms)${s.status === "error" ? " · エラー" : ""}`}
                    style={{
                      position: "absolute", left: `${left}%`, width: `${width}%`,
                      top: 4, height: 14, borderRadius: 4,
                      background: s.status === "error" ? "#c73a2b" : KIND_COLOR[kind],
                      opacity: 0.85, minWidth: 3,
                    }} />
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 10.5, color: "var(--text-faint)", display: "flex", gap: 14, flexWrap: "wrap" }}>
        {lanes.filter((k) => byLane[k]?.length).map((k) => (
          <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: KIND_COLOR[k] }} />
            {KIND_LABEL[k]} {byLane[k].length}
          </span>
        ))}
        <span style={{ marginLeft: "auto" }}>ホバーでスパン名と所要時間を表示</span>
      </div>
    </section>
  );
}

export function TechStrip({ bundle, modeNote }: { bundle: Bundle; modeNote: string }) {
  if (!bundle.incident) return null;
  const runs = bundle.model_runs;
  const calls = runs.length;
  const tokens = runs.reduce((a, r) => a + (r.input_tokens ?? 0) + (r.output_tokens ?? 0), 0);
  const cost = runs.reduce((a, r) => a + (r.cost_usd ?? 0), 0);
  const lastRun = runs[runs.length - 1];
  const toolCalls = bundle.evidence.length;
  return (
    <div style={{
      order: 10, gridColumn: "1 / -1", display: "flex", gap: 18, flexWrap: "wrap",
      fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--mono)",
      background: "#fff", border: "1px solid var(--border-inner)", borderRadius: 10, padding: "10px 16px",
    }}>
      <span>trace: {bundle.incident.id}</span>
      <span>mode: {modeNote}</span>
      {lastRun?.resolved_model && <span>resolved_model: {lastRun.resolved_model}</span>}
      <span>llm_calls {calls} · tokens {tokens.toLocaleString()} · est ${cost.toFixed(4)}</span>
      <span>tool_calls {toolCalls}（読取上限20）</span>
      <span>data_class: external_allowed（合成データ・登録済み）</span>
    </div>
  );
}
