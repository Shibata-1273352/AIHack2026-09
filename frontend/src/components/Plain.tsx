// 画面に出す語の一元管理（表記揺れ防止）と、平易語＋技術名の二層表示部品。
//
// 規約: 生のID・hash・IPアドレス・ポート番号・enum・JSON は必ず
//   ① <Term> の技術側（<small>）  ② <details> の中  ③ 技術詳細モーダル
// のいずれかに置く。それ以外の場所（見出し・本文）には出さない。
//
// ツールチップは native の title 属性のみ。4分の発表で誰もホバーしないため、
// 独自ポップオーバーは作らない（保守コストに見合わない）。

import type { ReactNode } from "react";

/** 画面に出す語の辞書。技術名は消さず技術層へ移す。 */
export const PLAIN = {
  // モデル・推論
  vlm: "マルチモーダルAI",
  vlmRead: "AIが図を読み取る",
  llm: "AI",
  llmDecisions: "AIが考えた回数",
  // 構成理解の出所
  sourceRegistered: "図は未読取（登録情報を使用）",
  sourceGolden: "記録した読取結果を再生",
  sourceLive: "AIが構成図を読み取り",
  // ネットワーク用語
  acl: "通信ルール",
  aclBad: "通信ルールの誤り",
  blocked443: "業務通信ブロック",
  allowed443: "業務通信OK",
  linkDown: "回線が切れている",
  l3OkTcpNg: "相手までは届くが、業務の通信だけ止められている",
  probe: "経路を試験",
  observeNode: "機器の状態を確認",
  backupPath: "予備経路",
  verifier: "利用者と同じ通信で確認",
  idempotency: "二重適用の防止",
  span: "処理の記録",
  cloneMatch: "本番と同じ構成であることを確認",
  // 状態
  needsHuman: "担当者の判断が必要",
  serviceRestored: "業務が復旧しました",
  resolved: "解決済み",
  applying: "変更を適用中",
  verifying: "復旧を確認中",
  rollingBack: "適用前の状態へ復元中",
} as const;

/** 機器IDと日本語名の対応（構成図・調査ログ・承認カードで共通）。 */
export const NODE_LABELS: Record<string, string> = {
  client: "業務端末",
  gw: "拠点ルータ",
  r1: "主回線ルータ",
  r2: "予備回線ルータ",
  srv: "受注サーバ",
};

export const nodeLabel = (id: string): string => NODE_LABELS[id] ?? id;

/** 構成図の読取り出所（VLM の source 文字列）を平易な一文にする。 */
export function readSourceLabel(source: string | undefined): string {
  if (!source) return "登録構成をもとに調査";
  if (source.startsWith("registered_table")) return PLAIN.sourceRegistered;
  if (source.startsWith("golden")) return PLAIN.sourceGolden;
  return PLAIN.sourceLive;
}

/**
 * 平易語を主、技術名を従で並べる。
 * `tech` を省略すると平易語だけを描く（移行途中でも壊れない）。
 */
export function Term({ plain, tech, block }: {
  plain: ReactNode; tech?: string; block?: boolean;
}) {
  if (!tech) return <>{plain}</>;
  return (
    <span className={block ? "term term-block" : "term"} title={tech}>
      <b>{plain}</b>
      <small>{tech}</small>
    </span>
  );
}

/** 構成図（SVG）用の双子。x/y はテキストの基準点。 */
export function TermSvg({ x, y, plain, tech, fill = "#1b2430", size = 11.5, techSize = 9 }: {
  x: number; y: number; plain: string; tech?: string;
  fill?: string; size?: number; techSize?: number;
}) {
  return (
    <>
      <text x={x} y={y} textAnchor="middle" fontSize={size} fill={fill} fontWeight="600">
        {plain}
      </text>
      {tech && (
        <text x={x} y={y + 13} textAnchor="middle" fontSize={techSize} fill="#8a94a0"
          fontFamily="'IBM Plex Mono',monospace">{tech}</text>
      )}
    </>
  );
}
