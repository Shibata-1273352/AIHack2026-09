// デモ運転席（/ops、隠しパネル）。障害注入・リセット・申告開始をワンクリックで行う。
// ここが呼ぶのは /api/demo/*（シミュレータの admin API）。エージェントからは不可視。

import { useEffect, useState } from "react";
import { post, useConfig } from "./api";

export default function OpsPage() {
  const { cfg } = useConfig();
  const [gt, setGt] = useState<any>(null);
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState("");

  const addLog = (s: string) =>
    setLog((l) => [`${new Date().toTimeString().slice(0, 8)} ${s}`, ...l].slice(0, 30));

  const refreshGt = async () => {
    try {
      const r = await fetch("/api/demo/ground_truth");
      setGt(await r.json());
    } catch { setGt(null); }
  };
  useEffect(() => {
    refreshGt();
    const t = setInterval(refreshGt, 3000);
    return () => clearInterval(t);
  }, []);

  const run = async (label: string, fn: () => Promise<any>) => {
    setBusy(label);
    try { await fn(); addLog(`${label} → OK`); }
    catch (e: any) { addLog(`${label} → 失敗: ${e.message}`); }
    finally { setBusy(""); refreshGt(); }
  };

  const host = window.location.host;
  const btn: React.CSSProperties = { padding: "14px 18px", fontSize: 14 };

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "28px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <h1 style={{ fontSize: 18, margin: 0 }}>NetWalker デモ運転席</h1>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
          コンソール: <a href={`http://${host}/console`}>http://{host}/console</a>
          iPad承認: <a href={`http://${host}/approve`}>http://{host}/approve</a>（同一Wi-Fi）
        </div>
      </div>

      <section className="card">
        <h2>シナリオ操作（デモの順番どおり）</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 10 }}>
          <button className="btn-outline" style={btn} disabled={!!busy}
            onClick={() => run("① 環境リセット", () => post("/api/demo/reset"))}>
            ① 環境リセット（正常状態へ）
          </button>
          <button className="btn-primary" style={btn} disabled={!!busy}
            onClick={() => run("② 複合障害を注入(A+B)", () => post("/api/demo/inject", { fault: "both" }))}>
            ② 複合障害を注入（A: 主回線断 + B: ACL誤設定）
          </button>
          <button className="btn-green" style={btn} disabled={!!busy}
            onClick={() => run("③ 申告→調査開始", () => post("/api/incidents", {}))}>
            ③ 拠点から申告 → 調査開始
          </button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 10 }}>
          <button className="btn-outline" disabled={!!busy}
            onClick={() => run("障害Aのみ注入", () => post("/api/demo/inject", { fault: "a" }))}>
            障害Aのみ（T-02）
          </button>
          <button className="btn-outline" disabled={!!busy}
            onClick={() => run("障害Bのみ注入", () => post("/api/demo/inject", { fault: "b" }))}>
            障害Bのみ（T-03）
          </button>
        </div>
        {busy && <div style={{ fontSize: 12, color: "var(--blue)" }}><span className="spinner" /> {busy}…</div>}
      </section>

      <section className="card">
        <div className="card-head">
          <h2>正解情報（評価系のみ・エージェント不可視）</h2>
          <span className="card-note">3秒ごとに更新</span>
        </div>
        {gt ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 8 }}>
            <div className="subtile"><div className="lbl">障害A（主回線断）</div>
              <div style={{ fontWeight: 600, color: gt.fault_a_active ? "var(--red)" : "var(--green)" }}>
                {gt.fault_a_active ? "注入中" : "なし"}</div></div>
            <div className="subtile"><div className="lbl">障害B（ACL誤設定）</div>
              <div style={{ fontWeight: 600, color: gt.fault_b_active ? "var(--red)" : "var(--green)" }}>
                {gt.fault_b_active ? "注入中" : "なし"}</div></div>
            <div className="subtile"><div className="lbl">冗長化制御の使用経路</div>
              <div style={{ fontWeight: 600 }}>{gt.failover?.active_path ?? "—"}</div></div>
            <div className="subtile"><div className="lbl">業務通信（実測）</div>
              <div style={{ fontWeight: 600, color: gt.business ? "var(--green)" : "var(--red)" }}>
                {gt.business ? "正常" : "不通"}</div></div>
          </div>
        ) : (
          <div style={{ fontSize: 12.5, color: "var(--text-faint)" }}>シミュレータに接続できません</div>
        )}
      </section>

      <section className="card">
        <h2>実行設定</h2>
        {cfg && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 12, lineHeight: 1.8, color: "var(--text-muted)" }}>
            agent_mode: {cfg.agent_mode}<br />
            route_mode: {cfg.route_mode}<br />
            orcarouter_key: {cfg.has_api_key ? "設定済み" : "未設定（scripted で動作）"}<br />
            sim: {cfg.sim?.ok ? "OK" : "NG"}
          </div>
        )}
      </section>

      <section className="card">
        <h2>操作ログ</h2>
        <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, lineHeight: 1.8, color: "var(--text-muted)", maxHeight: 200, overflowY: "auto" }}>
          {log.length ? log.map((l, i) => <div key={i}>{l}</div>) : "（まだ操作していません）"}
        </div>
      </section>
    </div>
  );
}
