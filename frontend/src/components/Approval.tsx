// 承認UIの共有部品。/approve（実iPad・フル画面）とコンソール内 ApprovalStage
// （iPadベゼル風埋め込み）の両方から使う。どちらから決裁しても
// サーバの hash/版/期限照合が二重承認を防ぐ（M-14）。

import { ReactNode, useEffect, useState } from "react";
import { post } from "../api";
import type { Bundle } from "../types";
import { CloneCheck } from "./CloneCheck";
import { Term } from "./Plain";

export function useClock(): string {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

// ---------------------------------------------------------------- 承認状態フック

export function useApproval(bundle: Bundle) {
  const [approver, setApprover] = useState("田中（変更承認権限）");
  const [reason, setReason] = useState("");   // 却下理由（任意・人間向けの記録のみ）
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [, tick] = useState(0);
  // 残り時間カウントダウン用の再描画（StrictMode でも cleanup で二重タイマーを防ぐ）
  useEffect(() => {
    const t = setInterval(() => tick((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const inc = bundle.incident;
  const ap = bundle.approvals[bundle.approvals.length - 1];
  const plan = ap ? bundle.plans.find((p) => p.id === ap.plan_id) : bundle.plans[bundle.plans.length - 1];

  const remain = ap && ap.decision === "pending"
    ? Math.max(0, Math.floor(ap.expires_epoch - Date.now() / 1000)) : 0;
  const remainStr = `${Math.floor(remain / 60)}:${String(remain % 60).padStart(2, "0")}`;

  const decide = async (decision: "approve" | "reject") => {
    if (!inc || !ap || !plan || busy || remain <= 0) return;
    setBusy(true);
    setError("");
    try {
      await post(`/api/incidents/${inc.id}/approval`, {
        plan_id: ap.plan_id, plan_hash: ap.plan_hash, decision, approver,
        reason: decision === "reject" ? reason : "",
      });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return { inc, ap, plan, remain, remainStr, error, decide, approver, setApprover,
           reason, setReason, busy };
}

// ---------------------------------------------------------------- 却下後の出口（M-12 / §14.3）

/**
 * 却下すると担当者対応待ちで止まるが、そこで画面が行き止まりになると
 * 4分の発表で却下を実演した瞬間に詰む。却下は失敗ではなく正常な安全動作なので、
 * 「何も変えていない」ことを明示したうえで、次へ進む道を3つ用意する。
 */
export function RejectedExits({ bundle, onReset, compact }: {
  bundle: Bundle; onReset?: () => void; compact?: boolean;
}) {
  const inc = bundle.incident;
  const handoff = bundle.handoffs[bundle.handoffs.length - 1];
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [assignee, setAssignee] = useState("ネットワーク運用担当（一次対応）");
  if (!inc) return null;

  const run = async (label: string, fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(label); setError("");
    try { await fn(); }
    catch (e: any) { setError(e.message || "処理に失敗しました"); }
    finally { setBusy(""); }
  };

  const accepted = handoff?.status === "accepted" || handoff?.status === "held";

  return (
    <div className={`rejected-exits${compact ? " compact" : ""}`}>
      <b className="exits-lead">承認しなかったので、ネットワークには何も変更していません</b>
      {handoff?.reason && <p className="exits-reason">却下の理由：{handoff.reason}</p>}
      {handoff && (
        <p className="exits-note">
          これまでの調査結果（証拠 {handoff.evidence_ids.length}件・仮説 {handoff.hypothesis_ids.length}件）と
          却下した変更案は、この案件に記録済みです。担当を替えても入力し直す必要はありません。
        </p>
      )}
      {accepted && (
        <p className="exits-accepted">
          引き継ぎを{handoff?.status === "accepted" ? "受領" : "保留"}として記録しました
          {handoff?.notes.at(-1)?.assignee ? `（${handoff.notes.at(-1)!.assignee}）` : ""}
        </p>
      )}
      {error && <div role="alert" className="exits-error">{error}</div>}
      <div className="exits-buttons">
        <button className="btn-primary" disabled={!!busy}
          onClick={() => run("調べ直しています", () => post(`/api/incidents/${inc.id}/reinvestigate`))}>
          もう一度調べ直す
        </button>
        <button className="btn-outline" disabled={!!busy || !handoff}
          onClick={() => run("引き継ぎを記録しています", () => post(`/api/incidents/${inc.id}/handoff`,
            { action: "accept", assignee, note: "" }))}>
          担当者に引き継ぐ
        </button>
        {onReset && (
          <button className="btn-outline" disabled={!!busy} onClick={onReset}>
            デモを初期状態へ戻す
          </button>
        )}
      </div>
      <label className="exits-assignee">
        引き継ぎ先
        <input value={assignee} onChange={(e) => setAssignee(e.target.value)} />
      </label>
      {busy && <div role="status" className="exits-busy">{busy}…</div>}
    </div>
  );
}

// ---------------------------------------------------------------- 承認画面（共有）

export function ApprovalScreen({ bundle, compact, footer, onReset }: {
  bundle: Bundle; compact?: boolean; footer?: ReactNode; onReset?: () => void;
}) {
  const clock = useClock();
  const { inc, ap, plan, remain, remainStr, error, decide, approver, setApprover,
          reason, setReason, busy } = useApproval(bundle);

  const card: React.CSSProperties = {
    background: "#fff", borderRadius: compact ? 10 : 12, padding: compact ? "9px 11px" : "12px 14px",
    border: "1px solid rgba(17,24,39,.06)", boxShadow: "0 1px 2px rgba(17,24,39,.04)",
  };
  const lbl: React.CSSProperties = { fontSize: compact ? 10 : 11, color: "#5d6773" };
  const pad = compact ? 12 : 18;
  const fs = compact ? 11.5 : 12.5;

  const statusLine = (() => {
    if (!inc) return null;
    switch (inc.status) {
      case "APPLYING": return { t: "承認された1件だけを適用しています", c: "#1f5fbf" };
      case "VERIFYING": return { t: "利用者と同じ通信で、復旧を確認しています", c: "#1f5fbf" };
      case "SERVICE_RESTORED": return { t: "業務が復旧しました · 主回線の対応は継続中です", c: "#1f8a5b" };
      case "RESOLVED": return { t: "解決済み", c: "#1f8a5b" };
      case "NEEDS_HUMAN": return { t: "担当者の判断が必要です（対象環境は変更していません）", c: "#b9770e" };
      case "ROLLING_BACK": return { t: "適用前の状態へ戻しています", c: "#b9770e" };
      default: return null;
    }
  })();
  const rejected = ap?.decision === "rejected";

  return (
    <div style={{
      display: "flex", flexDirection: "column", minHeight: compact ? 450 : "100vh",
      background: compact ? undefined : "linear-gradient(180deg,#fbfbfd,#f2f4f7)",
      maxWidth: compact ? undefined : 560, margin: compact ? undefined : "0 auto",
      width: "100%",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", padding: `${compact ? 8 : 10}px ${pad}px 0`, fontSize: compact ? 10 : 11, color: "#5d6773", fontWeight: 600 }}>
        <span>{clock}</span>
        <span>人による変更承認</span>
      </div>

      <div style={{ padding: `${compact ? 10 : 16}px ${pad}px ${compact ? 6 : 8}px` }}>
        <div style={lbl}>変更承認</div>
        <div style={{ fontSize: compact ? 14 : 17, fontWeight: 700, marginTop: 2 }}>
          {inc ? `${inc.id.toUpperCase()} · ${inc.site}` : "案件なし"}
        </div>
        {plan && (
          <div style={{ fontSize: compact ? 10 : 11, color: "#5d6773", marginTop: 2 }}>
            {/* hash は消さず従属表示にする。「人間がこのハッシュの計画を承認した」ことが論拠 */}
            <Term plain={`変更案 第${plan.version}版`}
              tech={`${plan.id.toUpperCase()}-v${plan.version} · hash ${plan.hash.slice(0, 8)}`} />
            {ap?.decision === "pending" && (
              <span style={{ marginLeft: 8 }}>有効期限 {remainStr}</span>
            )}
          </div>
        )}
      </div>

      {!plan && (
        <div style={{ padding: `${compact ? 14 : 24}px ${pad}px`, fontSize: compact ? 12 : 13.5, color: "#5d6773", lineHeight: 1.7 }}>
          承認待ちの変更計画はありません。<br />
          調査が完了し事前検証に合格すると、この画面に承認依頼が表示されます。
        </div>
      )}

      {plan && (
        <div style={{ padding: `0 ${pad}px`, display: "flex", flexDirection: "column", gap: compact ? 6 : 8, fontSize: fs }}>
          {/* 差分はカードの主役。「実際に流す1行」を人が見て承認したことが論拠になる（ASI09） */}
          <div style={{ ...card, borderColor: "rgba(185,119,14,.35)" }}>
            <div style={lbl}>変更内容</div>
            <div style={{ marginTop: 2, lineHeight: 1.5, fontWeight: 600 }}>
              {plan.title_plain ?? plan.title}
            </div>
            <div style={{ marginTop: 6, lineHeight: 1.5, color: "#5d6773" }}>
              {plan.diff_plain ?? "承認された1件だけを適用します。"}
            </div>
            <details className="approval-diff" open={!compact}>
              <summary>実際に流す変更（1行）を見る</summary>
              <div style={{ fontFamily: "var(--mono)", fontSize: 12, marginTop: 6, color: "#c73a2b", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{plan.diff}</div>
            </details>
          </div>
            <>
              <div style={card}>
                <div style={lbl}>この変更で起きること</div>
                <div style={{ marginTop: 2, lineHeight: 1.5 }}>{plan.impact_plain ?? plan.impact}</div>
              </div>
              <div style={card}>
                <div style={lbl}>本番に出す前の確認</div>
                <CloneCheck plan={plan} compact />
                {!plan.validation?.verified && (
                  <div style={{ marginTop: 2, lineHeight: 1.5, color: "#c73a2b", fontWeight: 600 }}>
                    複製環境での確認に合格していません
                  </div>
                )}
              </div>
              <div style={card}>
                <div style={lbl}>うまくいかなかったときは</div>
                <div style={{ marginTop: 2, lineHeight: 1.5 }}>{plan.rollback_plain ?? plan.rollback}</div>
              </div>
            </>
        </div>
      )}

      <div style={{ marginTop: "auto", padding: `${compact ? 10 : 16}px ${pad}px ${compact ? 12 : 20}px`, display: "flex", flexDirection: "column", gap: compact ? 8 : 10 }}>
        {error && (
          <div style={{ background: "#fbeeec", color: "#c73a2b", borderRadius: 11, padding: compact ? 9 : 12, fontSize: fs, fontWeight: 600 }}>
            {error}
          </div>
        )}

        {statusLine && (
          <div style={{
            background: statusLine.c === "#1f8a5b" ? "#e6f4ec" : statusLine.c === "#b9770e" ? "#fdf3e7" : "#eef3fb",
            color: statusLine.c, borderRadius: 11, padding: compact ? 9 : 12, fontSize: fs, fontWeight: 600, textAlign: "center",
          }}>
            {statusLine.t}
          </div>
        )}

        {ap?.decision === "pending" && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, fontSize: compact ? 10 : 11, color: "#5d6773", flexWrap: "wrap" }}>
              <span style={{ display: "inline-flex", alignItems: "center", minWidth: 0 }}>承認者：
                <input value={approver} onChange={(e) => setApprover(e.target.value)}
                  style={{ border: "1px solid #d6dbe1", borderRadius: 6, padding: "4px 8px", font: "inherit", marginLeft: 4, minWidth: 0, width: compact ? 130 : undefined }} />
              </span>
              <span style={{ fontWeight: 600, color: "#b9770e" }}>承認待ち</span>
            </div>
            {remain <= 0 && <div role="alert">承認期限が切れました。リセットして再検証してください。</div>}
            <button className="btn-green" disabled={busy || remain <= 0 || !approver.trim()} style={{ borderRadius: 13, padding: compact ? 11 : 14 }} onClick={() => decide("approve")}>
              {busy ? "送信中…" : "承認して適用へ"}
            </button>
            <div style={{ fontSize: compact ? 10.5 : 11.5, color: "#5d6773", textAlign: "center" }}>
              承認した1件以外は、何も変更されません
            </div>
            <button className="btn-outline" disabled={busy || remain <= 0 || !approver.trim()} style={{ borderRadius: 11, color: "#c73a2b", padding: compact ? "8px 12px" : undefined }} onClick={() => decide("reject")}>
              却下（対象環境は変更されません）
            </button>
            <label style={{ fontSize: compact ? 10 : 11, color: "#5d6773", display: "flex", flexDirection: "column", gap: 4 }}>
              却下する場合の理由（任意・記録用）
              <input value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="例：メンテナンス時間外のため"
                style={{ border: "1px solid #d6dbe1", borderRadius: 6, padding: "6px 8px", font: "inherit", minWidth: 0 }} />
            </label>
          </>
        )}

        {ap && ap.decision !== "pending" && (
          <div style={{
            background: ap.decision === "approved" ? "#e6f4ec" : "#fbeeec",
            color: ap.decision === "approved" ? "#1f8a5b" : "#c73a2b",
            borderRadius: 11, padding: compact ? 9 : 12, fontSize: fs, fontWeight: 600, textAlign: "center",
          }}>
            {ap.decision === "approved"
              ? `承認済み · ${ap.decided_at?.slice(11)} · ${ap.approver} · 即時同期`
              : ap.decision === "rejected" ? "却下 · 対象環境は変更されません" : "期限切れ · 再検証・再承認が必要です"}
          </div>
        )}

        {rejected && inc?.status === "NEEDS_HUMAN" && (
          <RejectedExits bundle={bundle} onReset={onReset} compact={compact} />
        )}

        {footer}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- iPad ベゼル（ui-spec §7.1 逐語）

export function IpadFrame({ children }: { children: ReactNode }) {
  return (
    <div className="slide-in" style={{
      width: 300, flex: "none",
      background: "#0f1420", borderRadius: 32, padding: 11,
      boxShadow: "0 34px 60px -24px rgba(15,20,32,.5), inset 0 0 0 1px rgba(255,255,255,.1)",
    }}>
      <div style={{
        background: "linear-gradient(180deg,#fbfbfd,#f2f4f7)",
        borderRadius: 23, minHeight: 450, overflow: "hidden",
        display: "flex", flexDirection: "column",
      }}>
        {children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- コンソール内 承認ステージ

export function ApprovalStage({ bundle }: { bundle: Bundle }) {
  const plan = bundle.plans[bundle.plans.length - 1];
  const ap = bundle.approvals[bundle.approvals.length - 1];
  const v = plan?.validation;
  const awaiting = ap?.decision === "pending";

  return (
    <div style={{ display: "flex", gap: 12, minHeight: 0, flex: 1, alignItems: "stretch" }}>
      {/* 左: 計画 diff + 事前検証（コンパクト） */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 8, overflowY: "auto" }}>
        {awaiting && (
          <span className="chip" style={{ background: "var(--bg-amber-tint)", color: "var(--amber)", alignSelf: "flex-start" }}>
            承認待ち · 残り <RemainChip bundle={bundle} />
          </span>
        )}
        {plan && (
          <>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
              <span style={{ fontFamily: "var(--mono)" }}>{plan.id.toUpperCase()}-v{plan.version} · {plan.hash.slice(0, 6)}</span>
              　対象：{plan.body.node} · nftables {plan.body.table}/{plan.body.chain}
            </div>
            <pre className="diff-block" style={{ fontSize: 10.5, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              <span style={{ color: "#8a94a0" }}>table inet fw · chain forward</span>{"\n"}
              <span style={{ color: "#ff8a7a" }}>{plan.diff}</span>
            </pre>
            {v && (
              <div style={{
                fontSize: 11.5, lineHeight: 1.6, borderRadius: 10, padding: "8px 10px",
                background: v.verified ? "var(--bg-green-tint)" : "var(--bg-red-tint)",
                color: v.verified ? "var(--green)" : "var(--red)", fontWeight: 600,
              }}>
                事前検証：{v.verified ? "複製一致 ✓ · 業務 3/3 · 禁止遮断 維持 · 合格" : `不合格（${v.reason ?? ""}）`}
              </div>
            )}
            <div className="subtile"><div className="lbl">影響</div><div>{plan.impact}</div></div>
            <div className="subtile"><div className="lbl">復元</div><div>{plan.rollback}</div></div>
            <div style={{ fontSize: 10.5, color: "var(--text-faint)", lineHeight: 1.6 }}>
              コンソール・実iPad（/approve）のどちらからでも決裁できます。
              サーバが計画の版・ハッシュ・期限を照合し、二重承認や古い画面からの承認を拒否します。
            </div>
          </>
        )}
        {!plan && <div style={{ fontSize: 12, color: "var(--text-faint)" }}>承認待ちの変更計画はありません。</div>}
      </div>

      {/* 右: iPad ベゼル風 承認端末（常設埋め込み） */}
      <div style={{ flex: "none", display: "flex", flexDirection: "column" }}>
        <IpadFrame>
          <ApprovalScreen bundle={bundle} compact />
        </IpadFrame>
      </div>
    </div>
  );
}

function RemainChip({ bundle }: { bundle: Bundle }) {
  const { remainStr } = useApproval(bundle);
  return <span style={{ fontFamily: "var(--mono)" }}>{remainStr}</span>;
}
