// Mac 調査コンソール（/console）。SSEイベント駆動でサーバの案件状態を表示する。

import { useBundle, useConfig, post } from "./api";
import { Sidebar, HeaderBar, currentStep } from "./components/Chrome";
import { Topology } from "./components/Topology";
import {
  IntakeCard, VlmCard, HypothesesCard, EvidenceCard,
  CauseAndPlanCard, ApplyCard, VerifyCard, AwaitingApprovalHint, NeedsHumanBanner,
} from "./components/Panels";
import { TimelineCard, TechStrip } from "./components/Timeline";

function topoNote(step: number, bundle: ReturnType<typeof useBundle>["bundle"]): string {
  const inc = bundle.incident;
  if (!inc) return "";
  if (step <= 2) return "図由来。識別子は登録機器と照合中";
  if (step === 3) return "探索位置を青で表示。実測で確認した機器のみ確定";
  if (inc.status === "SERVICE_RESTORED" || inc.status === "RESOLVED") return "予備経路のACLを修正済み";
  if (bundle.executions.length > 0) return "予備経路のACLを修正済み";
  return "複合障害：主回線断 ＋ 予備経路ACL";
}

export default function ConsolePage() {
  const { bundle, connected } = useBundle();
  const cfg = useConfig();
  const inc = bundle.incident;
  const step = currentStep(bundle);
  const active = inc && !["SERVICE_RESTORED", "RESOLVED", "CANCELLED"].includes(inc.status);

  const modeNote = inc
    ? (inc.route_label ?? inc.mode)
    : cfg
      ? `agent=${cfg.agent_mode} · route=${cfg.route_mode}${cfg.has_api_key ? "" : "（キー未設定）"}`
      : "";

  const startIncident = async () => { await post("/api/incidents", {}); };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "244px minmax(0,1fr)", minHeight: "100vh" }}>
      <Sidebar bundle={bundle} modeNote={modeNote} />
      <main style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <HeaderBar bundle={bundle} connected={connected} />
        <div style={{
          display: "grid", gap: 16, padding: "20px 28px 32px",
          gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,500px),1fr))",
          alignItems: "start",
        }}>
          {!inc || inc.status === "RECEIVED" ? (
            <IntakeCard started={!!inc} onStart={startIncident} />
          ) : (
            <>
              <Topology incident={inc} note={topoNote(step, bundle)} />
              <div style={{ order: 2, display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
                <NeedsHumanBanner bundle={bundle} />
                {step >= 4 && <AwaitingApprovalHint bundle={bundle} />}
                {step === 2 && <VlmCard bundle={bundle} />}
                {step >= 3 && <HypothesesCard hypotheses={bundle.hypotheses} />}
                {step >= 4 && <CauseAndPlanCard bundle={bundle} />}
                {step >= 5 && <ApplyCard bundle={bundle} />}
                {step >= 6 && <VerifyCard bundle={bundle} />}
                <EvidenceCard evidence={bundle.evidence} />
                {step >= 3 && <VlmCard bundle={bundle} />}
              </div>
              <TimelineCard bundle={bundle} />
              <TechStrip bundle={bundle} modeNote={modeNote} />
            </>
          )}
        </div>
      </main>
    </div>
  );
}
