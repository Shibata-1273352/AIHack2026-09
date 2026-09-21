// 「機器が自分で切り替えた」タイムライン。AIが動く前にネットワークが自力で
// 復旧していたことを、シミュレータの実履歴で示す（誠実さの証明であり、物語の起点）。
//
// 時刻の扱い: sim コンテナ内の時計（HH:MM:SS）をそのまま表示する。
// 案件側（サーバ時刻）とは別の時計なので、**異なる時計を引き算しない**。
// 秒数は sim 内の履歴どうしの差分のみ（同一時計なので安全）。

import type { SimFailover, SimFailoverEvent } from "../types";

/** "HH:MM:SS" → 秒。パースできなければ null。 */
function secondsOf(at: string): number | null {
  const m = /^(\d{2}):(\d{2}):(\d{2})$/.exec(at ?? "");
  if (!m) return null;
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
}

/** 同一時計（sim 内）どうしの差分のみを取る。日跨ぎは負になるので捨てる。 */
function gapSeconds(from: string, to: string): number | null {
  const a = secondsOf(from), b = secondsOf(to);
  if (a === null || b === null) return null;
  const d = b - a;
  return d >= 0 && d < 3600 ? d : null;
}

function lastOf(history: SimFailoverEvent[], event: string): SimFailoverEvent | undefined {
  for (let i = history.length - 1; i >= 0; i--) if (history[i].event === event) return history[i];
  return undefined;
}

/** 障害注入後〜申告前に出す自力復旧タイムライン。履歴が無ければ何も描かない。 */
export function FailoverTimeline({ failover }: { failover: SimFailover | null }) {
  const history = failover?.history ?? [];
  const detected = lastOf(history, "primary_link_down_detected");
  const switched = lastOf(history, "switch_to_backup");
  if (!switched) return null;

  const poll = failover?.threshold && failover?.poll_sec
    ? `${failover.poll_sec}秒ごとに監視・${failover.threshold}回連続で確定`
    : "連続確認して確定";
  const took = detected ? gapSeconds(detected.at, switched.at) : null;

  return (
    <div className="failover-timeline fadein">
      <b>機器が自分で切り替えました（AIではありません）</b>
      <ol>
        {detected && (
          <li><time>{detected.at}</time><span>主回線の切断を検知<small>{poll}</small></span></li>
        )}
        <li>
          <time>{switched.at}</time>
          <span>予備回線へ自動切替{took !== null ? ` — 約${took}秒で完了` : ""}
            <small>登録済みの冗長化制御による動作</small>
          </span>
        </li>
      </ol>
      <p>ここまでは装置の機能です。<b>それでも業務は止まったまま。ここからが NetWalker の仕事です。</b></p>
    </div>
  );
}

/**
 * 案件開始後も残す1行。質疑の「その切替は誰がやったの？」を先回りする。
 * 予備経路を使っていないときは何も描かない。
 */
export function FailoverNote({ failover, activePath }: {
  failover: SimFailover | null; activePath: "r1" | "r2";
}) {
  const switched = lastOf(failover?.history ?? [], "switch_to_backup");
  if (activePath !== "r2" || !switched) return null;
  return (
    <div className="service-foot">
      予備経路を使用中 · {switched.at} に機器が自動切替（AIの操作ではありません）
    </div>
  );
}
