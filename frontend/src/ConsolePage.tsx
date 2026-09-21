import { useEffect, useState } from "react";
import { useBundle, useConfig, post } from "./api";
import { Topology } from "./components/Topology";
import { EvidenceFeed } from "./components/Panels";
import { PhaseStage } from "./components/PhaseStage";
import { TimelineCard } from "./components/Timeline";
import { ApprovalScreen, RejectedExits } from "./components/Approval";
import { useElapsed } from "./components/Chrome";
import { TopologyUpload, type TopologyDocument } from "./components/TopologyUpload";
import { FailoverTimeline, FailoverNote } from "./components/FailoverTimeline";
import { InvestigationLog } from "./components/InvestigationLog";
import { CloneCheck } from "./components/CloneCheck";
import { readSourceLabel } from "./components/Plain";

const RUNNING = ["RECEIVED", "INVESTIGATING", "VALIDATING_PLAN", "APPLYING", "VERIFYING", "ROLLING_BACK"];
const STEPS = ["申告", "原因を探す", "安全に検証", "人が承認", "業務復旧"];

export default function ConsolePage() {
  const { bundle, connected, pulse, failover, refresh } = useBundle();
  const { cfg } = useConfig();
  const inc = bundle.incident;
  const status = inc?.status;
  const elapsed = useElapsed(inc);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [details, setDetails] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [document, setDocument] = useState<TopologyDocument | null>(null);
  const documentBusy = document?.status === "processing";
  const documentReady = !document || (document.status === "ready" && document.result?.comparison?.ok);
  useEffect(() => { window.scrollTo({ top: 0, behavior: "instant" }); }, [inc?.id, status]);
  const running = RUNNING.includes(status ?? "");
  const done = status === "SERVICE_RESTORED" || status === "RESOLVED";
  const waiting = status === "AWAITING_APPROVAL";
  const plan = bundle.plans.at(-1);
  const findings = bundle.hypotheses.filter(h => h.status === "supported");
  const latest = bundle.steps.at(-1);
  const vlm = bundle.evidence.find(e => e.tool === "vlm_read_topology")?.result;
  const rejected = bundle.approvals.at(-1)?.decision === "rejected";
  const needsHuman = status === "NEEDS_HUMAN";
  const activePath = pulse?.active_path === "r2" ? "r2" : "r1";
  // Simulator timestamps are UTC, while incident timestamps use server local time.
  const pulseTime = pulse ? new Date(`${pulse.at}Z`).toLocaleTimeString("ja-JP", { hour12: false }) : "";
  const mode = inc?.route_label ?? (cfg?.agent_mode === "llm" ? "AIによる調査" : cfg ? "決められた手順のデモ" : "接続確認中");
  const step = !inc ? 0 : status === "INVESTIGATING" ? 1 : status === "VALIDATING_PLAN" ? 2 : waiting ? 3 : done || status === "VERIFYING" || status === "APPLYING" ? 4 : 1;
  const heading = !inc ? "受注画面が開かない。原因はどこに？"
    : waiting ? "修正は1件。最後の判断は、人に。"
    : done ? "復旧を確認。次の対応までつなぐ。"
    : status === "VALIDATING_PLAN" ? "本番に触る前に、複製環境で検証。"
    : status === "APPLYING" ? "承認された変更だけを適用中。"
    : status === "VERIFYING" ? "利用者と同じ経路で、復旧を確認。"
    : needsHuman ? (rejected ? "承認しなかったので、何も変えていません。" : "担当者の判断が必要です。")
    : findings.length ? "主回線だけでは説明できない。" : "観測を重ね、原因を絞り込む。";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { setDetails(false); setConfirmReset(false); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const run = async (label: string, fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(label); setError("");
    try { await fn(); refresh(); }
    catch (e: any) { setError(e.message || "処理に失敗しました。再度お試しください。"); }
    finally { setBusy(""); }
  };
  const start = async () => {
    if (!documentReady) { setError("PDFの解析と登録構成の確認を完了してください"); return; }
    await run("調査を開始しています", () => post("/api/incidents", {topology_document_id:document?.id ?? null}));
  };
  const reset = async () => {
    setConfirmReset(false);
    await run("環境をリセットしています", async () => { await post("/api/demo/reset"); setDetails(false); });
  };

  // 「本物のネットワーク」バッジ。最後の主回線チップだけがデモ中に動き、
  // 他が飾りでないことの証明になる。
  const netns = cfg?.sim?.netns_count;
  const footChips: { text: string; tone?: "down" | "up" }[] = [
    { text: netns ? `Linuxの名前空間 ${netns}個で動く実ネットワーク` : "実ネットワーク（隔離環境）" },
    { text: "本物のTLS通信" },
    { text: "telnetは待受中・ポリシーで遮断" },
  ];
  if (pulse && pulse.primary_link_up !== null && pulse.primary_link_up !== undefined) {
    footChips.push(pulse.primary_link_up
      ? { text: "主回線：復旧", tone: "up" }
      : { text: "主回線：切断中", tone: "down" });
  }

  return <div className="demo-app">
    <header className="demo-header">
      <a className="demo-brand" href="/console"><span className="brand-symbol">N</span>NetWalker<span className="brand-caption">ネットワーク復旧エージェント</span></a>
      <div className="demo-actions">
        <span className={`connection ${connected ? "online" : ""}`}>{connected ? "● 接続中" : "○ 再接続中"}</span>
        <button className="btn-outline" onClick={() => setDetails(true)}>技術詳細</button>
        <button className="btn-outline reset-button" disabled={!!busy || running || documentBusy || !connected}
          title={running ? "調査・適用の完了後、または承認待ちにリセットできます" : "環境と表示を初期状態へ戻します。履歴は保存されます"}
          onClick={() => setConfirmReset(true)}>↺ デモをリセット</button>
      </div>
    </header>
    <main className="demo-main">
      <div className="demo-intro"><div><div className="eyebrow">拠点 A / 受注業務</div><h1>{heading}</h1>
        <p className="demo-subtitle">{!inc ? "症状の申告から、調査・検証・承認・復旧までをひとつの案件で。" : latest?.title ?? inc.current_activity}</p></div>
        <div className="mode-summary"><span>{mode}</span>{inc && <strong>{elapsed}<small>今回の処理時間</small></strong>}</div>
      </div>
      <ol className="demo-progress" aria-label="デモの進行">{STEPS.map((label, i) => <li key={label} className={i === step ? "active" : i < step ? "complete" : ""}><span>{i < step ? "✓" : `0${i + 1}`}</span>{label}</li>)}</ol>
      {(busy || error) && <div role={error ? "alert" : "status"} className={`demo-notice ${error ? "error" : ""}`}>{busy || error}</div>}
      {running && <div className="reset-hint">調査・適用中です。リセットは処理完了後、または承認待ちに利用できます。</div>}
      <div className="demo-grid">
        <section className="network-stage">
          {!inc ? <TopologyUpload value={document} onChange={setDocument} /> : <Topology key={inc.id} incident={inc} pulse={pulse} evidence={bundle.evidence} note="案件で確認した構成・原因" />}
          <div className="discovery-row">
            <div><span className="eyebrow">構成の理解</span><p>{readSourceLabel(vlm?.source)}</p></div>
            <div><span className="eyebrow">観測から分かったこと</span><p>{findings.length ? `${findings.length}つの要因を証拠付きで確認` : "観測結果に応じて更新します"}</p></div>
          </div>
        </section>
        <aside className="story-rail">
          <section className={`service-card ${pulse ? pulse.business_ok ? "healthy" : "down" : "unknown"}`} aria-live="polite">
            <div className="service-top"><span>受注サービス</span><span>現在の実測</span></div>
            <h2>{pulse ? pulse.business_ok ? "受注画面に接続できます" : "受注画面に接続できません" : "通信状態を確認しています"}</h2>
            <p>{pulse ? `${activePath === "r2" ? "予備" : "主"}経路を使用 · ${pulseTime} 時点` : "最新の測定値を待っています"}</p>
            {inc && <FailoverNote failover={failover} activePath={activePath} />}
            {done && <div className="service-foot">案件の復旧確認：{inc?.status_history.find(h => ["SERVICE_RESTORED", "RESOLVED"].includes(h.status))?.at.slice(11,19)}{pulse && !pulse.business_ok ? " · 現在は再び不通です" : ""}</div>}
          </section>
          {!inc ? <section className="story-card"><span className="eyebrow">DEMO / 症状から始める</span><h2>「機器は動いているのに、仕事ができない」</h2>
            {failover?.history?.some(h => h.event === "switch_to_backup")
              ? <FailoverTimeline failover={failover} />
              : <p>主回線の切断と、予備経路の設定不備を再現します。調査がどこまで原因を絞れるか、ご覧ください。</p>}
            <p className="intake-document-note">{document ? documentReady ? "解析済みのPDFを調査に使用します。" : "左の構成図の解析・確認を完了してください。" : "左で構成図を選べます。未選択の場合は登録済み構成を使用します。"}</p>
            <button className="btn-outline" disabled={!!busy || documentBusy || !connected || !pulse || !pulse.business_ok} onClick={() => run("複合障害を再現しています", () => post("/api/demo/inject", {fault:"both"}))}>① 複合障害を再現</button>
            <button className="btn-primary" disabled={!!busy || !documentReady || !connected || !pulse || pulse.business_ok} onClick={start}>② 申告して調査を開始 →</button>
          </section> : waiting ? <section className="story-card approval-focus"><ApprovalScreen bundle={bundle} compact /></section>
          : done ? <section className="story-card result-card"><span className="eyebrow">今回の対応結果</span><h2>業務復旧を確認しました</h2><p>適用後に業務通信と禁止通信の遮断を検証。最新の通信状態は上の実測表示で確認できます。</p>
            {inc.residual_issues.map(r => <div className="residual" key={r.title}><b>継続対応：{r.title}</b><p>{r.action}</p><small>{r.assignee}</small></div>)}
            <button className="btn-outline" disabled={!!busy || !connected} onClick={() => setConfirmReset(true)}>↺ リセットして、もう一度</button>
          </section> : needsHuman && rejected
          ? <section className="story-card"><span className="eyebrow">承認されませんでした</span><h2>ネットワークには何も変更していません</h2>
            <RejectedExits bundle={bundle} onReset={() => setConfirmReset(true)} />
          </section>
          : <section className="story-card" aria-live="polite"><span className="eyebrow">{status === "VALIDATING_PLAN" ? "修正案の事前検証" : "調査の進行"}</span><h2>{latest?.title ?? "調査を開始しています"}</h2>
            <InvestigationLog steps={bundle.steps} evidence={bundle.evidence} onOpenDetails={() => setDetails(true)} />
            {findings.map((h, i) => <div className="finding" key={h.id}><b>要因 {i + 1}</b><p>{(h.text_plain ?? h.text).replace(/^障害[A-Z]:\s*/, "")}</p><small>証拠 {h.evidence_ids.length}件</small></div>)}
            <CloneCheck plan={plan} compact />
          </section>}
        </aside>
      </div>
      <footer className="demo-footer">
        <span className="foot-chips">
          {footChips.map(c => <span key={c.text} className={`foot-chip${c.tone ? ` ${c.tone}` : ""}`}>{c.text}</span>)}
        </span>
        <span>調査 → 複製環境で検証 → 人が承認 → 復旧確認</span>
      </footer>
    </main>
    {details && <div className="modal-backdrop"><section className="detail-modal" role="dialog" aria-modal="true" aria-label="技術詳細"><div className="detail-heading"><h2>証拠と実行記録</h2><button autoFocus className="btn-outline" onClick={() => setDetails(false)}>閉じる</button></div><div className="detail-grid"><PhaseStage key={inc?.id ?? "empty"} bundle={bundle} onStart={start}/><EvidenceFeed evidence={bundle.evidence}/></div><TimelineCard bundle={bundle}/></section></div>}
    {confirmReset && <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="reset-title" className="reset-dialog"><span className="eyebrow">次のデモの準備</span><h2 id="reset-title">環境を初期状態に戻しますか？</h2><p>障害を解除して案件表示をクリアします。過去の証拠・実行履歴は保存されます。承認待ちの計画は適用できなくなります。</p><div><button autoFocus className="btn-outline" onClick={() => setConfirmReset(false)}>キャンセル</button><button className="btn-primary" disabled={!!busy || running} onClick={reset}>リセットする</button></div></section></div>}
  </div>;
}
