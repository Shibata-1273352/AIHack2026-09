// デモ通し実演の録画（ライブデモの予備・事前準備用）。
//
// ライブで sim や回線が不調でも発表を続けられるように、同じ画面・同じ順序の
// 録画を用意しておく。操作はすべて**実際のUI**から行い、実際のシミュレータと
// 実際のモデルを通す（作り物の再生ではない）。
//
// 使い方:
//   cd frontend
//   NW_BASE=http://localhost:8000 APPROVAL_TOKEN=<token> node scripts/record-demo.mjs
//
// 出力:
//   docs/media/netwalker-demo.webm  … Playwright の録画（無音）
//   docs/media/netwalker-demo.mp4   … ffmpeg があれば mp4 も作る（発表で扱いやすい）
//
// 台本は docs/demo-script.md の「4分版の時間配分」に合わせてある。
// 各場面で読む時間を取るため、意図的に待ちを入れている。

import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { existsSync, mkdirSync, renameSync, readdirSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = resolve(HERE, "../../docs/media");
const BASE = process.env.NW_BASE ?? "http://localhost:8000";
const TOKEN = process.env.APPROVAL_TOKEN ?? "";
const W = Number(process.env.NW_WIDTH ?? 1920);
const H = Number(process.env.NW_HEIGHT ?? 1080);

const ui = (path) => BASE + path + (TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : "");

const api = async (path, body) => {
  const r = await fetch(BASE + path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json", ...(TOKEN ? { "X-Netwalker-Token": TOKEN } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(`${path}: ${r.status} ${JSON.stringify(data)}`);
  return data;
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(label, pred, timeoutMs = 300000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (await pred()) { console.log(`  ✓ ${label} (${((Date.now() - t0) / 1000).toFixed(1)}s)`); return; }
    await sleep(1000);
  }
  throw new Error(`timeout: ${label}`);
}

const statusIs = (...sts) => async () => {
  const b = await api("/api/incidents/latest");
  return b.incident && sts.includes(b.incident.status);
};

mkdirSync(OUT_DIR, { recursive: true });

console.log("== 収録の準備: 環境をリセット ==");
await api("/api/demo/reset", {});
await waitFor("正常状態に戻った", async () => {
  const gt = await api("/api/demo/ground_truth");
  return gt.business && !gt.fault_a_active && !gt.fault_b_active;
}, 120000);

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: W, height: H },
  recordVideo: { dir: OUT_DIR, size: { width: W, height: H } },
});
const page = await context.newPage();

try {
  // ---- 0:00 課題（初期画面） ----
  console.log("== 0:00 初期画面 ==");
  await page.goto(ui("/console"), { waitUntil: "load" });
  await sleep(6000);   // 実測テレメトリの到着を待ちつつ、構成図を読む時間

  // ---- 0:25 障害を入れ、機器が自力で切り替わるのを見せる ----
  console.log("== 0:25 複合障害を再現（自力復旧タイムライン） ==");
  await page.getByRole("button", { name: /複合障害を再現/ }).click();
  await waitFor("業務が止まった", async () => !(await api("/api/demo/ground_truth")).business, 60000);
  await sleep(9000);   // 「機器が自分で切り替えました」を読む時間

  // ---- 0:45 申告 → 調査 ----
  console.log("== 0:45 申告して調査を開始 ==");
  await page.getByRole("button", { name: /申告/ }).click();
  await waitFor("調査中", statusIs("INVESTIGATING"));

  // 調査ログが積み上がる様子をそのまま見せる（ここが自律性の見どころ）
  await waitFor("承認待ち", statusIs("AWAITING_APPROVAL", "NEEDS_HUMAN", "RESOLVED"));
  await sleep(2000);

  const bundle = await api("/api/incidents/latest");
  if (bundle.incident.status !== "AWAITING_APPROVAL") {
    throw new Error(`承認待ちに到達しませんでした: ${bundle.incident.status} / ${bundle.incident.current_activity}`);
  }

  // ---- 2:15 複製環境での検証結果と承認カード ----
  console.log("== 2:15 承認カード（実差分と複製環境の実測） ==");
  await sleep(10000);  // 差分・変更前後の比較を読む時間

  // ---- 2:40 承認 ----
  console.log("== 2:40 人が承認 ==");
  await page.getByRole("button", { name: "承認して適用へ" }).click();
  await waitFor("適用・検証", statusIs("APPLYING", "VERIFYING", "SERVICE_RESTORED", "RESOLVED"));
  await sleep(3000);

  // ---- 3:05 復旧 ----
  console.log("== 3:05 業務復旧と残存課題 ==");
  await waitFor("業務復旧", statusIs("SERVICE_RESTORED", "RESOLVED"));
  await sleep(9000);   // 緑の復旧表示と残存課題を読む時間

  // ---- 3:30 技術詳細（防御層・AI呼出の明細・タイムライン） ----
  console.log("== 3:30 技術詳細 ==");
  await page.getByRole("button", { name: "技術詳細", exact: true }).click();
  await sleep(5000);
  const modal = page.locator(".detail-modal");
  await modal.evaluate((el) => el.scrollTo({ top: el.scrollHeight / 2, behavior: "smooth" }));
  await sleep(5000);
  await modal.evaluate((el) => el.scrollTo({ top: el.scrollHeight, behavior: "smooth" }));
  await sleep(6000);
  await page.getByRole("button", { name: "閉じる", exact: true }).click();
  await sleep(2500);
  console.log("== 収録完了 ==");
} finally {
  await context.close();   // ここで録画ファイルが書き出される
  await browser.close();
}

// ---- 出力を分かりやすい名前にし、可能なら mp4 へ ----
const webms = readdirSync(OUT_DIR).filter((f) => f.endsWith(".webm"));
if (webms.length === 0) throw new Error("録画ファイルが生成されませんでした");
const newest = webms
  .map((f) => ({ f, t: statSafe(resolve(OUT_DIR, f)) }))
  .sort((a, b) => b.t - a.t)[0].f;
const webm = resolve(OUT_DIR, "netwalker-demo.webm");
if (resolve(OUT_DIR, newest) !== webm) renameSync(resolve(OUT_DIR, newest), webm);
console.log(webm);

const mp4 = resolve(OUT_DIR, "netwalker-demo.mp4");
const ffmpeg = findFfmpeg();
if (ffmpeg) {
  const r = spawnSync(ffmpeg, ["-y", "-i", webm, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                               "-crf", "23", "-movflags", "+faststart", mp4],
                      { stdio: "inherit" });
  if (r.status === 0) console.log(mp4);
  else console.warn("mp4 への変換に失敗しました（webm はそのまま使えます）");
} else {
  console.warn("ffmpeg が見つかりません。webm をそのまま使ってください");
}

function statSafe(p) {
  try { return statSync(p).mtimeMs; } catch { return 0; }
}

function findFfmpeg() {
  const candidates = [
    process.env.FFMPEG,
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    resolve(process.env.HOME ?? "", "Library/Caches/ms-playwright/ffmpeg-1011/ffmpeg-mac"),
  ].filter(Boolean);
  return candidates.find((p) => existsSync(p)) ?? null;
}
