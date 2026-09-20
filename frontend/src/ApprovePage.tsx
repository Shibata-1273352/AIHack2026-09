// iPad 承認・業務確認画面（/approve）。同一Wi-Fiの実iPadで開く（フル画面・タッチ最適化）。
// 対象・計画版・ハッシュ・期限をサーバで照合し、古い画面からの承認は拒否される（M-14）。

import { useEffect, useState } from "react";
import { useBundle, post } from "./api";

function useClock(): string {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

export default function ApprovePage() {
  const { bundle, connected } = useBundle();
  const clock = useClock();
  const [approver, setApprover] = useState("田中（変更承認権限）");
  const [error, setError] = useState("");
  const [bizResult, setBizResult] = useState<any>(null);
  const [bizBusy, setBizBusy] = useState(false);
  const [, tickState] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tickState((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const inc = bundle.incident;
  const ap = bundle.approvals[bundle.approvals.length - 1];
  const plan = ap ? bundle.plans.find((p) => p.id === ap.plan_id) : bundle.plans[bundle.plans.length - 1];

  const remain = ap && ap.decision === "pending"
    ? Math.max(0, Math.floor(ap.expires_epoch - Date.now() / 1000)) : 0;
  const remainStr = `${Math.floor(remain / 60)}:${String(remain % 60).padStart(2, "0")}`;

  const decide = async (decision: "approve" | "reject") => {
    if (!inc || !ap || !plan) return;
    setError("");
    try {
      await post(`/api/incidents/${inc.id}/approval`, {
        plan_id: ap.plan_id, plan_hash: ap.plan_hash, decision, approver,
      });
    } catch (e: any) {
      setError(e.message);
    }
  };

  const checkBusiness = async () => {
    setBizBusy(true);
    setBizResult(null);
    try { setBizResult(await post("/api/business_check")); }
    catch (e: any) { setBizResult({ error: e.message }); }
    finally { setBizBusy(false); }
  };

  const card: React.CSSProperties = {
    background: "#fff", borderRadius: 12, padding: "12px 14px",
    border: "1px solid rgba(17,24,39,.06)", boxShadow: "0 1px 2px rgba(17,24,39,.04)",
  };
  const lbl: React.CSSProperties = { fontSize: 11, color: "#5d6773" };

  const statusLine = (() => {
    if (!inc) return null;
    switch (inc.status) {
      case "APPLYING": return { t: "実行中 · 承認された差分を適用しています", c: "#1f5fbf" };
      case "VERIFYING": return { t: "検証中 · 独立検証器で業務テストを実行", c: "#1f5fbf" };
      case "SERVICE_RESTORED": return { t: "業務復旧 · 主回線の対応は継続（残存課題あり）", c: "#1f8a5b" };
      case "RESOLVED": return { t: "解決済み", c: "#1f8a5b" };
      case "NEEDS_HUMAN": return { t: "担当者対応待ち（NEEDS_HUMAN）", c: "#b9770e" };
      case "ROLLING_BACK": return { t: "復元中", c: "#b9770e" };
      default: return null;
    }
  })();

  return (
    <div style={{
      minHeight: "100vh", background: "linear-gradient(180deg,#fbfbfd,#f2f4f7)",
      display: "flex", flexDirection: "column", maxWidth: 560, margin: "0 auto",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 18px 0", fontSize: 11, color: "#5d6773", fontWeight: 600 }}>
        <span>{clock}</span>
        <span>iPad · 承認端末 {connected ? "· 接続中" : "· 再接続中…"}</span>
      </div>

      <div style={{ padding: "16px 18px 8px" }}>
        <div style={lbl}>変更承認</div>
        <div style={{ fontSize: 17, fontWeight: 700, marginTop: 2 }}>
          {inc ? `${inc.id.toUpperCase()} · ${inc.site}` : "案件なし"}
        </div>
        {plan && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "#5d6773", marginTop: 2 }}>
            {plan.id.toUpperCase()}-v{plan.version} · hash {plan.hash.slice(0, 8)}
            {ap?.decision === "pending" && ` · 有効期限 ${remainStr}`}
          </div>
        )}
      </div>

      {!plan && (
        <div style={{ padding: "24px 18px", fontSize: 13.5, color: "#5d6773", lineHeight: 1.7 }}>
          承認待ちの変更計画はありません。<br />
          調査が完了し事前検証に合格すると、この画面に承認依頼が表示されます。
        </div>
      )}

      {plan && (
        <div style={{ padding: "0 18px", display: "flex", flexDirection: "column", gap: 8, fontSize: 12.5 }}>
          <div style={card}>
            <div style={lbl}>変更内容</div>
            <div style={{ marginTop: 2, lineHeight: 1.5 }}>{plan.title}</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, marginTop: 4, color: "#5d6773", whiteSpace: "pre-wrap" }}>{plan.diff}</div>
          </div>
          <div style={card}>
            <div style={lbl}>想定影響</div>
            <div style={{ marginTop: 2, lineHeight: 1.5 }}>{plan.impact}</div>
          </div>
          <div style={card}>
            <div style={lbl}>事前検証（検証用環境の複製で実測）</div>
            <div style={{ marginTop: 2, lineHeight: 1.5, color: plan.validation?.verified ? "#1f8a5b" : "#c73a2b", fontWeight: 600 }}>
              {plan.validation?.verified
                ? "複製一致 · 業務テスト 3/3 · 禁止通信 遮断維持 · 合格"
                : "未検証または不合格"}
            </div>
          </div>
          <div style={card}>
            <div style={lbl}>失敗時の復元</div>
            <div style={{ marginTop: 2, lineHeight: 1.5 }}>{plan.rollback}</div>
          </div>
        </div>
      )}

      <div style={{ marginTop: "auto", padding: "16px 18px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
        {error && (
          <div style={{ background: "#fbeeec", color: "#c73a2b", borderRadius: 11, padding: 12, fontSize: 12.5, fontWeight: 600 }}>
            {error}
          </div>
        )}

        {statusLine && (
          <div style={{
            background: statusLine.c === "#1f8a5b" ? "#e6f4ec" : statusLine.c === "#b9770e" ? "#fdf3e7" : "#eef3fb",
            color: statusLine.c, borderRadius: 11, padding: 12, fontSize: 12.5, fontWeight: 600, textAlign: "center",
          }}>
            {statusLine.t}
          </div>
        )}

        {ap?.decision === "pending" && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, color: "#5d6773" }}>
              <span>承認者：
                <input value={approver} onChange={(e) => setApprover(e.target.value)}
                  style={{ border: "1px solid #d6dbe1", borderRadius: 6, padding: "4px 8px", font: "inherit", marginLeft: 4 }} />
              </span>
              <span style={{ fontWeight: 600, color: "#b9770e" }}>承認待ち</span>
            </div>
            <button className="btn-green" style={{ borderRadius: 13, padding: 14 }} onClick={() => decide("approve")}>
              承認して適用へ
            </button>
            <button className="btn-outline" style={{ borderRadius: 11, color: "#c73a2b" }} onClick={() => decide("reject")}>
              却下（対象環境は変更されません）
            </button>
          </>
        )}

        {ap && ap.decision !== "pending" && (
          <div style={{
            background: ap.decision === "approved" ? "#e6f4ec" : "#fbeeec",
            color: ap.decision === "approved" ? "#1f8a5b" : "#c73a2b",
            borderRadius: 11, padding: 12, fontSize: 12.5, fontWeight: 600, textAlign: "center",
          }}>
            {ap.decision === "approved"
              ? `承認済み · ${ap.decided_at?.slice(11)} · ${ap.approver} · Macへ同期`
              : ap.decision === "rejected" ? "却下 · 対象環境は変更されません" : "期限切れ · 再検証・再承認が必要です"}
          </div>
        )}

        {/* 業務確認（再読込）: キャッシュを避け、当該試行の結果と確認時刻を表示（M-14） */}
        {inc && ["VERIFYING", "SERVICE_RESTORED", "RESOLVED"].includes(inc.status) && (
          <div style={{ ...card, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={lbl}>業務確認（拠点クライアント経由の実測 · キャッシュなし）</div>
            <button className="btn-primary" style={{ padding: 12 }} disabled={bizBusy} onClick={checkBusiness}>
              {bizBusy ? "受注画面へ実アクセス中…" : "受注画面を再読込"}
            </button>
            {bizResult && !bizResult.error && (
              <div style={{
                borderRadius: 10, padding: 12, fontSize: 12.5,
                background: bizResult.pass ? "#e6f4ec" : "#fbeeec",
                color: bizResult.pass ? "#1f8a5b" : "#c73a2b",
              }}>
                <div style={{ fontWeight: 700 }}>
                  {bizResult.pass ? "受注画面 表示成功（3回連続）" : "受注画面 表示失敗"}
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 11, marginTop: 4, color: "#1b2430" }}>
                  {bizResult.attempts?.map((a: any) =>
                    `試行${a.attempt}: ${a.ok ? `200 · ${a.ms}ms` : "失敗"}`).join("　")}
                </div>
                <div style={{ fontSize: 11, marginTop: 4, color: "#5d6773" }}>確認時刻 {bizResult.at}</div>
              </div>
            )}
            {bizResult?.error && (
              <div style={{ fontSize: 12, color: "#c73a2b" }}>{bizResult.error}</div>
            )}
          </div>
        )}

        {inc?.status === "SERVICE_RESTORED" && inc.residual_issues.length > 0 && (
          <div style={{ background: "#fdf3e7", border: "1px solid rgba(185,119,14,.12)", borderRadius: 11, padding: 12, fontSize: 12 }}>
            <b style={{ color: "#b9770e" }}>残存課題</b>：{inc.residual_issues[0].title}（担当候補：{inc.residual_issues[0].assignee}）
          </div>
        )}
      </div>
    </div>
  );
}
