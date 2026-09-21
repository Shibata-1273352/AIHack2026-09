// NetWalker 4Kダッシュボード検証:
//  run1 (1920×1080): 常設操作で 障害再現→申告→承認→復旧→リセット
//  run2 (3840×2160): API で運転し、/approve（iPad役ウィンドウ）から承認
//  各フェーズを撮影し、横方向のはみ出しと繰り返し実行を検証
import { chromium } from "playwright";

const BASE = process.env.NW_BASE ?? "http://localhost:8000";
const SHOTS = process.env.SHOTS_DIR ?? "./shots";
// 変更系API（承認・注入・リセット）の操作トークン。demo.sh が表示する値を
// APPROVAL_TOKEN で渡す。サーバ側が未設定（開発モード）なら空でよい。
const TOKEN = process.env.APPROVAL_TOKEN ?? "";
// 画面側は ?token= から取り込んで localStorage に保持する
const ui = (path) => BASE + path + (TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : "");

const api = async (path, body) => {
  const r = await fetch(BASE + path, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "content-type": "application/json",
      ...(TOKEN ? { "X-Netwalker-Token": TOKEN } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(`${path}: ${r.status} ${JSON.stringify(data)}`);
  return data;
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(label, pred, timeoutMs = 150000) {
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

async function shoot(page, name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png` });
  const scroll = await page.evaluate(() => {
    const d = document.scrollingElement;
    return { sh: d.scrollHeight, ch: d.clientHeight, sw: d.scrollWidth, cw: d.clientWidth };
  });
  const ok = scroll.sw <= scroll.cw;
  console.log(`  📸 ${name}  scroll: ${JSON.stringify(scroll)} ${ok ? "OK" : "!!! PAGE SCROLLS !!!"}`);
  if (!ok) throw new Error(`page scrolls at ${name}`);
}

async function resetEnv() {
  await api("/api/demo/reset", {});
  await waitFor("reset (business ok)", async () => {
    const gt = await api("/api/demo/ground_truth");
    return gt.business && !gt.fault_a_active && !gt.fault_b_active;
  }, 90000);
}

const browser = await chromium.launch();

// ---------------------------------------------------------------- run1: FHD + コンソール内承認
console.log("== run1: 1920×1080, visible controls, in-console approval ==");
await resetEnv();
{
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto(ui("/console"), { waitUntil: "load" });
  await sleep(4000); // SSE 接続 + sim_pulse 到着待ち（networkidle は SSE で永久に来ない）
  await shoot(page, "fhd-1-intake");

  // 常設のデモ操作から障害を再現する
  await page.getByRole("button", { name: /複合障害を再現/ }).click();
  await waitFor("faults injected", async () => {
    const gt = await api("/api/demo/ground_truth");
    return gt.fault_a_active && gt.fault_b_active;
  });
  await waitFor("business down (pulse)", async () => !(await api("/api/demo/ground_truth")).business, 30000);
  await sleep(5000); // 次の pulse 反映（2秒周期）
  await shoot(page, "fhd-3-fault-injected");

  // ③ 申告→調査開始
  await page.getByRole("button", { name: /申告/ }).click();
  await waitFor("investigating", statusIs("INVESTIGATING"));
  await sleep(6000); // 仮説・証拠の流入を待つ
  await shoot(page, "fhd-4-investigating");

  // 承認待ち → コンソールの承認カードで承認
  await waitFor("awaiting approval", statusIs("AWAITING_APPROVAL"));
  await sleep(1500);
  await shoot(page, "fhd-5-awaiting-approval");
  await page.getByRole("button", { name: "承認して適用へ" }).click();
  await waitFor("applying/verifying", statusIs("APPLYING", "VERIFYING", "SERVICE_RESTORED"));
  await sleep(800);
  await shoot(page, "fhd-6-applying");

  await waitFor("service restored", statusIs("SERVICE_RESTORED", "RESOLVED"));
  await sleep(5000); // 緑パケット + リボン成功チップ
  await shoot(page, "fhd-7-restored");
  await page.getByRole("button", { name: "↺ デモをリセット", exact: true }).click();
  await page.getByRole("button", { name: "リセットする", exact: true }).click();
  await waitFor("reset clears active case", async () => !(await api("/api/incidents/latest")).incident);
  await page.getByRole("button", { name: /複合障害を再現/ }).waitFor({state: "visible"});
  await shoot(page, "fhd-8-reset");
  await page.close();
}

// ---------------------------------------------------------------- run2: 4K + /approve（iPad役）承認
console.log("== run2: 3840×2160, /approve approval ==");
await resetEnv();
{
  const page = await browser.newPage({ viewport: { width: 3840, height: 2160 } });
  await page.goto(ui("/console"), { waitUntil: "load" });
  await sleep(4000);
  await shoot(page, "4k-1-intake");

  await api("/api/demo/inject", { fault: "both" });
  await waitFor("business down", async () => !(await api("/api/demo/ground_truth")).business, 30000);
  await sleep(5000);
  await shoot(page, "4k-2-fault-injected");

  await api("/api/incidents", {});
  await waitFor("investigating", statusIs("INVESTIGATING"));
  await sleep(6000);
  await shoot(page, "4k-3-investigating");

  await waitFor("awaiting approval", statusIs("AWAITING_APPROVAL"));
  await sleep(1500);
  await shoot(page, "4k-4-awaiting-approval");

  // iPad 役ウィンドウ（/approve はステージ非適用・レスポンシブのまま）
  const ipad = await browser.newPage({ viewport: { width: 820, height: 1180 } });
  await ipad.goto(ui("/approve"), { waitUntil: "load" });
  await sleep(2500);
  await ipad.screenshot({ path: `${SHOTS}/ipad-approve.png` });
  await ipad.getByRole("button", { name: "承認して適用へ" }).click();
  await sleep(1200);
  await ipad.screenshot({ path: `${SHOTS}/ipad-approved.png` });
  await ipad.close();

  await waitFor("service restored", statusIs("SERVICE_RESTORED", "RESOLVED"));
  await sleep(5000);
  await shoot(page, "4k-5-restored");
  await page.close();
}

await browser.close();
console.log("ALL OK");
