// 調査の進行を「積み上がるログ」として見せる。
//
// 以前は最新の1件で上書きしていたため、AIが観測に応じて手順を変えていく過程が
// 画面に残らなかった。全ステップは既に bundle.steps に蓄積されているので、
// 描き方を変えるだけで「観測に応じて手順が変わる＝自律性」が目で読める。
//
// 高さは固定（max-height + 内部スクロール）。行が増えてもページ全体は伸びないので、
// 一画面レイアウトとリハーサル（横スクロール禁止チェック）を壊さない。

import { useEffect, useRef, useState } from "react";
import type { AgentStep, Evidence } from "../types";

const VISIBLE = 6;   // 既定で見せる直近の行数（それ以前は折り畳む）

/** 各ステップに、その後に届いた証拠の件数を割り当てる。 */
function evidenceCounts(steps: AgentStep[], evidence: Evidence[]): number[] {
  return steps.map((s, i) => {
    const next = steps[i + 1];
    return evidence.filter((e) => e.at >= s.at && (!next || e.at < next.at)).length;
  });
}

export function InvestigationLog({ steps, evidence, onOpenDetails }: {
  steps: AgentStep[];
  evidence: Evidence[];
  onOpenDetails?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const endRef = useRef<HTMLLIElement>(null);
  const hoverRef = useRef(false);

  // 新着で最新行へ自動スクロール（読んでいる間＝ホバー中は止める）
  useEffect(() => {
    if (!hoverRef.current) endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [steps.length]);

  if (steps.length === 0) {
    return <p>実測の証拠を確認しています。</p>;
  }

  const counts = evidenceCounts(steps, evidence);
  const hiddenCount = expanded ? 0 : Math.max(0, steps.length - VISIBLE);
  const shown = hiddenCount > 0 ? steps.slice(hiddenCount) : steps;

  return (
    <div className="investigation-log"
      onMouseEnter={() => { hoverRef.current = true; }}
      onMouseLeave={() => { hoverRef.current = false; }}>
      <ol>
        {hiddenCount > 0 && (
          <li className="log-more">
            <button type="button" className="log-more-btn" onClick={() => setExpanded(true)}>
              … 前の {hiddenCount} 件を表示
            </button>
          </li>
        )}
        {shown.map((s, i) => {
          const idx = hiddenCount + i;
          const latest = idx === steps.length - 1;
          const n = counts[idx];
          return (
            <li key={s.id} className={latest ? "log-row latest fadein" : "log-row done"}
              ref={latest ? endRef : undefined}
              title={s.tech_title ? `${s.tech_title}${s.tech_detail ? ` / ${s.tech_detail}` : ""}` : undefined}
              onClick={onOpenDetails}
              role={onOpenDetails ? "button" : undefined}
              tabIndex={onOpenDetails ? 0 : undefined}
              onKeyDown={onOpenDetails ? (e) => { if (e.key === "Enter") onOpenDetails(); } : undefined}>
              <span className="log-mark">{latest ? "▸" : "✓"}</span>
              <time>{s.at.slice(11, 19)}</time>
              <span className="log-body">
                <span className="log-title">{s.title}</span>
                {latest && s.detail && <span className="log-detail">{s.detail}</span>}
                {/* 判断ごとに違うモデルが選ばれる様子＝モデル選択の価値の直接的な証拠 */}
                {s.route?.text && <span className="log-route">{s.route.text}</span>}
              </span>
              {n > 0 && <small className="log-count">証拠 {n}件</small>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
