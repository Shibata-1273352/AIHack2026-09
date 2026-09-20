// コンソール内の運転操作ドロワー（プレゼン用の隠し操作盤）。
// キー `o` または右下の極小ギアで開閉。呼ぶのは /api/demo/*（エージェント不可視の admin 経路）。
// フル機能の /ops ページは別途そのまま残している。

import { useEffect, useState } from "react";
import { post } from "../api";

export function OpsDrawer() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [log, setLog] = useState<string[]>([]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "o" && !e.metaKey && !e.ctrlKey && !e.altKey) setOpen((v) => !v);
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    const at = new Date().toTimeString().slice(0, 8);
    try { await fn(); setLog((l) => [`${at} ${label} → OK`, ...l].slice(0, 8)); }
    catch (e: any) { setLog((l) => [`${at} ${label} → 失敗: ${e.message}`, ...l].slice(0, 8)); }
    finally { setBusy(""); }
  };

  const btn: React.CSSProperties = { padding: "12px 14px", fontSize: 13, textAlign: "left" };

  return (
    <>
      {/* 極小ギア（右下） */}
      <button aria-label="運転操作" onClick={() => setOpen((v) => !v)} style={{
        position: "fixed", right: 10, bottom: 10, zIndex: 40,
        width: 26, height: 26, borderRadius: "50%", border: "1px solid var(--border-inner)",
        background: "rgba(255,255,255,.75)", color: "var(--text-faint)",
        fontSize: 13, cursor: "pointer", opacity: 0.55, lineHeight: 1,
      }}>⚙</button>

      {open && (
        <>
          <div onClick={() => setOpen(false)}
            style={{ position: "fixed", inset: 0, zIndex: 41, background: "rgba(15,20,32,.25)" }} />
          <aside className="drawer-in" style={{
            position: "fixed", top: 0, right: 0, bottom: 0, zIndex: 42, width: 320,
            background: "#fff", borderLeft: "1px solid var(--border-card)",
            boxShadow: "-24px 0 48px -24px rgba(15,20,32,.4)",
            padding: "18px 16px", display: "flex", flexDirection: "column", gap: 10,
          }}>
            <div style={{ display: "flex", alignItems: "center" }}>
              <h2 style={{ fontSize: 13.5, margin: 0 }}>運転操作（デモ）</h2>
              <span style={{ marginLeft: "auto", fontSize: 10.5, color: "var(--text-faint)" }}>
                o で開閉 · Esc で閉じる
              </span>
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6 }}>
              /api/demo/*（エージェント不可視の admin 経路）を呼びます。/ops ページも利用できます。
            </div>
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
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn-outline" style={{ ...btn, flex: 1, padding: "9px 10px", fontSize: 12 }} disabled={!!busy}
                onClick={() => run("障害Aのみ注入", () => post("/api/demo/inject", { fault: "a" }))}>
                A単独（主回線断）
              </button>
              <button className="btn-outline" style={{ ...btn, flex: 1, padding: "9px 10px", fontSize: 12 }} disabled={!!busy}
                onClick={() => run("障害Bのみ注入", () => post("/api/demo/inject", { fault: "b" }))}>
                B単独（ACL誤設定）
              </button>
            </div>
            {busy && (
              <div style={{ fontSize: 12, color: "var(--blue)", display: "flex", alignItems: "center", gap: 8 }}>
                <span className="spinner" /> {busy}…
              </div>
            )}
            <div style={{
              marginTop: "auto", fontFamily: "var(--mono)", fontSize: 10.5,
              color: "var(--text-muted)", lineHeight: 1.7, minHeight: 60,
            }}>
              {log.length ? log.map((l, i) => <div key={i}>{l}</div>) : "（まだ操作していません）"}
            </div>
          </aside>
        </>
      )}
    </>
  );
}
