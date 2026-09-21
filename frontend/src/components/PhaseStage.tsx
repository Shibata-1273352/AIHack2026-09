// 右上のフェーズステージ（560×約540）。工程の進行に自動追従し、タブで手動固定もできる
// （質疑で「さっきのVLM結果」に戻れる。次の工程遷移で自動追従へ復帰）。
// タブの有効化はデータ到着基準（currentStep の判定に依存しない）。

import { useEffect, useRef, useState } from "react";
import type { Bundle } from "../types";
import { ApprovalStage } from "./Approval";
import {
  ApplyCard, CauseAndPlanCard, HypothesesCard, IntakeForm, VerifyCard, VlmCard,
} from "./Panels";

type Tab = "vlm" | "hypo" | "plan" | "approval" | "apply" | "verify";

const TABS: { key: Tab; label: string }[] = [
  { key: "vlm", label: "構成図" },
  { key: "hypo", label: "仮説" },
  { key: "plan", label: "計画" },
  { key: "approval", label: "承認" },
  { key: "apply", label: "適用" },
  { key: "verify", label: "検証" },
];

const TITLES: Record<Tab, string> = {
  vlm: "構成理解（マルチモーダルAIの読取と照合）", hypo: "仮説と次の検査", plan: "根本原因と変更計画",
  approval: "変更承認", apply: "承認された差分のみ適用", verify: "復旧確認・引き継ぎ",
};

function availability(b: Bundle): Record<Tab, boolean> {
  const st = b.incident?.status ?? "";
  return {
    vlm: b.evidence.some((e) => e.tool === "vlm_read_topology"),
    hypo: b.hypotheses.length > 0,
    plan: b.plans.length > 0,
    approval: b.approvals.length > 0,
    apply: b.executions.length > 0 || st === "APPLYING" || st === "ROLLING_BACK",
    verify: ["VERIFYING", "SERVICE_RESTORED", "RESOLVED"].includes(st),
  };
}

function autoTab(b: Bundle, avail: Record<Tab, boolean>): Tab | null {
  switch (b.incident?.status) {
    case "INVESTIGATING":
      return avail.hypo ? "hypo" : avail.vlm ? "vlm" : null;
    case "VALIDATING_PLAN":
      return avail.plan ? "plan" : avail.hypo ? "hypo" : null;
    case "AWAITING_APPROVAL":
      return "approval";
    case "APPLYING":
    case "ROLLING_BACK":
      return "apply";
    case "VERIFYING":
    case "SERVICE_RESTORED":
    case "RESOLVED":
      return "verify";
    case "NEEDS_HUMAN":
      // 直前の表示を保持する（データの到達度から復元）
      if (b.executions.length > 0) return "apply";
      if (avail.approval) return "approval";
      if (avail.plan) return "plan";
      if (avail.hypo) return "hypo";
      return avail.vlm ? "vlm" : null;
    default:
      return null;
  }
}

export function PhaseStage({ bundle, onStart, style }: {
  bundle: Bundle; onStart: () => Promise<void>; style?: React.CSSProperties;
}) {
  const inc = bundle.incident;
  const intake = !inc || inc.status === "RECEIVED";
  const avail = availability(bundle);
  const auto = autoTab(bundle, avail);

  const [pinned, setPinned] = useState<Tab | null>(null);
  const prevAuto = useRef<Tab | null>(auto);
  useEffect(() => {
    // 工程が進んだら手動固定を解除して自動追従へ復帰
    if (auto !== prevAuto.current) {
      prevAuto.current = auto;
      setPinned(null);
    }
  }, [auto]);

  const active: Tab | null = pinned && avail[pinned] ? pinned : auto;
  const ap = bundle.approvals[bundle.approvals.length - 1];
  const awaiting = inc?.status === "AWAITING_APPROVAL" && ap?.decision === "pending";

  return (
    <section className={`card${awaiting && active === "approval" ? " amber-glow" : ""}`}
      style={{ minWidth: 0, minHeight: 0, gap: 10, ...style }}>
      <div className="card-head" style={{ flex: "none" }}>
        <h2>{intake ? "症状の申告" : active ? TITLES[active] : "調査待機"}</h2>
        {!intake && (
          <span style={{ marginLeft: "auto", display: "flex", gap: 4, alignItems: "center" }}>
            {TABS.map((t) => (
              <button key={t.key} className={`ptab${active === t.key ? " on" : ""}`}
                disabled={!avail[t.key]}
                onClick={() => setPinned(t.key)}>
                {t.label}
              </button>
            ))}
            {pinned && (
              <button className="ptab" title="工程の進行に自動追従へ戻す" onClick={() => setPinned(null)}>
                自動
              </button>
            )}
          </span>
        )}
      </div>

      <div className="stage-embed fadein" key={intake ? "intake" : active ?? "none"}
        style={{ flex: 1, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
        {intake ? (
          <IntakeForm started={!!inc} onStart={onStart} />
        ) : active === "vlm" ? (
          <VlmCard bundle={bundle} />
        ) : active === "hypo" ? (
          <HypothesesCard hypotheses={bundle.hypotheses} />
        ) : active === "plan" ? (
          <CauseAndPlanCard bundle={bundle} />
        ) : active === "approval" ? (
          <ApprovalStage bundle={bundle} />
        ) : active === "apply" ? (
          <ApplyCard bundle={bundle} />
        ) : active === "verify" ? (
          <VerifyCard bundle={bundle} />
        ) : (
          <div style={{ fontSize: 12.5, color: "var(--text-faint)", padding: 6 }}>
            観測結果の到着を待っています。
          </div>
        )}
      </div>
    </section>
  );
}
