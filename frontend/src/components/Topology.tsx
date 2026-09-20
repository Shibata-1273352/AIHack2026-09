// 構成図（SVG）。モックアップの視覚言語（ui-spec §5）を実トポロジ
// （client/gw/r1/r2/srv = シミュレータの netns）に対応付ける。
// ノード・リンクの状態はサーバの実イベント（node_status/link_status）にのみ連動する（M-13）。

import type { Incident } from "../types";

const C = { blue: "#1f5fbf", green: "#1f8a5b", red: "#c73a2b", gray: "#c3c9d1", ink: "#1b2430", amber: "#b9770e" };

interface NodeDef { id: string; kind: string; label: string; sub: string; x: number; y: number }

const NODES: NodeDef[] = [
  { id: "client", kind: "PC", label: "業務端末", sub: "10.0.1.10", x: 120, y: 190 },
  { id: "gw", kind: "GW", label: "拠点GW", sub: "10.0.1.1", x: 270, y: 300 },
  { id: "r1", kind: "RT", label: "経路ノード r1", sub: "主回線", x: 481, y: 150 },
  { id: "r2", kind: "RT", label: "経路ノード r2", sub: "予備回線", x: 481, y: 385 },
  { id: "srv", kind: "SRV", label: "受注サービス", sub: "10.0.100.10", x: 760, y: 260 },
];

const LINKS: { id: string; a: string; b: string }[] = [
  { id: "client-gw", a: "client", b: "gw" },
  { id: "gw-r1", a: "gw", b: "r1" },
  { id: "gw-r2", a: "gw", b: "r2" },
  { id: "r1-srv", a: "r1", b: "srv" },
  { id: "r2-srv", a: "r2", b: "srv" },
];

const nodeById = Object.fromEntries(NODES.map((n) => [n.id, n]));

function bezier(a: NodeDef, b: NodeDef): string {
  const cx = (a.x + b.x) / 2;
  return `M ${a.x} ${a.y} C ${cx} ${a.y}, ${cx} ${b.y}, ${b.x} ${b.y}`;
}

// ノードアイコン（ui-spec §5.5 逐語）
function Icon({ kind, c }: { kind: string; c: string }) {
  const common = { stroke: c, fill: "none", strokeWidth: 1.9 } as const;
  switch (kind) {
    case "PC":
      return (
        <g {...common} strokeLinecap="round" strokeLinejoin="round">
          <rect x="-12" y="-10" width="24" height="15" rx="2.5" />
          <path d="M -6 11 H 6 M 0 5 V 11" />
        </g>
      );
    case "GW":
      return (
        <g {...common} strokeLinecap="round" strokeLinejoin="round">
          <rect x="-13" y="-8" width="26" height="16" rx="3" />
          <path d="M -7 0 H 7 M 3 -4 L 7 0 L 3 4 M -13 -8 L -8 -14 H 8 L 13 -8" />
        </g>
      );
    case "SRV":
      return (
        <g {...common} strokeLinejoin="round">
          <rect x="-11" y="-12" width="22" height="9" rx="2" />
          <rect x="-11" y="3" width="22" height="9" rx="2" />
          <circle cx="-6" cy="-7.5" r="1.3" fill={c} stroke="none" />
          <circle cx="-6" cy="7.5" r="1.3" fill={c} stroke="none" />
        </g>
      );
    default: // RT
      return (
        <g {...common} strokeLinecap="round" strokeLinejoin="round">
          <circle r="12.5" />
          <path d="M -8 -3 H 4 M 1 -6 L 4 -3 L 1 0 M 8 3 H -4 M -1 0 L -4 3 L -1 6" />
        </g>
      );
  }
}

// ノード状態スタイル（ui-spec §5.4）
function nodeStyle(status: string) {
  switch (status) {
    case "ok":
    case "fixed":
      return { fill: "#e6f4ec", stroke: C.green, sw: 1.5, icon: C.green, filter: "url(#nwsh)" };
    case "bad":
      return { fill: "#fbeeec", stroke: C.red, sw: 2, icon: C.red, filter: "url(#nwglowred)" };
    case "probing":
      return { fill: "#fff", stroke: C.blue, sw: 2.5, icon: C.blue, filter: "url(#nwglow)" };
    default:
      return { fill: "#fff", stroke: C.gray, sw: 1.5, icon: "#8a94a0", filter: "url(#nwsh)" };
  }
}

function linkStyle(status: string) {
  switch (status) {
    case "active": return { stroke: C.blue, width: 3.5, dash: undefined, packets: true, cross: false };
    case "ok":
    case "restored": return { stroke: C.green, width: 3.5, dash: undefined, packets: true, cross: false };
    case "down": return { stroke: C.red, width: 3.5, dash: "7 7", packets: false, cross: true };
    case "blocked": return { stroke: C.red, width: 3.5, dash: "7 7", packets: false, cross: false };
    default: return { stroke: C.gray, width: 2.5, dash: undefined, packets: false, cross: false };
  }
}

function badgeFor(status: string, label: string): { text: string; bg: string } | null {
  if (label.includes("残存")) return { text: "残存課題", bg: C.amber };
  if (status === "bad") {
    if (label.includes("ACL")) return { text: "ACL異常", bg: C.red };
    if (label.includes("リンク")) return { text: "リンク断", bg: C.red };
    return { text: "異常", bg: C.red };
  }
  if (status === "fixed") return { text: "修正済", bg: C.green };
  if (status === "ok" && label.includes("業務OK")) return { text: "業務OK", bg: C.green };
  return null;
}

function tagFor(status: string, label: string): { text: string; bg: string } | null {
  if (status === "blocked") return { text: "443遮断", bg: C.red };
  if (status === "down") return { text: "リンク断", bg: C.red };
  if (status === "restored") return { text: "443許可", bg: C.green };
  if (status === "active" && label.includes("予備")) return { text: "予備経路", bg: C.blue };
  return null;
}

function Badge({ text, bg, y = -46 }: { text: string; bg: string; y?: number }) {
  const bw = text.length * 10.5 + 16;
  return (
    <g transform={`translate(0,${y})`}>
      <rect x={-bw / 2} y="-10" width={bw} height="20" rx="10" fill={bg} filter="url(#nwsh)" />
      <text y="4" textAnchor="middle" fontSize="10" fontWeight="600" fill="#fff">{text}</text>
    </g>
  );
}

export function Topology({ incident, note }: { incident: Incident | null; note: string }) {
  const gs = incident?.graph_status ?? { nodes: {}, links: {} };
  const probedCount = Object.values(gs.nodes).filter((n) => n.status !== "unknown" && n.status !== "probing").length;
  const diffCount = Object.values(gs.links).filter((l) => l.status === "down").length
    + Object.values(gs.nodes).filter((n) => n.status === "bad" && n.label.includes("ACL")).length;

  return (
    <section className="card" style={{ order: 1 }}>
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <h2>構成図（構造化）</h2>
        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{note}</span>
        <span style={{ marginLeft: "auto", display: "flex", gap: 12, fontSize: 11, color: "var(--text-muted)" }}>
          {[["調査中", C.blue], ["確認済", C.green], ["異常", C.red], ["未確認", C.gray]].map(([t, c]) => (
            <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 9, height: 9, borderRadius: "50%", background: c as string }} />{t}
            </span>
          ))}
        </span>
      </div>

      <svg viewBox="0 0 900 490" style={{ width: "100%", height: "auto", display: "block", fontFamily: "'Noto Sans JP',sans-serif" }}>
        <defs>
          <pattern id="nwdots" width="22" height="22" patternUnits="userSpaceOnUse">
            <circle cx="1.2" cy="1.2" r="1.2" fill="#dde2e9" />
          </pattern>
          <filter id="nwsh" x="-40%" y="-40%" width="180%" height="180%">
            <feDropShadow dx="0" dy="4" stdDeviation="4" floodColor="#111827" floodOpacity=".16" />
          </filter>
          <filter id="nwglow" x="-60%" y="-60%" width="220%" height="220%">
            <feDropShadow dx="0" dy="0" stdDeviation="8" floodColor="#1f5fbf" floodOpacity=".55" />
          </filter>
          <filter id="nwglowred" x="-60%" y="-60%" width="220%" height="220%">
            <feDropShadow dx="0" dy="0" stdDeviation="7" floodColor="#c73a2b" floodOpacity=".45" />
          </filter>
          <linearGradient id="nwzone" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#ffffff" stopOpacity=".9" />
            <stop offset="1" stopColor="#f3f5f9" stopOpacity=".9" />
          </linearGradient>
        </defs>

        <rect width="900" height="490" rx="14" fill="url(#nwdots)" />

        {/* ゾーン */}
        <rect x="22" y="26" width="318" height="440" rx="18" fill="url(#nwzone)" stroke="#e1e6ee" />
        <text x="40" y="52" fontSize="11" fontWeight="700" letterSpacing="1.5" fill="#5d6773">拠点A</text>
        <text x="40" y="68" fontSize="10" fill="#8a94a0">東京・営業所 · 10.0.1.0/24</text>
        <rect x="362" y="26" width="238" height="440" rx="18" fill="none" stroke="#dbe1ea" strokeDasharray="5 6" />
        <text x="380" y="52" fontSize="11" fontWeight="700" letterSpacing="1.5" fill="#5d6773">WAN</text>
        <text x="380" y="68" fontSize="10" fill="#8a94a0">回線事業者 · 冗長構成</text>
        <rect x="622" y="26" width="256" height="440" rx="18" fill="url(#nwzone)" stroke="#e1e6ee" />
        <text x="640" y="52" fontSize="11" fontWeight="700" letterSpacing="1.5" fill="#5d6773">データセンター</text>
        <text x="640" y="68" fontSize="10" fill="#8a94a0">10.0.100.0/24</text>

        {/* 回線雲 */}
        {[{ ty: 150, label: "主回線 · 専用線 100M" }, { ty: 385, label: "予備回線 · インターネットVPN" }].map((cl) => (
          <g key={cl.ty} transform={`translate(481,${cl.ty})`}>
            <path d="M -78 26 C -112 26 -112 -22 -74 -24 C -70 -58 -10 -66 10 -36 C 34 -60 92 -42 82 -6 C 112 0 106 36 70 34 Z"
              fill="#eef3fb" stroke="#c9d7f0" strokeDasharray="4 4" />
            <text x="0" y="62" textAnchor="middle" fontSize="10" fill="#5d6773" fontWeight="600">{cl.label}</text>
          </g>
        ))}

        {/* リンク */}
        {LINKS.map((l) => {
          const a = nodeById[l.a], b = nodeById[l.b];
          const d = bezier(a, b);
          const st = gs.links[l.id]?.status ?? "plain";
          const lbl = gs.links[l.id]?.label ?? "";
          const s = linkStyle(st);
          const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
          const tag = tagFor(st, lbl);
          const ty = my - (s.cross && tag ? 26 : 16);
          return (
            <g key={l.id}>
              <path d={d} fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" opacity=".9" />
              <path d={d} fill="none" stroke={s.stroke} strokeWidth={s.width}
                strokeDasharray={s.dash} strokeLinecap="round" />
              {s.packets && (
                <>
                  <circle r="4.5" fill={s.stroke} stroke="#fff" strokeWidth="1.5">
                    <animateMotion dur="1.6s" repeatCount="indefinite" path={d} />
                  </circle>
                  <circle r="4.5" fill={s.stroke} stroke="#fff" strokeWidth="1.5">
                    <animateMotion dur="1.6s" begin="0.8s" repeatCount="indefinite" path={d} />
                  </circle>
                </>
              )}
              {s.cross && (
                <g transform={`translate(${mx},${my})`}>
                  <circle r="11" fill="#fff" stroke={C.red} strokeWidth="2" />
                  <path d="M -4.5 -4.5 L 4.5 4.5 M 4.5 -4.5 L -4.5 4.5" stroke={C.red} strokeWidth="2.2" strokeLinecap="round" />
                </g>
              )}
              {tag && (
                <g transform={`translate(${mx},${ty})`}>
                  <rect x="-32" y="-10" width="64" height="20" rx="10" fill={tag.bg} filter="url(#nwsh)" />
                  <text y="4" textAnchor="middle" fontSize="10" fontWeight="600" fill="#fff">{tag.text}</text>
                </g>
              )}
            </g>
          );
        })}

        {/* ノード */}
        {NODES.map((n) => {
          const st = gs.nodes[n.id]?.status ?? "unknown";
          const lbl = gs.nodes[n.id]?.label ?? "";
          const s = nodeStyle(st);
          const badge = badgeFor(st, lbl);
          return (
            <g key={n.id} transform={`translate(${n.x},${n.y})`}>
              {st === "probing" && (
                <circle className="pulse-circle" r="30" fill="none" stroke={C.blue} strokeWidth="2.5" />
              )}
              <circle r="30" fill={s.fill} stroke={s.stroke} strokeWidth={s.sw} filter={s.filter} />
              <Icon kind={n.kind} c={s.icon} />
              {(st === "ok" || st === "fixed") && (
                <g>
                  <circle cx="22" cy="-22" r="7.5" fill={C.green} stroke="#fff" strokeWidth="2" />
                  <path d="M 18.5 -22 L 21 -19.5 L 25.5 -25" stroke="#fff" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                </g>
              )}
              {st === "bad" && (
                <g>
                  <circle cx="22" cy="-22" r="7.5" fill={C.red} stroke="#fff" strokeWidth="2" />
                  <path d="M 22 -25 V -21 M 22 -18.5 V -18" stroke="#fff" strokeWidth="1.8" fill="none" strokeLinecap="round" />
                </g>
              )}
              <text y="48" textAnchor="middle" fontSize="11.5" fill={C.ink} fontWeight="600">{n.label}</text>
              <text y="62" textAnchor="middle" fontSize="9.5" fill="#8a94a0" fontFamily="'IBM Plex Mono',monospace">{n.sub}</text>
              {badge && <Badge {...badge} />}
            </g>
          );
        })}
      </svg>

      <div style={{ borderTop: "1px solid var(--border-divider)", paddingTop: 10, fontSize: 11.5, color: "var(--text-muted)", display: "flex", gap: 14, flexWrap: "wrap" }}>
        <span>ノード 5 · リンク 5</span>
        <span>実測確認 {probedCount} / 5</span>
        <span>図と実態の差：{diffCount > 0 ? `${diffCount}件` : "0"}</span>
      </div>
    </section>
  );
}
