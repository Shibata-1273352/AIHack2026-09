// AI呼出の明細（技術詳細モーダル）。どのモデルがなぜ選ばれ、いくらかかったか。
//
// 費用は二本立てで出す（誠実性）:
//   実費 … OrcaRouter GET /v1/generation の確定請求額
//   推定 … 単価表からの計算（呼出前の予算判定に使う値。実費が出たら置き換える）
// 未確定は「—」のまま。0 円と偽らない。

import type { Bundle, ModelRun } from "../types";

function costCell(r: ModelRun) {
  if (r.actual_cost_usd != null) {
    return <><b>${r.actual_cost_usd.toFixed(6)}</b><small> 実費</small></>;
  }
  if (r.cost_usd != null) {
    return <><span>${r.cost_usd.toFixed(6)}</span><small> 推定</small></>;
  }
  return <small>未確定</small>;
}

function routeCell(r: ModelRun) {
  if (["mock", "fallback_to_mock"].includes(r.outcome)) {
    return <small>録画再生{r.resolved_model ? `（記録時: ${r.resolved_model}）` : ""}</small>;
  }
  if (r.router) {
    return <>
      <b>{r.resolved_model ?? "—"}</b>
      <small>{` OrcaRouter ${r.router}${r.strategy ? ` · ${r.strategy}` : ""}`}
        {r.fallback_level != null ? ` · fallback ${r.fallback_level}` : ""}</small>
    </>;
  }
  return <>
    <b>{r.resolved_model ?? r.route ?? "—"}</b>
    <small> 固定モデル</small>
  </>;
}

export function ModelRunsCard({ bundle }: { bundle: Bundle }) {
  const runs = bundle.model_runs;
  const sel = bundle.incident?.model_selection;

  return (
    <section className="card model-runs">
      <div className="card-head">
        <h2>AI呼出の明細</h2>
        <span className="card-note">{runs.length}件</span>
      </div>
      {sel && (
        <div className="subtile">
          <div className="lbl">この案件のモデル選択</div>
          <div>
            要求 <code>{sel.requested ?? "—"}</code> → 実際 <code>{sel.resolved ?? "—"}</code>
            {sel.router ? `（OrcaRouter ${sel.router}${sel.strategy ? ` · ${sel.strategy}` : ""}）` : ""}
            <br />
            出所：{sel.source === "override" ? "画面からの選択" : "設定どおり（route_policy.yaml）"}
            {` · 比較方式 ${sel.variant}`}
            {sel.replay ? " · 録画再生（実際のモデルは呼ばれていません）" : ""}
          </div>
        </div>
      )}
      {runs.length === 0 && (
        <div style={{ fontSize: 12.5, color: "var(--text-faint)" }}>
          まだAIの呼出はありません。
        </div>
      )}
      {runs.map(r => (
        <div key={r.id} className="mrun-row">
          <span className="mrun-key">{r.key}</span>
          <span className="mrun-route">{routeCell(r)}</span>
          <span className="mrun-tok">
            {r.input_tokens != null ? `${r.input_tokens}+${r.output_tokens ?? 0} tok` : "—"}
          </span>
          <span className="mrun-lat">
            {(r.actual_latency_ms ?? r.latency_ms) != null
              ? `${r.actual_latency_ms ?? r.latency_ms}ms` : "—"}
          </span>
          <span className="mrun-cost">{costCell(r)}</span>
          <span className={`mrun-outcome ${r.outcome}`}>{r.outcome}</span>
        </div>
      ))}
    </section>
  );
}
