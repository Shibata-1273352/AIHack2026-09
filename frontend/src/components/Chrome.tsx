// サイドバー・ヘッダ（ui-spec §3.2 / §3.3 / §4.1 / §4.3）

import { useEffect, useState } from "react";
import type { Bundle, Incident } from "../types";

export const STEP_NAMES = [
  "受付・構成図", "構成理解（図とAIの照合）", "自律調査",
  "原因提示・承認", "自動復旧", "復旧確認・引き継ぎ",
];

export function currentStep(b: Bundle): number {
  const inc = b.incident;
  if (!inc) return 1;
  switch (inc.status) {
    case "RECEIVED": return 1;
    case "INVESTIGATING":
      return b.hypotheses.length > 0 ? 3
        : b.evidence.some((e) => e.tool === "vlm_read_topology") ? 2 : 2;
    case "VALIDATING_PLAN":
    case "AWAITING_APPROVAL": return 4;
    case "APPLYING":
    case "ROLLING_BACK": return 5;
    case "VERIFYING": return 6;
    case "SERVICE_RESTORED":
    case "RESOLVED": return 6;
    case "NEEDS_HUMAN": {
      if (b.executions.length) return 6;
      if (b.plans.length) return 4;
      return b.hypotheses.length ? 3 : 2;
    }
    default: return 1;
  }
}

const SM_DOT = (s: string) =>
  s === "SERVICE_RESTORED" || s === "RESOLVED" ? "#1f8a5b"
    : s === "NEEDS_HUMAN" ? "#b9770e" : "#1f5fbf";

export function Sidebar({ bundle, modeNote }: { bundle: Bundle; modeNote: string }) {
  const inc = bundle.incident;
  const step = currentStep(bundle);
  const finished = inc && (inc.status === "SERVICE_RESTORED" || inc.status === "RESOLVED");
  return (
    <aside className="sidebar">
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 6px" }}>
        <div style={{
          width: 30, height: 30, borderRadius: 9,
          background: "linear-gradient(135deg,#5b93f5,#1f5fbf)",
          boxShadow: "0 4px 12px -4px rgba(59,116,217,.7)",
          display: "grid", placeItems: "center", fontWeight: 700, fontSize: 14, color: "#fff",
        }}>N</div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: ".02em" }}>NetWalker</div>
          <div style={{ fontSize: 10.5, color: "#9aa4b1" }}>障害調査エージェント</div>
        </div>
      </div>

      <div style={{
        background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.07)",
        borderRadius: 12, padding: "12px 12px",
      }}>
        <div style={{ fontSize: 10.5, color: "#9aa4b1", letterSpacing: ".06em" }}>案件</div>
        <div style={{ fontFamily: "var(--mono)", fontSize: 13, marginTop: 2 }}>
          {inc ? inc.id.toUpperCase() : "—"}
        </div>
        <div style={{ fontSize: 12, color: "#cfd5dd", marginTop: 6 }}>
          {inc ? `${inc.site}／${inc.symptom.split("。")[0]}` : "申告待ち"}
        </div>
        {inc && (
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 8, fontSize: 11 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: SM_DOT(inc.status) }} />
            <span style={{ fontFamily: "var(--mono)", color: "#cfd5dd" }}>{inc.status}</span>
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ fontSize: 10.5, color: "#9aa4b1", letterSpacing: ".06em", padding: "0 10px 6px" }}>工程</div>
        {STEP_NAMES.map((name, i) => {
          const n = i + 1;
          const done = n < step || (n === step && finished);
          const cur = n === step && !finished;
          return (
            <div key={n} className={`step-btn ${cur ? "current" : ""} ${done ? "done" : ""}`}>
              <span className="step-num">{done ? "✓" : n}</span>
              <span style={{ flex: 1 }}>{name}</span>
              <span style={{ fontSize: 10, color: "#9aa4b1" }}>
                {done ? "完了" : cur ? "進行中" : ""}
              </span>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: "auto", padding: "0 6px", fontSize: 10.5, color: "#7f8a97", lineHeight: 1.6 }}>
        <div style={{
          marginBottom: 8, padding: "8px 10px", borderRadius: 8,
          background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.07)",
          fontFamily: "var(--mono)", fontSize: 10, color: "#cfd5dd", lineHeight: 1.6,
        }}>
          {modeNote}
        </div>
        実通信を伴う擬似ネットワーク上のデモ。観測・変更はすべて実測です。
      </div>
    </aside>
  );
}

export function useElapsed(inc: Incident | null): string {
  const [, force] = useState(0);
  useEffect(() => {
    const t = setInterval(() => force((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);
  if (!inc) return "00:00";
  const terminal = ["SERVICE_RESTORED", "RESOLVED", "CANCELLED"].includes(inc.status);
  let endMs = Date.now();
  if (terminal) {
    const last = inc.status_history[inc.status_history.length - 1];
    endMs = new Date(last.at).getTime();
  }
  const sec = Math.max(0, Math.floor((endMs - inc.started_ms) / 1000));
  const mm = String(Math.floor(sec / 60)).padStart(2, "0");
  const ss = String(sec % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

export function bizChip(inc: Incident | null): { label: string; bg: string; fg: string } {
  if (!inc) return { label: "申告中", bg: "#f4f6f9", fg: "#5d6773" };
  if (inc.business_status === "down") return { label: "不通 · 受注業務", bg: "#fbeeec", fg: "#c73a2b" };
  if (inc.business_status === "ok") {
    const residual = inc.residual_issues.length > 0;
    return residual
      ? { label: "暫定復旧（予備経路）", bg: "#e6f4ec", fg: "#1f8a5b" }
      : { label: "正常 · 受注業務", bg: "#e6f4ec", fg: "#1f8a5b" };
  }
  return { label: "確認中 · 受注業務", bg: "#f4f6f9", fg: "#5d6773" };
}

export function HeaderBar({ bundle, connected }: { bundle: Bundle; connected: boolean }) {
  const inc = bundle.incident;
  const elapsed = useElapsed(inc);
  const biz = bizChip(inc);
  return (
    <header className="header">
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="hlabel">現在の処理</div>
        <div style={{ fontSize: 15, fontWeight: 700, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis" }}>
          {inc ? inc.current_activity : "構成図と症状を確認して調査を開始します"}
        </div>
      </div>
      <div style={{ display: "flex", gap: 24, flexWrap: "nowrap", flex: "none" }}>
        <div>
          <div className="hlabel">業務状態</div>
          <span className="chip" style={{ marginTop: 3, background: biz.bg, color: biz.fg }}>{biz.label}</span>
        </div>
        <div>
          <div className="hlabel">経過時間</div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 15, marginTop: 3 }}>{elapsed}</div>
        </div>
        <div>
          <div className="hlabel">担当</div>
          <div style={{ fontSize: 13, marginTop: 4 }}>
            NetWalker <span style={{ color: "var(--text-faint)" }}>
              {inc?.status === "NEEDS_HUMAN" ? "→ 担当者対応待ち" : "· 自律対応中"}
            </span>
          </div>
        </div>
        <div>
          <div className="hlabel">接続</div>
          <div style={{ fontSize: 13, marginTop: 4, color: connected ? "var(--green)" : "var(--red)" }}>
            {connected ? "● live" : "○ 再接続中…"}
          </div>
        </div>
      </div>
    </header>
  );
}
