// iPad 承認・業務確認画面（/approve）。同一Wi-Fiの実iPadで開く（フル画面・タッチ最適化）。
// 承認UI本体は components/Approval.tsx を共有（コンソール内 ApprovalStage と同一実装）。
// 対象・計画版・ハッシュ・期限をサーバで照合し、古い画面からの承認は拒否される（M-14）。

import { useState } from "react";
import { useBundle, post } from "./api";
import { ApprovalScreen } from "./components/Approval";

export default function ApprovePage() {
  const { bundle } = useBundle();
  const [bizResult, setBizResult] = useState<any>(null);
  const [bizBusy, setBizBusy] = useState(false);

  const inc = bundle.incident;

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

  const footer = (
    <>
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
    </>
  );

  return <ApprovalScreen bundle={bundle} footer={footer} />;
}
