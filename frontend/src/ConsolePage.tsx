// Mac 調査コンソール（/console）。SSEイベント駆動でサーバの案件状態を表示する。
// 1920×1080 の論理ステージ（components/Stage.tsx が 4K/ノートPC へ拡縮）に
// 「調査 → 承認 → 復旧」の全てをページスクロール無しの一画面で配置する。
//
//   ┌─244─┬─ HeaderBar(64) ──────────────────────────────┐
//   │ サ  │ ┌ topo 構成図ヒーロー ─────┐ ┌ rail 560 ────┐ │
//   │ イ  │ │ (約1062×702)             │ │ PhaseStage   │ │
//   │ ド  │ ├ ribbon 仮説/成果 (96) ───┤ │ (540)        │ │
//   │ バ  │ ├ tl タイムライン+KPI(160) ┤ │ EvidenceFeed │ │
//   └─────┴──────────────────────────────────────────────┘

import { useBundle, useConfig, post } from "./api";
import { Sidebar, HeaderBar, currentStep } from "./components/Chrome";
import { Topology } from "./components/Topology";
import { DiagramPreviewCard, EvidenceFeed, InsightRibbon } from "./components/Panels";
import { PhaseStage } from "./components/PhaseStage";
import { TimelineCard } from "./components/Timeline";
import { OpsDrawer } from "./components/OpsDrawer";
import { STAGE_W, STAGE_H } from "./components/Stage";

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
  const { bundle, connected, pulse } = useBundle();
  const cfg = useConfig();
  const inc = bundle.incident;
  const step = currentStep(bundle);
  const intake = !inc || inc.status === "RECEIVED";

  const modeNote = inc
    ? (inc.route_label ?? inc.mode)
    : cfg
      ? `agent=${cfg.agent_mode} · route=${cfg.route_mode}${cfg.has_api_key ? "" : "（キー未設定）"}`
      : "";

  const startIncident = async () => { await post("/api/incidents", {}); };

  // グリッド子は全て minWidth/minHeight 0 のラッパで包む（はみ出し事故の定番対策）
  const cell = (area: string): React.CSSProperties =>
    ({ gridArea: area, minWidth: 0, minHeight: 0, display: "flex" });

  return (
    <div style={{
      display: "grid", gridTemplateColumns: "244px minmax(0,1fr)",
      width: STAGE_W, height: STAGE_H,
    }}>
      <Sidebar bundle={bundle} modeNote={modeNote} />
      <main style={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
        <HeaderBar bundle={bundle} connected={connected} />
        <div style={{
          flex: 1, minHeight: 0, minWidth: 0,
          display: "grid", gap: 14, padding: "14px 20px 16px",
          gridTemplateColumns: "minmax(0,1fr) 560px",
          gridTemplateRows: "minmax(0,1fr) 96px 160px",
          gridTemplateAreas: '"topo rail" "ribbon rail" "tl rail"',
        }}>
          <div style={cell("topo")}>
            {intake && !bundle.evidence.some((e) => e.tool === "vlm_read_topology")
              ? <DiagramPreviewCard pulse={pulse} style={{ flex: 1 }} />
              : <Topology incident={inc} note={topoNote(step, bundle)}
                  pulse={pulse} evidence={bundle.evidence} style={{ flex: 1 }} />}
          </div>
          <div style={cell("ribbon")}>
            <InsightRibbon bundle={bundle} style={{ flex: 1 }} />
          </div>
          <div style={cell("tl")}>
            <TimelineCard bundle={bundle} style={{ flex: 1 }} />
          </div>
          <div style={{
            gridArea: "rail", minWidth: 0, minHeight: 0,
            display: "grid", gridTemplateRows: "minmax(0,540px) minmax(0,1fr)", gap: 14,
          }}>
            <PhaseStage bundle={bundle} onStart={startIncident} />
            <EvidenceFeed evidence={bundle.evidence} />
          </div>
        </div>
      </main>
      <OpsDrawer />
    </div>
  );
}
