// 「本番に触る前に、そっくりな複製環境で試した」の可視化。
//
// シミュレータは変更前後のルールセット全文まで返しているのに、これまで画面では
// ✓1行に潰れていた。NetWalker の最大の差別化なので、4秒で読める形にして前面へ出す。
// 変更前／変更後を左右に並べるのが肝（一目で「業務NG→OK・禁止は遮断のまま」が分かる）。

import type { Plan } from "../types";

function Col({ head, business, forbidden, tone }: {
  head: string; business: boolean; forbidden: boolean; tone: "before" | "after";
}) {
  return (
    <div className={`clone-col ${tone}`}>
      <div className="clone-col-head">{head}</div>
      <div className={business ? "ok" : "ng"}>業務通信　{business ? "OK" : "NG"}</div>
      <div className={forbidden ? "ok" : "ng"}>禁止通信　{forbidden ? "遮断されている" : "遮断できていない"}</div>
    </div>
  );
}

export function CloneCheck({ plan, compact }: { plan: Plan | undefined; compact?: boolean }) {
  const v = plan?.validation;
  if (!v || !v.verified) return null;
  const deleted = v.applied_in_verify?.deleted_rule ?? null;

  return (
    <section className={`clone-check${compact ? " compact" : ""} fadein`}>
      <b className="clone-lead">本番に触る前に、そっくりな複製環境で試しました</b>

      {!compact && (
        <div className="clone-step">
          <span>①</span> 複製をつくった — 本番と同じ構成であることを確認
        </div>
      )}

      <div className="clone-grid">
        <Col head={compact ? "変更する前" : "② 変更する前"} tone="before"
          business={!!v.pre?.business} forbidden={!!v.pre?.forbidden} />
        <Col head={compact ? "変更したあと" : "③ 変更したあと"} tone="after"
          business={!!v.post?.business} forbidden={!!v.post?.forbidden} />
      </div>

      <div className="clone-verdict">
        {compact ? "" : "④ "}判定 <b>合格</b> → だから本番に出せます
      </div>

      <details className="clone-details">
        <summary>複製の手順と、変更前後のルール全文</summary>
        {deleted && (
          <div className="clone-deleted">
            複製環境で削除したルール
            <pre>{deleted}</pre>
          </div>
        )}
        {v.clone_steps && v.clone_steps.length > 0 && (
          <div className="clone-steps">
            複製の実行手順（{v.clone_steps.length}件）
            <pre>{v.clone_steps.map((s) => `${s.step}${s.rc !== undefined ? ` (rc=${s.rc})` : ""}`).join("\n")}</pre>
          </div>
        )}
        {v.diff && (
          <div className="clone-rulesets">
            <div>
              <span>変更前のルールセット全文</span>
              <pre>{v.diff.pre}</pre>
            </div>
            <div>
              <span>変更後のルールセット全文</span>
              <pre>{v.diff.post}</pre>
            </div>
          </div>
        )}
      </details>
    </section>
  );
}
