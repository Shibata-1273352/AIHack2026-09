// この案件で実際に通った防御層を並べる（S8c-2）。
//
// 「安全です」と言うだけでは検証できない。どの層が何件を通し、どこで止めたかを
// 件数で出す。ゲートウェイのファイアウォールは**シャドーモード（監視のみ）**なので、
// 実際に遮断しているのは NetWalker 側であることを画面にも明記する（§15 の誠実性）。

import type { Bundle } from "../types";

export function DefenseLayers({ bundle }: { bundle: Bundle }) {
  const runs = bundle.model_runs;
  const sent = runs.filter(r => !["send_policy_violation"].includes(r.outcome)).length;
  const gateBlocked = runs.filter(r => r.outcome === "send_policy_violation").length;
  const guardrailBlocked = runs.filter(r => r.outcome === "guardrail_blocked").length;
  const schemaViolations = runs.filter(r => r.outcome === "schema_violation").length;
  const vlmEv = bundle.evidence.find(e => e.tool === "vlm_read_topology");
  const cmp = vlmEv?.result?.comparison;
  const unmatched = (cmp?.unmatched_labels?.length ?? 0) + (cmp?.missing_registered?.length ?? 0);
  const plans = bundle.plans.length;
  const validated = bundle.plans.filter(p => p.validation?.verified).length;
  const approvals = bundle.approvals.length;
  const approved = bundle.approvals.filter(a => a.decision === "approved").length;
  const rejected = bundle.approvals.filter(a => a.decision === "rejected").length;

  const rows: { n: string; name: string; detail: string; who: string }[] = [
    {
      n: "①", name: "ゲートウェイのガードレール（内容）",
      detail: guardrailBlocked > 0
        ? `${guardrailBlocked}件を遮断（AIには渡っていません）`
        : `${sent}件を送信。遮断 0件`,
      who: "OrcaRouter",
    },
    {
      n: "②", name: "NetWalker の送信ゲート（データ区分）",
      detail: gateBlocked > 0
        ? `外部送信不可のデータ ${gateBlocked}件をプロバイダ呼出前に遮断`
        : "外部送信可のデータのみ送信（違反 0件）",
      who: "NetWalker",
    },
    {
      n: "③", name: "構造化出力スキーマ",
      detail: schemaViolations > 0
        ? `スキーマ不適合 ${schemaViolations}件を不採用`
        : "全ての応答が型に適合",
      who: "NetWalker",
    },
    {
      n: "④", name: "登録機器表との機械照合",
      detail: cmp
        ? (unmatched > 0 ? `確認待ち ${unmatched}件（実測で補完）` : "図と登録情報が全件一致")
        : "未実行",
      who: "NetWalker",
    },
    {
      n: "⑤", name: "変更操作のホワイトリスト",
      detail: `変更案 ${plans}件のうち、事前検証に合格 ${validated}件。`
        + "許可範囲外の操作はシミュレータ側で拒否されます",
      who: "NetWalker",
    },
    {
      n: "⑥", name: "人の承認",
      detail: approvals === 0 ? "承認依頼なし"
        : `依頼 ${approvals}件 / 承認 ${approved}件 / 却下 ${rejected}件`,
      who: "人間",
    },
  ];

  return (
    <section className="card defense-layers">
      <div className="card-head">
        <h2>この案件で通った防御層</h2>
        <span className="card-note">外側（ゲートウェイ）と内側（アプリ）の二層</span>
      </div>
      {rows.map(r => (
        <div key={r.n} className="defense-row">
          <span className="defense-n">{r.n}</span>
          <span className="defense-body">
            <span className="defense-name">{r.name}</span>
            <span className="defense-detail">{r.detail}</span>
          </span>
          <span className={`defense-who ${r.who === "OrcaRouter" ? "gw" : r.who === "人間" ? "human" : "app"}`}>
            {r.who}
          </span>
        </div>
      ))}
      <p className="defense-note">
        OrcaRouter のファイアウォールは<b>シャドーモード（監視のみ）</b>で運用しています。
        実際に操作を遮断しているのは NetWalker 側の変更ホワイトリストと承認ゲートです。
        ゲートウェイの記録は、同じツール呼出に対する<b>独立した第二の判定</b>として突き合わせに使います。
      </p>
    </section>
  );
}
