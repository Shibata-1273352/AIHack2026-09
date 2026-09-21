// 右パネル群: 受付 / VLM読取 / 仮説 / 証拠フィード / 変更計画 / 適用 / 復旧確認 / リボン
// すべてサーバの実データ（証拠・計画・実行記録）を表示する。

import { useEffect, useRef, useState } from "react";
import type { Approval, Bundle, Evidence, Hypothesis, Plan, SimPulse } from "../types";
import { LiveIndicator } from "./Topology";
import { Term, readSourceLabel } from "./Plain";

const AC = { open: "#b9770e", supported: "#c73a2b", rejected: "#8a94a0" } as const;
const AS = { open: "調査中", supported: "支持", rejected: "棄却" } as const;

// ---------------------------------------------------------------- 受付（構成図プレビュー = topo エリア）

export function DiagramPreviewCard({ pulse, style }: { pulse: SimPulse | null; style?: React.CSSProperties }) {
  const activePath = pulse?.active_path === "r2" ? "r2" : "r1";
  return (
    <section className="card" style={{ minWidth: 0, minHeight: 0, ...style }}>
      <div className="card-head">
        <h2>構成図</h2>
        <span className="card-note">管理者登録済み · NW-A-102 · 版 site-A-2026-09-20（調査開始で登録機器表と照合）</span>
        <LiveIndicator pulse={pulse} />
      </div>
      <div style={{
        flex: 1, minHeight: 0, border: "1px solid var(--border-inner)", borderRadius: 10,
        background: "#fbfbfc", padding: 12, display: "flex", flexDirection: "column",
      }}>
        <div style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 8 }}>プレビュー（原図）</div>
        <img src="/api/assets/topology-diagram.png" alt="拠点A構成図"
          style={{ flex: 1, minHeight: 0, width: "100%", objectFit: "contain", display: "block" }} />
      </div>
      {/* 申告前でもシミュレータ実測は動いている（注入の瞬間がここに映る） */}
      <div style={{ borderTop: "1px solid var(--border-divider)", paddingTop: 10, fontSize: 11.5, display: "flex", gap: 14 }}>
        <span style={{ color: "var(--text-muted)" }}>業務経路（実測）: client → gw → {activePath} → srv</span>
        {pulse && (
          <span style={{ marginLeft: "auto", fontWeight: 700, color: pulse.business_ok ? "var(--green)" : "var(--red)" }}>
            {pulse.business_ok ? "業務通信 疎通" : "業務通信 不通"}
          </span>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- 受付（申告フォーム = PhaseStage 内）

export function IntakeForm({ started, onStart }: { started: boolean; onStart: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <>
      {[["拠点", "拠点A（東京・営業所）"],
        ["対象業務", "受注システム（https://order.example.com）"],
        ["症状", "9:40頃から受注画面が開かない。社内チャットは使える。機器のランプは点灯している。"]].map(([l, v]) => (
        <label key={l} style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 12, color: "var(--text-muted)" }}>
          {l}
          <div style={{
            border: "1px solid var(--border-input)", borderRadius: 8, padding: "9px 12px",
            fontSize: 13.5, color: "var(--ink)", background: "#fff",
            lineHeight: l === "症状" ? 1.6 : undefined,
          }}>{v}</div>
        </label>
      ))}
      <div style={{
        background: "var(--bg-subtle)", border: "1px solid var(--border-subtle)", borderRadius: 10,
        padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6,
      }}>
        接続情報・許可範囲は導入時登録済み（拠点A設定 v7）。再入力は不要です。
      </div>
      <button className="btn-primary" disabled={busy || started} style={{ marginTop: "auto" }}
        onClick={async () => { setBusy(true); try { await onStart(); } finally { setBusy(false); } }}>
        {busy || started ? "受付中…" : "調査を開始"}
      </button>
    </>
  );
}

// ---------------------------------------------------------------- VLM 読取

export function VlmCard({ bundle }: { bundle: Bundle }) {
  const ev = bundle.evidence.find((e) => e.tool === "vlm_read_topology");
  if (!ev) return null;
  const r = ev.result;
  const nodes = r.mapped_nodes ?? [];
  const links = r.mapped_links ?? [];
  const pending = (r.comparison?.unmatched_labels?.length ?? 0) + (r.comparison?.missing_registered?.length ?? 0);
  const model = r.model?.resolved_model || r.model?.route || "登録機器表";
  return (
    <section className="card fadein">
      <div className="card-head">
        <h2>構成図の読取結果（マルチモーダルAI）</h2>
        <span className="card-note"><Term plain={readSourceLabel(r.source)} tech={model} /></span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8 }}>
        {[["抽出ノード", String(nodes.length), false],
          ["抽出リンク", String(links.length), false],
          ["確認待ち", String(pending), pending > 0]].map(([l, v, warn]) => (
          <div key={l as string} style={{
            background: warn ? "var(--bg-amber-tint)" : "var(--bg-subtle)",
            border: `1px solid ${warn ? "rgba(185,119,14,.12)" : "var(--border-subtle)"}`,
            borderRadius: 10, padding: 10,
            color: warn ? "var(--amber)" : undefined,
          }}>
            <div style={{ fontSize: 10.5, color: warn ? "var(--amber)" : "var(--text-muted)" }}>{l}</div>
            <div style={{ fontSize: 20, fontWeight: 700, marginTop: 2 }}>{v}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {nodes.map((n: any, i: number) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 10, fontSize: 12.5,
            padding: "7px 10px", borderRadius: 8,
            background: n.registered_id ? "var(--bg-faint)" : "var(--bg-amber-tint)",
          }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, width: 74, flex: "none" }}>
              {n.registered_id ?? "?"}
            </span>
            <span style={{ flex: 1 }}>{n.label}{n.registered_id ? " · 登録機器と一致" : " → 管理者確認待ち（実測で補完）"}</span>
          </div>
        ))}
      </div>
      <div className="dark-panel">
        <div style={{ display: "flex" }}>
          <span style={{ fontSize: 12, color: "#9aa4b1", fontWeight: 600 }}>抽出グラフ（JSON・未修正出力）</span>
          <span style={{ marginLeft: "auto", fontSize: 10.5, color: "#7f8a97" }}>
            {r.registered_version} · {r.source === "vlm" ? "図由来" : r.source}
          </span>
        </div>
        <pre style={{ maxHeight: 180 }}>{JSON.stringify(r.extracted, null, 2)}</pre>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- 仮説

export function HypothesesCard({ hypotheses }: { hypotheses: Hypothesis[] }) {
  return (
    <section className="card fadein">
      <div className="card-head">
        <h2>仮説</h2>
        <span className="card-note">支持・反証は証拠IDに連動</span>
      </div>
      {hypotheses.length === 0 && (
        <div style={{ fontSize: 12.5, color: "var(--text-faint)" }}>まだ仮説はありません。観測を待っています。</div>
      )}
      {hypotheses.map((h) => (
        <div key={h.id} style={{
          border: "1px solid var(--border-inner)", borderLeft: `4px solid ${AC[h.status]}`,
          borderRadius: 8, padding: "10px 12px",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 600 }}>
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-muted)" }}>H{h.seq}</span>
            <span style={{ flex: 1 }}>{h.text}</span>
            <span style={{ fontSize: 11, fontWeight: 600, color: AC[h.status] }}>{AS[h.status]}</span>
          </div>
          {(h.evidence_ids.length > 0 || h.next_check) && (
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
              {h.evidence_ids.length > 0 && <>証拠 {h.evidence_ids.join(", ")}　</>}
              {h.next_check && <>次の検査：{h.next_check}</>}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

// ---------------------------------------------------------------- 証拠（実測）

function evVerdict(e: Evidence): { text: string; color: string } {
  const s = e.summary;
  if (s.includes("不合格") || s.includes("失敗") || s.includes("異常")) return { text: "異常", color: "#c73a2b" };
  if (s.includes("合格") || s.includes("成功") || s.includes("全て UP")) return { text: "確認", color: "#1f8a5b" };
  return { text: "注意", color: "#b9770e" };
}

function rawExcerpt(e: Evidence): string {
  const r = e.result;
  try {
    if (e.tool === "test_business") {
      return r.attempts.map((a: any) =>
        `試行${a.attempt}: ${a.ok ? `200 OK · ${a.ms}ms` : `失敗 (${a.error ?? a.http_code ?? "timeout"})`}`).join("\n");
    }
    if (e.tool === "test_forbidden") return (r.raw?.stdout ?? "").trim();
    if (e.tool === "probe_path") {
      const raw = r.raw ?? {};
      return `$ ${raw.cmd ?? ""}\n${(raw.stdout ?? "").trim() || (raw.stderr ?? "").trim()}`.trim();
    }
    if (e.tool === "observe_node") {
      const obs = r.observations ?? {};
      const parts: string[] = [];
      if (obs.link?.raw?.stdout) parts.push(obs.link.raw.stdout.trim());
      if (obs.route?.raw?.stdout) parts.push(obs.route.raw.stdout.trim());
      if (obs.nft?.raw?.stdout) parts.push(obs.nft.raw.stdout.trim());
      if (obs.failover?.state) parts.push(`failover: ${JSON.stringify(obs.failover.state.active_path)} を使用中`);
      return parts.join("\n").slice(0, 1200);
    }
    if (e.tool === "validate_plan") {
      return [
        `複製一致: ${r.clone_match ? "OK" : "NG"}`,
        `修正前: 業務 ${r.clone_tests_pre?.business?.pass ? "合格" : "不合格"} / 禁止遮断 ${r.clone_tests_pre?.forbidden?.pass ? "維持" : "解除"}`,
        `削除ルール: ${r.applied_in_verify?.deleted_rule ?? "-"}`,
        `修正後: 業務 ${r.clone_tests_post?.business?.pass ? "合格" : "不合格"} / 禁止遮断 ${r.clone_tests_post?.forbidden?.pass ? "維持" : "解除"}`,
      ].join("\n");
    }
    if (e.tool === "apply_plan") return r.deleted_rule ?? "";
  } catch { /* 表示できない形は JSON にフォールバック */ }
  return JSON.stringify(r).slice(0, 400);
}

export function EvidenceFeed({ evidence, style }: { evidence: Evidence[]; style?: React.CSSProperties }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const hoverRef = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);
  // 新着で末尾へ自動追尾（ホバー中＝読んでいる間は停止）
  useEffect(() => {
    if (!hoverRef.current) endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [evidence.length]);

  return (
    <section className="card" style={{ minWidth: 0, minHeight: 0, gap: 8, ...style }}
      onMouseEnter={() => { hoverRef.current = true; }}
      onMouseLeave={() => { hoverRef.current = false; }}>
      <div className="card-head">
        <h2>証拠（実測）</h2>
        <span className="card-note">実コマンド出力 · クリックで生JSON · {evidence.length}件</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
        {evidence.length === 0 && (
          <div style={{ fontSize: 12.5, color: "var(--text-faint)", padding: "8px 2px" }}>
            観測待機中。調査開始で実測コマンドの結果がここへ流れます。
          </div>
        )}
        {evidence.map((e) => {
          const v = evVerdict(e);
          const open = openId === e.id;
          return (
            <div key={e.id} className="ev-row fadein" style={{ cursor: "pointer" }}
              onClick={() => setOpenId(open ? null : e.id)}>
              <div className="ev-time">{e.at.slice(11, 19)}</div>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", minWidth: 0 }}>
                  <span className="tool-chip">{e.tool}</span>
                  <span style={{ fontWeight: 600, fontSize: 11.5 }}>{e.id}</span>
                  <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 600, color: v.color, flex: "none" }}>{v.text}</span>
                </div>
                <div className="clamp1" style={{ marginTop: 2, lineHeight: 1.45 }}>{e.summary}</div>
                <div className={`ev-out ${open ? "" : "clamp2"}`} style={{ maxHeight: open ? undefined : 34, overflow: "hidden" }}>
                  {rawExcerpt(e)}
                </div>
                {open && (
                  <pre className="ev-out" style={{ maxHeight: 200, background: "var(--bg-faint)", padding: 8, borderRadius: 6, overflow: "auto" }}>
                    {JSON.stringify(e.result, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- 根本原因・変更計画・事前検証

export function CauseAndPlanCard({ bundle }: { bundle: Bundle }) {
  const plan = bundle.plans[bundle.plans.length - 1];
  const supported = bundle.hypotheses.filter((h) => h.status === "supported");
  if (!plan) return null;
  const v = plan.validation;
  return (
    <>
      {supported.length > 0 && (
        <section className="card fadein">
          <h2>根本原因（複合障害）</h2>
          {supported.map((h, i) => (
            <div key={h.id} style={{
              display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 12px",
              background: "var(--bg-red-tint)", border: "1px solid rgba(199,58,43,.12)", borderRadius: 10,
            }}>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--red)", fontWeight: 600, flex: "none" }}>
                要因{String.fromCharCode(65 + i)}
              </span>
              <span style={{ fontSize: 12.5, lineHeight: 1.55 }}>
                <b>{h.text}</b>　<span style={{ color: "var(--text-muted)" }}>証拠 {h.evidence_ids.join(", ")}</span>
              </span>
            </div>
          ))}
        </section>
      )}

      <section className="card fadein">
        <div className="card-head">
          <h2>変更計画</h2>
          <span className="card-note" style={{ fontFamily: "var(--mono)" }}>
            {plan.id.toUpperCase()}-v{plan.version} · {plan.hash.slice(0, 6)}
          </span>
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          対象：{plan.body.node} · nftables {plan.body.table}/{plan.body.chain}（拠点→サービス方向）
        </div>
        <pre className="diff-block">
          <span style={{ color: "#8a94a0" }}>table inet fw · chain forward</span>{"\n"}
          <span style={{ color: "#ff8a7a" }}>{plan.diff}</span>{"\n"}
          <span style={{ color: "#8a94a0" }}>  ip daddr 10.0.100.10 tcp dport 23 drop comment "POLICY-DENY-TELNET"   (禁止通信・維持)</span>
        </pre>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 8 }}>
          {[["影響", plan.impact], ["復元", plan.rollback], ["観測前提の鮮度", "適用直前30秒以内に再観測"]].map(([l, t]) => (
            <div key={l} className="subtile"><div className="lbl">{l}</div><div>{t}</div></div>
          ))}
        </div>
      </section>

      {v && (
        <section className="card fadein">
          <div className="card-head">
            <h2>事前検証（検証用環境）</h2>
            <span className="card-note" style={{ color: v.verified ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
              {v.verified ? "複製一致 ✓ · 合格" : `不合格（${v.reason ?? ""}）`}
            </span>
          </div>
          {v.verified && [
            ["複製環境と対象環境の一致（回線・経路・通信ルール・サービス・通信）", "一致"],
            ["修正前の再現：業務テスト", v.pre?.business ? "合格（再現失敗）" : "不合格＝対象環境と同じ"],
            ["修正後：業務テスト HTTPS 受注画面", v.post?.business ? "3/3 成功" : "失敗"],
            ["回帰：禁止通信 telnet(23)", v.post?.forbidden ? "遮断維持" : "遮断解除（不合格）"],
          ].map(([name, val]) => (
            <div key={name} style={{
              display: "flex", alignItems: "center", gap: 10, fontSize: 12.5,
              padding: "6px 0", borderBottom: "1px solid var(--border-divider)",
            }}>
              <span style={{
                width: 18, height: 18, borderRadius: "50%", background: "var(--green)", color: "#fff",
                display: "grid", placeItems: "center", fontSize: 11, flex: "none",
              }}>✓</span>
              <span style={{ flex: 1 }}>{name}</span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-muted)" }}>{val}</span>
            </div>
          ))}
        </section>
      )}
    </>
  );
}

// ---------------------------------------------------------------- 適用・復旧確認・残存課題

export function ApplyCard({ bundle }: { bundle: Bundle }) {
  const inc = bundle.incident!;
  const ap = bundle.approvals[bundle.approvals.length - 1];
  const ex = bundle.executions[bundle.executions.length - 1];
  const plan = bundle.plans[bundle.plans.length - 1];
  const applying = inc.status === "APPLYING";
  const rows: { name: string; detail: string; state: "done" | "run" | "wait" }[] = [
    {
      name: `承認 ${ap?.id.toUpperCase() ?? "—"} と計画版・ハッシュを照合`,
      detail: ap ? `plan=${plan?.id} v${ap.plan_version} hash=${ap.plan_hash.slice(0, 6)} · ${ap.approver ?? ""}` : "",
      state: ap?.decision === "approved" ? "done" : "wait",
    },
    {
      name: "観測前提を再確認（30秒以内）",
      detail: "対象ルール存在 · 業務不通 · 予備経路使用中 → 一致を確認",
      state: ex ? "done" : applying ? "run" : "wait",
    },
    {
      name: "適用前状態を永続化し、承認された差分のみ適用",
      detail: ex ? `EXEC-${ex.execution_id} · 二重適用の防止キー ${ex.idempotency_key.slice(0, 6)}` : "",
      state: ex ? "done" : "wait",
    },
    {
      name: "適用結果を読み取りで照合",
      detail: ex?.deleted_rule ? `削除確認: ${ex.deleted_rule.split("#")[0].trim().slice(0, 60)}…` : "",
      state: ex ? "done" : "wait",
    },
  ];
  return (
    <section className="card fadein">
      <div className="card-head">
        <h2>承認された差分のみ適用</h2>
        {ex && <span className="card-note" style={{ fontFamily: "var(--mono)" }}>EXEC-{ex.execution_id}</span>}
      </div>
      {rows.map((r, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "flex-start", gap: 12, padding: "9px 0",
          borderBottom: "1px solid var(--border-divider)",
        }}>
          <span style={{
            width: 22, height: 22, borderRadius: "50%", flex: "none", marginTop: 1,
            background: r.state === "done" ? "var(--green)" : r.state === "run" ? "var(--blue)" : "var(--gray)",
            color: "#fff", display: "grid", placeItems: "center", fontSize: 12,
          }}>{r.state === "done" ? "✓" : r.state === "run" ? "…" : i + 1}</span>
          <span style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: r.state === "wait" ? "var(--text-faint)" : "var(--ink)" }}>{r.name}</div>
            {r.detail && <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>{r.detail}</div>}
          </span>
        </div>
      ))}
      {applying && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "var(--blue)", fontWeight: 600, padding: "4px 2px" }}>
          <span className="spinner" /> 適用中… 前提を再観測し、承認された差分だけを適用しています
        </div>
      )}
    </section>
  );
}

export function VerifyCard({ bundle }: { bundle: Bundle }) {
  const inc = bundle.incident!;
  const lastEx = bundle.executions[bundle.executions.length - 1];
  const completedAt = inc.status_history.find(h => ["SERVICE_RESTORED", "RESOLVED"].includes(h.status))?.at;
  const bizAfter = [...bundle.evidence].reverse().find(
    (e) => e.tool === "test_business" && e.at >= (lastEx?.at ?? "") && (!completedAt || e.at <= completedAt));
  const forbAfter = [...bundle.evidence].reverse().find(
    (e) => e.tool === "test_forbidden" && e.at >= (lastEx?.at ?? "") && (!completedAt || e.at <= completedAt));
  const verifying = inc.status === "VERIFYING";
  const done = inc.status === "SERVICE_RESTORED" || inc.status === "RESOLVED";

  const rows = [
    {
      name: "HTTPS 受注画面 取得（3回連続）",
      detail: bizAfter?.result?.pass
        ? bizAfter.result.attempts.map((a: any) => `${a.ms}ms`).join(" / ") + " · すべて200"
        : verifying ? "実行中…" : "",
      ok: !!bizAfter?.result?.pass,
    },
    {
      name: "期待内容の一致（NETWALKER-ORDER-OK）",
      detail: bizAfter?.result?.pass ? "受注一覧マーカーを3回とも確認" : "",
      ok: !!bizAfter?.result?.pass,
    },
    {
      name: "禁止通信の遮断維持（telnet 23）",
      detail: forbAfter?.result?.pass ? "TCP 23 → 遮断（POLICY-DENY-TELNET 維持）" : verifying ? "実行中…" : "",
      ok: !!forbAfter?.result?.pass,
    },
  ];
  return (
    <>
      <section className="card fadein">
        <div className="card-head">
          <h2>案件完了時の復旧確認試験</h2>
          <span className="card-note">利用者と同じ経路 · client → 受注サービス</span>
        </div>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 0", borderBottom: "1px solid var(--border-divider)" }}>
            <span style={{
              width: 22, height: 22, borderRadius: "50%", flex: "none",
              background: r.ok ? "var(--green)" : verifying ? "var(--blue)" : "var(--gray)",
              color: "#fff", display: "grid", placeItems: "center", fontSize: 12,
            }}>{r.ok ? "✓" : verifying ? "…" : i + 1}</span>
            <span style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{r.name}</div>
              {r.detail && <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>{r.detail}</div>}
            </span>
            {r.ok && <span style={{ fontSize: 11, fontWeight: 600, color: "var(--green)" }}>合格</span>}
          </div>
        ))}
        {verifying && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "var(--blue)", fontWeight: 600, padding: "8px 2px 2px" }}>
            <span className="spinner" /> 検証中…
          </div>
        )}
      </section>

      {done && (
        <>
          <div className="fadein" style={{
            background: "var(--bg-green-tint)", border: "1px solid #bfe3cf", borderRadius: 12,
            padding: "16px 18px", display: "flex", gap: 12, alignItems: "flex-start",
          }}>
            <span style={{
              width: 28, height: 28, borderRadius: "50%", background: "var(--green)", color: "#fff",
              display: "grid", placeItems: "center", fontSize: 15, flex: "none",
            }}>✓</span>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "var(--green)" }}>
                {inc.residual_issues.length > 0 ? "業務復旧 · 主回線の対応は継続" : "業務復旧を確認"}
              </div>
              <div style={{ fontSize: 12.5, marginTop: 3, lineHeight: 1.55 }}>
                受注業務は{inc.residual_issues.length > 0 ? "予備経路で" : ""}再開しました。状態は{" "}
                <span style={{ fontFamily: "var(--mono)" }}>{inc.status}</span>。
                {inc.residual_issues.length > 0 && "完全解決ではありません。"}
              </div>
            </div>
          </div>

          {inc.residual_issues.length > 0 && (
            <section className="card fadein">
              <h2>残存課題・引き継ぎ</h2>
              {inc.residual_issues.map((r, i) => (
                <div key={i} style={{
                  display: "flex", gap: 12, alignItems: "flex-start", padding: "10px 12px",
                  background: "var(--bg-amber-tint)", border: "1px solid rgba(185,119,14,.12)", borderRadius: 10,
                }}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--amber)", fontWeight: 600, flex: "none" }}>
                    残存{String.fromCharCode(65 + i)}
                  </span>
                  <span style={{ fontSize: 12.5, lineHeight: 1.55 }}>
                    <b>{r.title}</b>。{r.detail}
                  </span>
                </div>
              ))}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", gap: 8 }}>
                <div className="subtile"><div className="lbl">引き継ぎ状態</div><div style={{ fontWeight: 600 }}>依頼準備済み</div></div>
                <div className="subtile"><div className="lbl">担当候補</div><div>{inc.residual_issues[0]?.assignee}</div></div>
                <div className="subtile"><div className="lbl">次の作業</div><div>{inc.residual_issues[0]?.action}</div></div>
                <div className="subtile"><div className="lbl">再入力</div><div>不要（同一案件を参照）</div></div>
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- 承認残り時間（1秒カウントダウン）

function RemainText({ ap }: { ap: Approval }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const remain = Math.max(0, Math.floor(ap.expires_epoch - Date.now() / 1000));
  return <>{Math.floor(remain / 60)}:{String(remain % 60).padStart(2, "0")}</>;
}

// ---------------------------------------------------------------- インサイトリボン（仮説・成果チップ列、横1行・累積）

function RChip({ fg, bg, bd, title, wide, children }: {
  fg: string; bg: string; bd?: string; title?: string; wide?: boolean; children: React.ReactNode;
}) {
  return (
    <span className="fadein" title={title} style={{
      display: "inline-flex", alignItems: "center", gap: 6, flex: "none",
      maxWidth: wide ? undefined : 380, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis",
      padding: "5px 12px", borderRadius: 999, fontSize: 11.5, fontWeight: 600,
      color: fg, background: bg, border: `1px solid ${bd ?? "transparent"}`,
    }}>{children}</span>
  );
}

export function InsightRibbon({ bundle, style }: { bundle: Bundle; style?: React.CSSProperties }) {
  const inc = bundle.incident;
  const ap = bundle.approvals[bundle.approvals.length - 1];
  const vlmEv = bundle.evidence.find((e) => e.tool === "vlm_read_topology");
  const restored = !!inc && ["SERVICE_RESTORED", "RESOLVED"].includes(inc.status);
  const supported = bundle.hypotheses.filter((h) => h.status === "supported");
  const lastHist = inc?.status_history[inc.status_history.length - 1];

  const chips: React.ReactNode[] = [];

  if (!inc || inc.status === "RECEIVED") {
    chips.push(
      <RChip key="demo" wide fg="var(--text-muted)" bg="var(--bg-subtle)" bd="var(--border-subtle)">
        デモ手順：右下の ⚙（または o キー）→ ① リセット → ② 複合障害を注入 → ③ 申告 → 構成図の業務パケットに注目
      </RChip>,
    );
    if (inc) {
      chips.push(<RChip key="rcv" fg="var(--blue)" bg="var(--bg-chip-blue)">申告受付済み · 調査を開始します</RChip>);
    }
  } else {
    if (vlmEv) {
      const r = vlmEv.result;
      const pending = (r.comparison?.unmatched_labels?.length ?? 0) + (r.comparison?.missing_registered?.length ?? 0);
      chips.push(
        <RChip key="vlm" fg="var(--blue)" bg="var(--bg-chip-blue)">
          {readSourceLabel(r.source)} · 機器{(r.mapped_nodes ?? []).length} · 接続{(r.mapped_links ?? []).length}
          {pending > 0 ? ` · 確認待ち${pending}` : ""}
        </RChip>,
      );
    }
    for (const h of bundle.hypotheses) {
      const idx = supported.indexOf(h);
      const prefix = h.status === "supported" ? `要因${String.fromCharCode(65 + idx)} ` : `H${h.seq} `;
      chips.push(
        <RChip key={h.id} title={`${h.text}（証拠 ${h.evidence_ids.join(", ") || "—"}）`}
          fg={AC[h.status]}
          bg={h.status === "supported" ? "var(--bg-red-tint)" : h.status === "open" ? "var(--bg-amber-tint)" : "var(--bg-subtle)"}>
          <b>{prefix}</b>{h.text}
          {h.evidence_ids.length > 0 && (
            <span style={{ fontFamily: "var(--mono)", fontWeight: 400, fontSize: 10.5 }}>
              {h.evidence_ids.join(",")}
            </span>
          )}
          <span style={{ fontWeight: 700 }}>{AS[h.status]}</span>
        </RChip>,
      );
    }
    if (ap?.decision === "pending") {
      chips.push(
        <RChip key="await" fg="var(--amber)" bg="var(--bg-amber-tint)" bd="rgba(185,119,14,.25)">
          <span className="spinner" style={{ width: 11, height: 11, borderTopColor: "var(--amber)" }} />
          承認待ち · 残り <span style={{ fontFamily: "var(--mono)" }}><RemainText ap={ap} /></span>
        </RChip>,
      );
    }
    if (restored) {
      chips.push(
        <RChip key="ok" fg="#fff" bg="var(--green)">
          ✓ 業務復旧を確認 · {inc!.status}{inc!.residual_issues.length > 0 ? "（予備経路で暫定復旧）" : ""}
        </RChip>,
      );
      inc!.residual_issues.forEach((r, i) => {
        chips.push(
          <RChip key={`res-${i}`} fg="var(--amber)" bg="var(--bg-amber-tint)" title={`${r.detail}（担当候補：${r.assignee}）`}>
            残存{String.fromCharCode(65 + i)}: {r.title} → {r.assignee}
          </RChip>,
        );
      });
    }
    if (inc!.status === "NEEDS_HUMAN") {
      chips.push(
        <RChip key="nh" fg="var(--amber)" bg="var(--bg-amber-tint)" bd="rgba(185,119,14,.3)" title={lastHist?.note}>
          担当者対応待ち（NEEDS_HUMAN）· {lastHist?.note ?? "証拠・仮説は案件に保存済み"}
        </RChip>,
      );
    }
  }

  return (
    <section className="card" style={{
      minWidth: 0, minHeight: 0, flexDirection: "row", alignItems: "center",
      gap: 10, padding: "10px 18px", overflow: "hidden", ...style,
    }}>
      <div style={{ flex: "none", fontSize: 10.5, fontWeight: 700, letterSpacing: ".08em", color: "var(--text-muted)" }}>
        仮説・成果
      </div>
      <div style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 8, overflowX: "auto", paddingBottom: 2 }}>
        {chips}
      </div>
    </section>
  );
}
