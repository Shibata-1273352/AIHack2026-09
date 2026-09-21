// コンソール上部のモデル選択（S8-5）。
//
// native の <select> を使う理由: アクセシブル名・キーボード操作・無効化が無料で付き、
// Playwright のリハーサルがボタン名で操作している箇所と衝突しない。
//
// 安全策（サーバ側でも検証している）:
// - 処理中は切り替え不可（走っている調査の方式を途中で変えない）
// - 選択肢は「構造化出力の実タスク検証に合格したモデル」だけ
// - 上書きはメモリのみ・永続化しない。A/B/R 比較は別プロセスなので混入しない
// - 録画再生モードでは「実際には呼ばれない」と正直に出す（選択モデルを詐称しない）
//
// 単価はサーバが返す値をそのまま表示する（フロントにハードコードしない・M-17）。

import { useEffect, useState } from "react";
import { post } from "../api";
import type { ModelsResponse } from "../types";

export function ModelSelect({ running, onChanged }: {
  running: boolean; onChanged?: () => void;
}) {
  const [data, setData] = useState<ModelsResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = () => {
    fetch("/api/models").then(r => r.json()).then(setData).catch(() => {});
  };
  useEffect(load, []);
  useEffect(() => { if (!running) load(); }, [running]);

  if (!data) return null;
  const locked = running || data.locked;
  const value = data.current ?? "";

  const change = async (next: string) => {
    setBusy(true); setError(""); setMsg("");
    try {
      const r = await post("/api/models/select", { model: next || null });
      setData(d => d ? { ...d, current: r.current } : d);
      setMsg(r.note || r.applies_to || "次の案件から適用されます");
      onChanged?.();
    } catch (e: any) {
      setError(e.message || "モデルを切り替えられませんでした");
      load();
    } finally { setBusy(false); }
  };

  const priceOf = (m: string) => {
    const o = data.options.find(x => x.model === m);
    if (!o?.pricing) return "単価非公開";
    return `入力 $${o.pricing.prompt_per_million}/M · 出力 $${o.pricing.completion_per_million}/M`;
  };

  return (
    <div className="model-select">
      <label>
        <span>AIモデル</span>
        <select value={value} disabled={locked || busy}
          onChange={(e) => void change(e.target.value)}>
          <option value="">設定どおり（{data.default}）</option>
          {data.options.map(o => (
            <option key={o.model} value={o.model}>
              {o.display}（{o.model}）
            </option>
          ))}
        </select>
      </label>
      <small className="model-select-note">
        {error ? <span className="err">{error}</span>
          : locked ? "調査・適用の処理中は切り替えできません"
          : data.replay ? "録画再生モードのため、選択したモデルは実際には呼ばれません"
          : msg ? msg
          : value ? priceOf(value)
          : "検証に合格したモデルだけを選べます"}
      </small>
    </div>
  );
}
