// 1920×1080 の論理ステージを画面にフィットさせるスケーラ。
// 4K では約2倍に拡大、ノートPCでは縮小され、開発中も本番と同一レイアウトを確認できる。
// zoom でなく transform を使う: レイアウト再計算がなく、1920×1080 で検証した配置が
// そのまま拡大される（SVG・テキストはベクタなので滲まない）。

import { ReactNode, useEffect, useState } from "react";

export const STAGE_W = 1920;
export const STAGE_H = 1080;

export function useFitScale(): { k: number; vw: number; vh: number } {
  const [size, setSize] = useState({ vw: window.innerWidth, vh: window.innerHeight });
  useEffect(() => {
    const onResize = () => setSize({ vw: window.innerWidth, vh: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return { k: Math.min(size.vw / STAGE_W, size.vh / STAGE_H), ...size };
}

export function Stage({ children }: { children: ReactNode }) {
  const { k, vw, vh } = useFitScale();
  // /approve・/ops はスクロール可能なままにするため、ステージ表示中だけ固定する
  useEffect(() => {
    document.documentElement.classList.add("stage-lock");
    document.body.classList.add("stage-lock");
    return () => {
      document.documentElement.classList.remove("stage-lock");
      document.body.classList.remove("stage-lock");
    };
  }, []);
  const left = Math.max(0, (vw - STAGE_W * k) / 2);
  const top = Math.max(0, (vh - STAGE_H * k) / 2);
  return (
    <div style={{ position: "fixed", inset: 0, overflow: "hidden", background: "var(--bg-page)" }}>
      <div style={{
        position: "absolute", left, top,
        width: STAGE_W, height: STAGE_H,
        transform: `scale(${k})`, transformOrigin: "top left",
      }}>
        {children}
      </div>
    </div>
  );
}
