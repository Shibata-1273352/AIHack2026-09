# NetWalker デモUI 設計仕様書（ui-spec）

**Source of Truth**: `mockup/NetWalker-Prototype/NetWalker Demo v2.dc.html`（単一ファイルモックアップ、609行）
本書はこのモックアップの React 再実装のための唯一の正となる設計仕様である。値はすべてモックアップからの逐語的な転記であり、創作・改変はしていない。

> **support.js について**: `mockup/NetWalker-Prototype/support.js` は dc-runtime（`<x-dc>` テンプレート + `sc-if` / `sc-for` + `DCLogic` React コンポーネント）を動かすための**生成済みビューワハーネス**であり、アプリ固有のロジックは一切含まない。デモの挙動はすべて HTML 内の `<script type="text/x-dc" data-dc-script>` にある（本書 §8 参照）。

> ⚠ **現行実装との差分（2026-09-22）**: 決勝が4分発表であること、審査員に非エンジニアが
> 含まれることを踏まえ、**画面の文言を平易層と技術層の二層**に作り替えた。本書は
> モックアップからの逐語転記であり**色・寸法・レイアウトの正**であり続けるが、
> **文言は現行実装が正**である。主な差分は次のとおり。
>
> - 見出しの語を平易化（例:「構成図（構造化）」→「ネットワーク構成図」、
>   「経路ノード r1」→「主回線ルータ」＋小さく `r1`）。技術名は `<small>` と
>   技術詳細モーダルへ移した（`frontend/src/components/Plain.tsx`）
> - 「調査の進行」カードを**最新1件の上書きから積み上げ式のログ**へ変更
>   （`InvestigationLog.tsx`）
> - 障害注入直後の**自力復旧タイムライン**、承認カード内の**複製環境の変更前後比較**、
>   **却下後の3つの出口**、コンソール上部の**モデル選択**を追加
> - 構成図の既知バグを修正: r1/r2 のノード副題と雲キャプションが同一座標（`y=62`）で
>   重なっていた問題、タグ幅が固定 `64` で日本語が見切れる問題、
>   浮遊チップの幅式がラテン等幅前提だった問題
>
> 経緯と意図は [../demo-script.md](../demo-script.md)（4分版）と
> [提出記事](../../articles/netwalker-aihack2026.md) を参照。

---

## 目次

1. [カラートークン](#1-カラートークン)
2. [タイポグラフィ](#2-タイポグラフィ)
3. [レイアウト構造](#3-レイアウト構造)
4. [コンポーネントレシピ](#4-コンポーネントレシピ)
5. [SVG構成図の完全仕様](#5-svg構成図の完全仕様)
6. [画面ステップ構成（全コピー逐語）](#6-画面ステップ構成)
7. [iPad承認パネル](#7-ipad承認パネル)
8. [JSの挙動（状態機械）](#8-jsの挙動)
9. [アニメーション一覧](#9-アニメーション一覧)

---

## 1. カラートークン

JS 内の定数（原文）:

```js
const C = { blue: '#1f5fbf', green: '#1f8a5b', red: '#c73a2b', gray: '#c3c9d1', amber: '#b9770e', ink: '#1b2430' };
```

### 1.1 プリミティブ / セマンティックカラー

| トークン案 | 値 | 用途（モックアップでの使用箇所） |
|---|---|---|
| `color-ink` | `#1b2430` | 基本テキスト色（body color）、暗色ボタン背景（「引き継ぎ文書を生成」）、SVGノード名ラベル |
| `color-blue` (C.blue) | `#1f5fbf` | プライマリ。リンク色、調査中ノード/リンク、パケットドット、ツールチップ背景文字、ボタングラデ終端、スピナー、凡例「調査中」 |
| `color-blue-hover` | `#164a96` | `a:hover` |
| `color-blue-light` | `#5b93f5` | ロゴのグラデーション始端 |
| `color-blue-btn-top` | `#3b74d9` | 青ボタングラデーション始端 `linear-gradient(180deg,#3b74d9,#1f5fbf)` |
| `color-green` (C.green) | `#1f8a5b` | 成功/確認済。凡例「確認済」、OKノード、チェックマーク円、承認済み、合格 |
| `color-green-btn-top` | `#2aa06c` | 緑ボタングラデーション始端 `linear-gradient(180deg,#2aa06c,#1f8a5b)` |
| `color-red` (C.red) | `#c73a2b` | 異常。凡例「異常」、故障ノード/リンク断、要因A/B ラベル、却下ボタン文字 |
| `color-amber` (C.amber) | `#b9770e` | 注意/確認待ち/保留/残存課題 |
| `color-gray` (C.gray) | `#c3c9d1` | 未確認ノードの枠、plain リンク、未実施ステップ番号円 |

### 1.2 背景・サーフェス

| トークン案 | 値 | 用途 |
|---|---|---|
| `bg-page` | `#f5f6f8` | body 背景 |
| `bg-card` | `#fff` | 白カード、フォーム入力風ボックス |
| `bg-subtle` | `#f6f7f9` | カード内サブタイル（統計・影響・引き継ぎ状態など）、Step1 注記ボックス |
| `bg-faint` | `#f8f9fb` | ドロップゾーン背景、VLM読取行の通常背景 |
| `bg-hover-blue` | `#eef3fb` | ドロップゾーン hover、「次の調査」ボックス背景、SVG雲の塗り |
| `bg-chip-blue` | `#eef3fc` | ツール名チップ背景（`probe_path` など）、アップロードアイコングラデ始端 |
| `bg-upload-icon-btm` | `#dfe9fa` | アップロードアイコングラデ終端 `linear-gradient(180deg,#eef3fc,#dfe9fa)` |
| `bg-green-tint` | `#e6f4ec` | 成功バナー、承認済み表示、OKノード塗り、「暫定復旧」チップ |
| `border-green-tint` | `#bfe3cf` | 成功バナー枠 |
| `bg-red-tint` | `#fbeeec` | 要因A/B ボックス、却下表示、故障ノード塗り、「不通」チップ |
| `border-red-tint` | `rgba(199,58,43,.12)` | 要因ボックス枠 |
| `bg-amber-tint` | `#fdf3e7` | 確認待ち統計タイル、保留表示、残存課題ボックス、VLM低信頼行 |
| `border-amber-tint` | `rgba(185,119,14,.12)` | 同上の枠 |
| `bg-neutral-chip` | `#f4f6f9` | 業務状態チップ「申告中」の背景 |
| `bg-dark` | `#0f1420` | サイドバー、Scene Graph JSONパネル、変更計画diffブロック、iPadベゼル |
| `bg-btn-disabled` | `#b8c0ca` | 「調査を開始」無効時の背景 |

### 1.3 テキスト（明色面）

| トークン案 | 値 | 用途 |
|---|---|---|
| `text-main` | `#1b2430` | 本文 |
| `text-muted` | `#5d6773` | ラベル、注記、凡例、SVGゾーン見出し |
| `text-faint` | `#8a94a0` | さらに薄い注記（「→ 未引き継ぎ」、EV時刻、ノードID、プレースホルダ、未実施行） |

### 1.4 テキスト・面（暗色面 = サイドバー / ダークパネル）

| トークン案 | 値 | 用途 |
|---|---|---|
| `dark-text` | `#e6e9ee` | サイドバー基本文字 |
| `dark-text-soft` | `#cfd5dd` | 案件説明、SMコード、diffブロック本文 |
| `dark-text-muted` | `#9aa4b1` | サイドバーのラベル/未到達工程、SVG凡例補足 |
| `dark-text-faint` | `#7f8a97` | サイドバー脚注、JSONパネル右上注記 |
| `dark-json-text` | `#cfe3ff` | Scene Graph JSON 文字色 |
| `dark-diff-del` | `#ff8a7a` | diff 削除行（`- 30 deny …`） |
| `dark-diff-add` | `#7fe0a5` | diff 追加行（`+ 30 permit …`） |
| `dark-diff-ctx` | `#8a94a0` | diff コンテキスト行 |
| `dark-surface` | `rgba(255,255,255,.05)` | サイドバー案件カード背景 |
| `dark-border` | `rgba(255,255,255,.07)` | 同カード枠 |
| `dark-divider` | `rgba(255,255,255,.06)` | サイドバー右境界、JSONパネル inset ring |
| `dark-active` | `rgba(255,255,255,.1)` | 現在工程ボタン背景、未実施ステップ番号円、iPadベゼル inset ring |
| `dark-hover` | `rgba(255,255,255,.07)` | 工程ボタン hover |

### 1.5 ボーダー・区切り（明色面）

| トークン案 | 値 | 用途 |
|---|---|---|
| `border-card` | `rgba(17,24,39,.06)` | 白カード枠、ヘッダ下線、iPad内カード枠 |
| `border-subtle` | `rgba(17,24,39,.05)` | サブタイル枠 |
| `border-input` | `#d6dbe1` | フォーム風ボックス枠、保留/却下ボタン枠 |
| `border-inner` | `#e3e6ea` | 仮説カード枠、プレビュー枠、技術詳細ストリップ枠 |
| `border-divider` | `#eef0f3` | 行区切り（証拠・事前検証・適用・検証の各行、SVGフッター上線） |
| `border-dashed-drop` | `#c5ccd6` | ドロップゾーン破線（1.5px dashed） |
| `spinner-track` | `#cfe0f7` | スピナーのトラック色 |

### 1.6 SVG 専用色

| トークン案 | 値 | 用途 |
|---|---|---|
| `svg-dots` | `#dde2e9` | 背景ドットパターン |
| `svg-zone-stroke` | `#e1e6ee` | 拠点A / DC ゾーン枠 |
| `svg-wan-stroke` | `#dbe1ea` | WAN ゾーン破線枠 |
| `svg-zone-grad-btm` | `#f3f5f9` | ゾーングラデ終端（`#ffffff` op .9 → `#f3f5f9` op .9） |
| `svg-cloud-fill` | `#eef3fb` | 回線雲の塗り |
| `svg-cloud-stroke` | `#c9d7f0` | 回線雲の破線枠 |
| `svg-shadow-flood` | `#111827` | ドロップシャドウ flood-color（opacity .16） |

### 1.7 グラデーション一覧（原文）

| 名称 | 定義 | 用途 |
|---|---|---|
| ロゴ | `linear-gradient(135deg,#5b93f5,#1f5fbf)` | サイドバー「N」ロゴ |
| 青ボタン | `linear-gradient(180deg,#3b74d9,#1f5fbf)` | 主要CTA |
| 緑ボタン | `linear-gradient(180deg,#2aa06c,#1f8a5b)` | 「承認して適用へ」「復旧確認試験へ」 |
| アップロードアイコン | `linear-gradient(180deg,#eef3fc,#dfe9fa)` | ドロップゾーンのアイコン台座 |
| iPad画面 | `linear-gradient(180deg,#fbfbfd,#f2f4f7)` | iPadスクリーン背景 |
| SVGゾーン | `linearGradient id="nwzone"`：`#ffffff` (stop-opacity .9) → `#f3f5f9` (stop-opacity .9)、x1=0 y1=0 x2=0 y2=1 | 拠点A / DC ゾーン |
| プレビュー方眼 | `repeating-linear-gradient(0deg,#f1f3f5 0 1px,transparent 1px 20px),repeating-linear-gradient(90deg,#f1f3f5 0 1px,transparent 1px 20px),#fff` + `filter:grayscale(1)` | アップロード後プレビュー枠 |

---

## 2. タイポグラフィ

### 2.1 フォント読み込み（原文）

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
```

- 本文: `font-family:"Noto Sans JP",system-ui,sans-serif`
- 等幅: `font-family:'IBM Plex Mono',monospace`
- body に `font-feature-settings:"tnum"`（等幅数字）と `-webkit-font-smoothing:antialiased`

### 2.2 テキストロール一覧

| ロール | サイズ | ウェイト | その他 | 使用箇所 |
|---|---|---|---|---|
| ブランド名 | 15px | 700 | `letter-spacing:.02em` | サイドバー「NetWalker」 |
| ブランド副題 | 10.5px | 400 | color `#9aa4b1` | 「障害調査エージェント」 |
| サイドバー節ラベル | 10.5px | 400 | `letter-spacing:.06em`、color `#9aa4b1` | 「工程」「案件」 |
| 工程ボタン | 13px | 400 | — | 工程名 |
| 工程番号 | 11px | 600 | 20px円内 | 番号 / ✓ |
| 工程ステータス | 10px | 400 | color `#9aa4b1` | 「完了」「進行中」 |
| 案件ID | 13px | 400 | IBM Plex Mono | `INC-2026-0042` |
| SMコード | 11px | 400 | IBM Plex Mono、color `#cfd5dd` | `RECEIVED` 等 |
| ヘッダラベル | 11px | 400 | color `#5d6773` | 「現在の処理」「業務状態」「経過時間」「担当」 |
| ヘッドライン | 15px | 700 | — | 現在の処理の本文 |
| 業務状態チップ | 12px | 600 | pill | 「不通 · 受注業務」等 |
| 経過時間 | 15px | 400 | IBM Plex Mono | `00:22` 等 |
| 担当 | 13px | 400 | 補足は `#8a94a0` | 「情シス・佐藤 → 未引き継ぎ」 |
| カード見出し h2 | 13.5px | 700 | `letter-spacing:.01em`、`margin:0` | 全カード見出し |
| カード右上注記 | 11px（一部11.5px） | 400 | color `#5d6773`（monoの場合あり） | 「PNG / JPEG 1枚」等 |
| フォームラベル | 12px | 400 | color `#5d6773` | 「拠点」「対象業務」「症状」 |
| フォーム値 | 13.5px | 400 | color `#1b2430`、`line-height:1.6`（症状） | 入力値表示 |
| CTAボタン | 14px | 600（承認は700） | color `#fff` | 主要ボタン |
| セカンダリボタン | 13px | 600 | — | 「保留」「却下」「デモを最初から」等 |
| 統計タイルラベル | 10.5px | 400 | color `#5d6773` | 「抽出ノード」等 |
| 統計タイル値 | 20px | 700 | — | 「9」等 |
| VLM読取行 | 12.5px | 400 | ID部は mono 11.5px 幅74px、confidence 11px/600 | 読取結果 |
| JSONテキスト | 11px | 400 | mono、`line-height:1.55`、color `#cfe3ff`、`white-space:pre`、`max-height:260px; overflow:auto` | Scene Graph |
| 仮説タイトル | 13px | 600 | ID mono 11px `#5d6773`、状態 11px/600 | H1/H2 |
| 仮説ノート | 12px | 400 | color `#5d6773`、`line-height:1.5` | — |
| 証拠行（全体） | 12px | 400 | 時刻 mono 11px `#8a94a0`（幅52px）、対象 600、判定 11px/600 | 証拠（実測） |
| 証拠出力 | 11px | 400 | mono、color `#5d6773`、`white-space:pre-wrap`、`line-height:1.5` | probe 出力 |
| ツールチップ | 11px | 400 | mono、bg `#eef3fc` color `#1f5fbf`、`padding:1px 7px; border-radius:5px` | `probe_path` 等 |
| 次の調査ボックス | 12px | 400（接頭辞600） | `line-height:1.5` | — |
| diffブロック | 11.5px | 400 | mono、`line-height:1.6`、`white-space:pre` | 変更計画 |
| 影響タイル | 12px 本文 / 10.5px ラベル | 400 | — | 影響・復元・鮮度 |
| 事前検証行 | 12.5px | 400 | 値 mono 11px | — |
| 適用/検証行タイトル | 13px | 600 | 詳細 mono 11.5px `#5d6773`、時刻 mono 11px `#8a94a0` | Step5/6 |
| 成功バナー見出し | 14px | 700 | color `#1f8a5b` | 「業務復旧 · 主回線の対応は継続」 |
| 成功バナー本文 | 12.5px | 400 | `line-height:1.55` | — |
| 技術詳細ストリップ | 11px | 400 | mono、color `#5d6773` | trace/calls等 |
| サイドバー脚注 | 10.5px | 400 | color `#7f8a97`、`line-height:1.6` | 「デモ用プロトタイプ…」 |
| SVG ゾーン見出し | 11px | 700 | `letter-spacing:1.5`、fill `#5d6773` | 「拠点A」「WAN」「データセンター」 |
| SVG ゾーン副題 | 10px | 400 | fill `#8a94a0` | 「東京・営業所 · 10.10.1.0/24」等 |
| SVG 雲ラベル | 10px | 600 | fill `#5d6773`、`text-anchor:middle` | 「主回線 · 専用線 100M」等 |
| SVG ノード名 | 11.5px | 600 | fill `#1b2430`、y=48 | 「業務端末」等 |
| SVG ノードID | 9.5px | 400 | mono、fill `#8a94a0`、y=62 | `PC-01` 等 |
| SVG バッジ/タグ | 10px | 600 | fill `#fff`、y=4 | 「異常」「443遮断」等 |
| SVG フッター統計 | 11.5px | 400 | color `#5d6773` | 「ノード 9 · リンク 9」等 |

---

## 3. レイアウト構造

### 3.1 ページ全体

```css
/* ルートグリッド */
display: grid;
grid-template-columns: 244px minmax(0,1fr);
min-height: 100vh;
```

- 左: サイドバー（244px 固定）
- 右: `<main>` `display:flex; flex-direction:column; min-width:0`

### 3.2 サイドバー

```css
background: #0f1420;
color: #e6e9ee;
padding: 24px 14px;
border-right: 1px solid rgba(255,255,255,.06);
display: flex; flex-direction: column; gap: 20px;
```

構成（上から）:
1. **ロゴ行**: `display:flex; align-items:center; gap:10px; padding:0 6px`
   - ロゴ: `width:30px; height:30px; border-radius:9px; background:linear-gradient(135deg,#5b93f5,#1f5fbf); box-shadow:0 4px 12px -4px rgba(59,116,217,.7); display:grid; place-items:center; font-weight:700; font-size:14px; color:#fff` — 文字「N」
   - 「NetWalker」15px/700、副題「障害調査エージェント」10.5px `#9aa4b1`
2. **案件カード**: `background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.07); border-radius:12px; padding:12px 12px`
   - ラベル「案件」10.5px → `INC-2026-0042`（mono 13px, margin-top 2px）→「拠点A／受注画面が開かない」12px `#cfd5dd`（margin-top 6px）
   - SM行（margin-top 8px, 11px）: ドット `width:7px;height:7px;border-radius:50%;background:{sm.dot}` + SMコード（mono, `#cfd5dd`）
3. **工程リスト**: `display:flex; flex-direction:column; gap:2px`、ラベル「工程」`padding:0 10px 6px`
4. **脚注**（`margin-top:auto`）: 「デモ用プロトタイプ。データはダミーです。」10.5px `#7f8a97` `padding:0 6px`

### 3.3 ヘッダ

```css
display: flex; align-items: center; gap: 20px;
padding: 14px 28px;
background: rgba(255,255,255,.82);
backdrop-filter: blur(14px);
border-bottom: 1px solid rgba(17,24,39,.06);
flex-wrap: wrap;
position: sticky; top: 0; z-index: 5;
```

- 左ブロック `flex:1; min-width:220px`: ラベル「現在の処理」+ ヘッドライン（15px/700, margin-top 2px）
- 右ブロック `display:flex; gap:24px; flex-wrap:wrap`:
  - 「業務状態」+ チップ（§4.3）
  - 「経過時間」+ mono 15px（margin-top 3px）
  - 「担当」+ 「情シス・佐藤 <span style="color:#8a94a0">→ 未引き継ぎ</span>」13px（margin-top 4px）

### 3.4 本文グリッド

```css
display: grid; gap: 16px;
padding: 20px 28px 32px;
grid-template-columns: {layout.cols};
align-items: start;
```

レイアウトプロップ（dcエディタ用 props、既定「図中央・右パネル」）:

| レイアウト名 | `cols` | `figOrder`（構成図セクションの order） |
|---|---|---|
| 図中央・右パネル（default） | `repeat(auto-fit,minmax(min(100%,500px),1fr))` | 1 |
| 図ワイド・下パネル | `minmax(0,1fr)` | 1 |
| パネル左・図右 | `repeat(auto-fit,minmax(min(100%,500px),1fr))` | 3 |

右（or 下）パネル側セクションは常に `order:2`。技術詳細ストリップは `order:9; grid-column:1/-1`。

もう一つの props: `showTechDetails`（boolean、default `false`）。

### 3.5 カード（共通シェル）

```css
background: #fff;
border: 1px solid rgba(17,24,39,.06);
border-radius: 16px;
box-shadow: 0 1px 2px rgba(17,24,39,.04), 0 12px 28px -16px rgba(17,24,39,.14);
padding: 18px 20px;            /* Step1 の2枚のみ 20px */
display: flex; flex-direction: column; gap: 10〜14px;  /* カードにより 8/10/12/14px */
```

---

## 4. コンポーネントレシピ

### 4.1 工程ボタン（サイドバー・ステップインジケータ）

```css
/* ボタン本体 */
display:flex; align-items:center; gap:10px; text-align:left;
border:0; cursor:pointer;
background: {現在: rgba(255,255,255,.1) / その他: transparent};
color: {現在または完了: #fff / 未到達: #9aa4b1};
padding:9px 10px; border-radius:8px; font:inherit; font-size:13px;
/* hover: background:rgba(255,255,255,.07) */

/* 番号円 */
width:20px; height:20px; border-radius:50%;
display:grid; place-items:center; font-size:11px; font-weight:600; flex:none;
background: {完了: #1f8a5b / 現在: #1f5fbf / 未到達: rgba(255,255,255,.1)};
color: {完了・現在: #fff / 未到達: #9aa4b1};
```

- 番号テキスト: 完了 = `✓`、それ以外 = ステップ番号
- 右端ステータス: 完了 = 「完了」、現在 = 「進行中」、未到達 = 空（10px `#9aa4b1`）
- 工程名（原文順）: `受付・構成図` / `構成理解（Scene Graph）` / `自律調査` / `原因提示・承認` / `自動復旧` / `復旧確認・引き継ぎ`

### 4.2 プライマリボタン

```css
/* 青CTA */
border:0; border-radius:12px; padding:13px 16px;
font:inherit; font-size:14px; font-weight:600; color:#fff;
background: linear-gradient(180deg,#3b74d9,#1f5fbf);
box-shadow: 0 1px 2px rgba(31,95,191,.25), 0 10px 20px -10px rgba(31,95,191,.7);
transition: transform .15s, box-shadow .15s; cursor:pointer;
/* hover: transform:translateY(-1px);
         box-shadow:0 2px 4px rgba(31,95,191,.25),0 14px 24px -10px rgba(31,95,191,.7) */
```

```css
/* 緑CTA（「復旧確認試験へ」）: 上と同形で */
background: linear-gradient(180deg,#2aa06c,#1f8a5b);
box-shadow: 0 1px 2px rgba(31,138,91,.25), 0 10px 20px -10px rgba(31,138,91,.7);
/* hover: transform:translateY(-1px) のみ */
```

```css
/* 「調査を開始」ボタン（Step1、グラデなし単色） */
border:0; border-radius:12px; padding:13px 16px; font-size:14px; font-weight:600; color:#fff;
background: {アップロード済: #1f5fbf / 未: #b8c0ca}; cursor:pointer; margin-top:auto;
/* disabled={notUploaded} */

/* 「業務テストを実行」（Step6）: 単色 #1f5fbf、margin-top:4px、他は同形 */
```

```css
/* ダークボタン（「引き継ぎ文書を生成」） */
border:0; border-radius:9px; padding:10px 16px; font-size:13px; font-weight:600;
color:#fff; background:#1b2430; cursor:pointer;

/* アウトラインボタン（「デモを最初から」） */
border:1px solid #d6dbe1; border-radius:9px; padding:10px 16px;
font-size:13px; font-weight:600; background:#fff; cursor:pointer;
```

### 4.3 チップ / バッジ

**業務状態チップ（ヘッダ）**:

```css
display:inline-flex; align-items:center; gap:6px; margin-top:3px;
padding:4px 11px; border-radius:999px; font-size:12px; font-weight:600;
box-shadow: inset 0 0 0 1px rgba(17,24,39,.06);
background:{biz.bg}; color:{biz.fg};
```

| 状態 | ラベル | bg | fg |
|---|---|---|---|
| Step1 未アップロード | `申告中` | `#f4f6f9` | `#5d6773` |
| 通常（障害中） | `不通 · 受注業務` | `#fbeeec` | `#c73a2b` (C.red) |
| 検証完了後 | `暫定復旧（予備経路）` | `#e6f4ec` | `#1f8a5b` (C.green) |

**SMドット（サイドバー）**: `width:7px; height:7px; border-radius:50%`。色は `SERVICE_RESTORED`→green、`NEEDS_HUMAN`→amber、それ以外→blue。

**ツール名チップ（証拠行）**: `font-family:'IBM Plex Mono'; font-size:11px; background:#eef3fc; color:#1f5fbf; padding:1px 7px; border-radius:5px`

**凡例ドット（構成図右上）**: `width:9px; height:9px; border-radius:50%` — 調査中 `#1f5fbf` / 確認済 `#1f8a5b` / 異常 `#c73a2b` / 未確認 `#c3c9d1`。各 `display:inline-flex; align-items:center; gap:5px`、11px `#5d6773`。

### 4.4 統計タイル（Step2）

```css
/* グリッド */ display:grid; grid-template-columns:repeat(3,1fr); gap:8px;
/* 通常タイル */ background:#f6f7f9; border:1px solid rgba(17,24,39,.05); border-radius:10px; padding:10px;
/* 注意タイル */ background:#fdf3e7; border:1px solid rgba(185,119,14,.12); /* ラベル・値とも #b9770e */
/* ラベル */ font-size:10.5px; color:#5d6773;  /* 値 */ font-size:20px; font-weight:700; margin-top:2px;
```

### 4.5 情報サブタイル（Step4影響 / Step6引き継ぎ）

```css
display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; font-size:12px;
/* Step6 は minmax(140px,1fr) */
/* タイル */ background:#f6f7f9; border:1px solid rgba(17,24,39,.05); border-radius:10px; padding:9px 11px;
/* ラベル */ color:#5d6773; font-size:10.5px;  /* 本文 */ margin-top:2px;
```

### 4.6 仮説カード（Step3）

```css
border:1px solid #e3e6ea; border-left:4px solid {h.accent}; border-radius:8px; padding:10px 12px;
/* 1行目 */ display:flex; align-items:center; gap:8px; font-size:13px; font-weight:600;
/*   ID */ mono 11px #5d6773;  /* 状態 */ margin-left:auto; font-size:11px; font-weight:600; color:{h.accent};
/* ノート */ font-size:12px; color:#5d6773; margin-top:4px; line-height:1.5;
```

### 4.7 証拠行（Step3）

```css
display:grid; grid-template-columns:52px minmax(0,1fr); gap:10px;
padding:8px 0; border-bottom:1px solid #eef0f3; font-size:12px;
/* 時刻 */ mono 11px #8a94a0
/* 見出し行 */ display:flex; gap:8px; align-items:center; flex-wrap:wrap
/*   ツールチップ（§4.3）+ 対象 font-weight:600 + 判定 margin-left:auto 11px/600 color:{e.color} */
/* 出力 */ mono 11px #5d6773; margin-top:3px; white-space:pre-wrap; line-height:1.5
/* 解釈 */ margin-top:3px; color:#1b2430; line-height:1.5
```

### 4.8 ダークパネル（Scene Graph JSON）

```css
background:#0f1420; border-radius:16px; padding:16px 18px;
box-shadow: inset 0 0 0 1px rgba(255,255,255,.06);
display:flex; flex-direction:column; gap:8px; min-width:0;
/* ヘッダ左 */ font-size:12px; color:#9aa4b1; font-weight:600  /* 「Scene Graph（JSON・未修正出力）」 */
/* ヘッダ右 */ font-size:10.5px; color:#7f8a97                 /* 「topology v3 · 図由来」 */
/* pre */ margin:0; mono 11px; line-height:1.55; color:#cfe3ff; white-space:pre; overflow:auto; max-height:260px;
```

### 4.9 diffブロック（Step4 変更計画）

```css
margin:0; background:#0f1420; border-radius:10px; padding:12px 14px;
font-family:'IBM Plex Mono',monospace; font-size:11.5px; line-height:1.6;
color:#cfd5dd; overflow:auto; white-space:pre;
```

行別カラー（内容は §6 Step4 を参照）: コンテキスト `#8a94a0` / 削除 `#ff8a7a` / 追加 `#7fe0a5`。

### 4.10 チェック行（事前検証 / 適用 / 検証）

```css
/* 事前検証（Step4） */
display:flex; align-items:center; gap:10px; font-size:12.5px; padding:6px 0; border-bottom:1px solid #eef0f3;
/* マーク円 */ width:18px; height:18px; border-radius:50%; background:{p.bg}; color:#fff;
              display:grid; place-items:center; font-size:11px; flex:none;
/* 値 */ mono 11px #5d6773

/* 適用ステップ（Step5） */
display:flex; align-items:flex-start; gap:12px; padding:9px 0; border-bottom:1px solid #eef0f3;
/* マーク円 */ 22px; font-size:12px; margin-top:1px; background:{完了:#1f8a5b / 実行中:#1f5fbf / 未:#c3c9d1};
/* マーク */ 完了 '✓' / 実行中 '…' / 未 連番
/* 名称 */ 13px/600 color:{完了・実行中:#1b2430 / 未:#8a94a0}
/* 詳細 */ mono 11.5px #5d6773 margin-top:2px  /* 時刻 */ mono 11px #8a94a0（右端）

/* 検証テスト（Step6） */
display:flex; align-items:center; gap:12px; padding:9px 0; border-bottom:1px solid #eef0f3;
/* マーク円 22px、マーク・背景は適用と同じ規則 */
/* 名称 13px/600（色は常に既定） */ /* 詳細: 完了→定義文 / 実行中→「実行中…」 / 未→空 */
/* 判定 */ 完了時のみ「合格」11px/600 #1f8a5b
```

### 4.11 スピナー / 進行表示

```jsx
// spinner（JSで生成、原文）
{ width:14, height:14, border:'2px solid #cfe0f7', borderTopColor:'#1f5fbf',
  borderRadius:'50%', display:'inline-block', animation:'nwspin .8s linear infinite' }
```

進行テキスト行: `display:flex; align-items:center; gap:10px; font-size:13px; color:#1f5fbf; font-weight:600; padding:4px 2px`（Step6 は `padding:8px 2px 2px`）。

### 4.12 成功バナー（Step6）

```css
background:#e6f4ec; border:1px solid #bfe3cf; border-radius:12px; padding:16px 18px;
display:flex; gap:12px; align-items:flex-start;
/* チェック円 */ width:28px; height:28px; border-radius:50%; background:#1f8a5b; color:#fff;
               display:grid; place-items:center; font-size:15px; flex:none;  /* 文字 '✓' */
/* 見出し */ 14px/700 #1f8a5b  /* 本文 */ 12.5px #1b2430 margin-top:3px line-height:1.55
```

### 4.13 要因/残存ボックス

```css
/* 要因（赤） */
display:flex; gap:10px; align-items:flex-start; padding:10px 12px;
background:#fbeeec; border:1px solid rgba(199,58,43,.12); border-radius:10px;
/* ラベル */ mono 11px #c73a2b 600 flex:none  /* 本文 */ 12.5px line-height:1.55（証拠参照は #5d6773）

/* 残存（琥珀） */ gap:12px; background:#fdf3e7; border:1px solid rgba(185,119,14,.12);
/* ラベル */ mono 11px #b9770e 600 flex:none
```

### 4.14 ドロップゾーン（Step1）

```css
border:1.5px dashed #c5ccd6; border-radius:14px; min-height:300px;
transition: background .15s, border-color .15s;
display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px;
cursor:pointer; background:#f8f9fb;
/* hover: background:#eef3fb; border-color:#1f5fbf */
```

アイコン台座: `width:52px; height:52px; border-radius:16px; background:linear-gradient(180deg,#eef3fc,#dfe9fa); box-shadow:0 8px 20px -10px rgba(31,95,191,.5); display:grid; place-items:center`
アップロードSVGアイコン（原文）:

```html
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#1f5fbf" stroke-width="1.8">
  <path d="M12 16V4M7 9l5-5 5 5"></path>
  <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"></path>
</svg>
```

### 4.15 フォーム風表示ボックス（Step1）

```css
/* label */ display:flex; flex-direction:column; gap:5px; font-size:12px; color:#5d6773;
/* 値ボックス */ border:1px solid #d6dbe1; border-radius:8px; padding:9px 12px;
               font-size:13.5px; color:#1b2430; background:#fff;
/* 症状のみ */ line-height:1.6; min-height:84px;
/* 注記ボックス */ background:#f6f7f9; border:1px solid rgba(17,24,39,.05); border-radius:10px;
                 padding:10px 12px; font-size:12px; color:#5d6773; line-height:1.6;
```

### 4.16 「次の調査」ボックス（Step3）

```css
font-size:12px; color:#5d6773; background:#eef3fb; border-radius:8px; padding:9px 12px; line-height:1.5;
/* 接頭辞 */ <span style="font-weight:600;color:#1f5fbf">次の調査：</span>
```

### 4.17 技術詳細ストリップ（showTechDetails=true 時）

```css
order:9; grid-column:1/-1; display:flex; gap:18px; flex-wrap:wrap;
font-size:11px; color:#5d6773; font-family:'IBM Plex Mono',monospace;
background:#fff; border:1px solid #e3e6ea; border-radius:10px; padding:10px 16px;
```

内容（原文）: `trace: {{traceId}}` / `local: DGX Spark · qwen2.5-vl-32b` / `router: OrcaRouter · 方式B（段階別）` / `calls {{calls}} · tokens {{tokens}} · ¥{{cost}}` / `data_class: local_only`
値: `traceId = '4b1e…0042'`、`calls` はステップ別 `{1:0, 2:3, 3:3+probeIdx*2, 4:17, 5:19, 6:21}`、`tokens = (calls*1840).toLocaleString()`、`cost = (calls*6.2).toFixed(0)`。

> **【未実装・W扱い】** `local: DGX Spark · qwen2.5-vl-32b` と `data_class: local_only` の
> 2項目は**モックアップ上の表示であり、実装では表示しない**。
> - DGX Spark ローカルLLM（M-16）は未接続。推論は OrcaRouter 経由または scripted のみ
>   （第15章の誠実性方針により、接続していないものを接続済みのように見せない）
> - 現行の実データは全て `data_class: external_allowed`。送信ゲート自体は実装済みで
>   （`backend/app/llm/gateway.py:28 SendPolicyViolation`）、`local_only` のデータが
>   発生した場合は外部送信前に遮断されるが、デモ経路では該当データが無いため表示もしない
>
> 実装の技術詳細ストリップは `trace` / `router` / `calls·tokens·cost` の3項目で構成する。
> ローカル推論を接続した場合に限り、上記2項目を表示に戻す。

---

## 5. SVG構成図の完全仕様

### 5.1 コンテナ

構成図カード（Step2以降 `showTopo = step>=2` で表示、`order:{figOrder}`、padding `18px 20px`）内:

```html
<svg viewBox="0 0 900 490" style="width:100%;height:auto;display:block;font-family:'Noto Sans JP',sans-serif">
```

カードヘッダ: h2「構成図（構造化）」+ 注記 `{{topoNote}}`（11.5px `#5d6773`）+ 右寄せ凡例（§4.3）。

`topoNote`（ステップ別・原文）:

| 条件 | 文言 |
|---|---|
| step===2 | `図由来。識別子は登録機器と照合中` |
| step===3 | `探索位置を青で表示。実測で確認した機器のみ確定` |
| step>=5 && applyIdx>=3 | `予備経路のACLを修正済み` |
| それ以外（step4、step5適用前） | `複合障害：主回線断 ＋ 予備経路ACL` |

SVG下のフッター統計（`border-top:1px solid #eef0f3; padding-top:10px`、11.5px、`·` 区切り）:
`ノード 9 · リンク 9` / `図由来 7 / 実測由来 2` / `図と実態の差：{{diffCount}}`
`diffCount = (step>=3 && probeIdx>=2) ? '1（GW-01 経路）' : '0'`

### 5.2 defs（原文）

```html
<pattern id="nwdots" width="22" height="22" patternUnits="userSpaceOnUse">
  <circle cx="1.2" cy="1.2" r="1.2" fill="#dde2e9"></circle>
</pattern>
<filter id="nwsh" x="-40%" y="-40%" width="180%" height="180%">
  <feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#111827" flood-opacity=".16"></feDropShadow>
</filter>
<filter id="nwglow" x="-60%" y="-60%" width="220%" height="220%">
  <feDropShadow dx="0" dy="0" stdDeviation="8" flood-color="#1f5fbf" flood-opacity=".55"></feDropShadow>
</filter>
<filter id="nwglowred" x="-60%" y="-60%" width="220%" height="220%">
  <feDropShadow dx="0" dy="0" stdDeviation="7" flood-color="#c73a2b" flood-opacity=".45"></feDropShadow>
</filter>
<linearGradient id="nwzone" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#ffffff" stop-opacity=".9"></stop>
  <stop offset="1" stop-color="#f3f5f9" stop-opacity=".9"></stop>
</linearGradient>
```

背景: `<rect width="900" height="490" rx="14" fill="url(#nwdots)">`

### 5.3 ゾーン（描画順: 背景→ゾーン→雲→リンク→ノード）

| ゾーン | rect | 見出し（11px/700 ls1.5 `#5d6773`） | 副題（10px `#8a94a0`） |
|---|---|---|---|
| 拠点A | `x=22 y=26 w=318 h=440 rx=18` fill `url(#nwzone)` stroke `#e1e6ee` | `拠点A` @ (40,52) | `東京・営業所 · 10.10.1.0/24` @ (40,68) |
| WAN | `x=362 y=26 w=238 h=440 rx=18` fill `none` stroke `#dbe1ea` `stroke-dasharray="5 6"` | `WAN` @ (380,52) | `回線事業者 · 冗長構成` @ (380,68) |
| データセンター | `x=622 y=26 w=256 h=440 rx=18` fill `url(#nwzone)` stroke `#e1e6ee` | `データセンター` @ (640,52) | `10.50.0.0/24` @ (640,68) |

**回線雲**（2つ、`transform=translate(481,150)` と `translate(481,385)`）:

```html
<path d="M -78 26 C -112 26 -112 -22 -74 -24 C -70 -58 -10 -66 10 -36 C 34 -60 92 -42 82 -6 C 112 0 106 36 70 34 Z"
      fill="#eef3fb" stroke="#c9d7f0" stroke-dasharray="4 4"></path>
<text x="0" y="62" text-anchor="middle" font-size="10" fill="#5d6773" font-weight="600">…</text>
```

ラベル: 上（RT-MAIN背面）`主回線 · 専用線 100M` / 下（RT-BKUP背面）`予備回線 · インターネットVPN`

### 5.4 ノード（9個）

座標テーブル（原文 `P`）とノード定義（原文 `base`）:

| id | 種別(kind) | 名称ラベル | x | y | ゾーン |
|---|---|---|---|---|---|
| PC-01 | PC | 業務端末 | 90 | 150 | 拠点A |
| AP-01 | AP | 無線AP | 90 | 370 | 拠点A |
| SW-01 | SW | 拠点スイッチ | 195 | 260 | 拠点A |
| GW-01 | GW | 拠点ゲートウェイ | 295 | 260 | 拠点A |
| RT-MAIN | RT | 主回線ルータ | 481 | 150 | WAN |
| RT-BKUP | RT | 予備回線ルータ | 481 | 385 | WAN |
| FW-01 | FW | DC ファイアウォール | 690 | 260 | DC |
| DNS-01 | DNS | 名前解決 | 818 | 150 | DC |
| APP-01 | SRV | 受注サービス | 818 | 385 | DC |

**ノードの描画構造**（`<g transform="translate(x,y)">` 内、順に）:
1. probing 時のみ: パルス円 `<circle r="30" fill="none" stroke="#1f5fbf" stroke-width="2.5" style="animation:nwpulse 1.4s ease-out infinite">`
2. 本体円: `<circle r="30" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" filter="{filter}">`
3. アイコン（§5.5）
4. 状態ドット（ok/fixed/bad のみ）: `<circle cx="22" cy="-22" r="7.5" fill="{dot}" stroke="#fff" stroke-width="2">` + マークパス
   - OK チェック: `d="M 18.5 -22 L 21 -19.5 L 25.5 -25"`（stroke `#fff` width 1.8, fill none, linecap/linejoin round）
   - 異常「!」: `d="M 22 -25 V -21 M 22 -18.5 V -18"`（同スタイル）
5. ラベル: 名称 `text-anchor:middle, y=48, font-size=11.5, fill=#1b2430, font-weight=600` / ID `y=62, font-size=9.5, fill=#8a94a0, font-family='IBM Plex Mono',monospace`
6. バッジ（ある場合）: `<g transform="translate(0,-46)">` 内に
   `<rect x="{-bw/2}" y="-10" width="{bw}" height="20" rx="10" fill="{badgeBg}" filter="url(#nwsh)">` + テキスト `y=4, font-size=10, font-weight=600, fill=#fff`
   バッジ幅の計算式（原文）: `bw = ラベル文字数 * 10.5 + 16`

**ノード状態スタイル**（原文 `nodeStyle`）:

| 状態 | fill | stroke | stroke-width | アイコン色 | filter |
|---|---|---|---|---|---|
| `unknown`（未確認） | `#fff` | `#c3c9d1` | 1.5 | `#8a94a0` | `url(#nwsh)` |
| `ok` / `fixed`（確認済/修正済） | `#e6f4ec` | `#1f8a5b` | 1.5 | `#1f8a5b` | `url(#nwsh)` |
| `bad`（異常） | `#fbeeec` | `#c73a2b` | 2 | `#c73a2b` | `url(#nwglowred)` |
| probing（調査中、上書き） | （状態の fill を維持） | `#1f5fbf` | 2.5 | `#1f5fbf` | `url(#nwglow)` + パルス円 |

状態ドット色: bad → `#c73a2b`、ok/fixed → `#1f8a5b`、unknown → なし。

### 5.5 ノードアイコン（8種、strokeWidth 1.9、fill none、色は状態依存 c）

React.createElement 定義の逐語仕様（すべて `<g stroke="{c}" fill="none" stroke-width="1.9" …>` 内）:

- **PC**（linecap/linejoin round）: `<rect x="-12" y="-10" width="24" height="15" rx="2.5"/>` + `<path d="M -6 11 H 6 M 0 5 V 11"/>`
- **AP**（linecap round）: `<circle cx="0" cy="6" r="2.4" fill="{c}"/>` + `<path d="M -7 0 A 10 10 0 0 1 7 0 M -12 -6 A 17 17 0 0 1 12 -6"/>`
- **SW**（linecap/linejoin round）: `<rect x="-13" y="-7" width="26" height="14" rx="3"/>` + `<path d="M -8 -2 L -5 -2 M -8 2 L -5 2 M -1 -2 L 2 -2 M -1 2 L 2 2 M 6 -2 L 9 -2 M 6 2 L 9 2"/>`
- **RT**（linecap/linejoin round）: `<circle r="12.5"/>` + `<path d="M -8 -3 H 4 M 1 -6 L 4 -3 L 1 0 M 8 3 H -4 M -1 0 L -4 3 L -1 6"/>`（双方向矢印）
- **FW**（linejoin round）: `<rect x="-13" y="-10" width="26" height="20" rx="2"/>` + `<path d="M -13 -3.5 H 13 M -13 3.5 H 13 M -4 -10 V -3.5 M 4 -3.5 V 3.5 M -4 3.5 V 10"/>`（レンガ模様）
- **DNS**: `<circle r="11"/>` + `<ellipse rx="4.5" ry="11"/>` + `<path d="M -11 0 H 11 M -9 -6 H 9 M -9 6 H 9"/>`（地球儀）
- **GW**（linecap/linejoin round）: `<rect x="-13" y="-8" width="26" height="16" rx="3"/>` + `<path d="M -7 0 H 7 M 3 -4 L 7 0 L 3 4 M -13 -8 L -8 -14 H 8 L 13 -8"/>`
- **SRV**（linejoin round）: `<rect x="-11" y="-12" width="22" height="9" rx="2"/>` + `<rect x="-11" y="3" width="22" height="9" rx="2"/>` + `<circle cx="-6" cy="-7.5" r="1.3" fill="{c}"/>` + `<circle cx="-6" cy="7.5" r="1.3" fill="{c}"/>`

未知の kind は RT にフォールバック（原文 `icons[kind] || icons.RT`）。

### 5.6 リンク（9本）

エンドポイント定義（原文 `linkDefs`、順序どおり）:

| # | from | to | 状態キー |
|---|---|---|---|
| 1 | PC-01 | SW-01 | `PC-01\|SW-01` |
| 2 | AP-01 | SW-01 | `AP-01\|SW-01` |
| 3 | SW-01 | GW-01 | `SW-01\|GW-01` |
| 4 | GW-01 | RT-MAIN | `GW-01\|RT-MAIN` |
| 5 | GW-01 | RT-BKUP | `GW-01\|RT-BKUP` |
| 6 | RT-MAIN | FW-01 | `RT-MAIN\|FW-01` |
| 7 | RT-BKUP | FW-01 | `RT-BKUP\|FW-01` |
| 8 | FW-01 | DNS-01 | `FW-01\|DNS-01` |
| 9 | FW-01 | APP-01 | `FW-01\|APP-01` |

**パス生成式**（原文）: 端点 `(x1,y1)`,`(x2,y2)`、`cx=(x1+x2)/2` として

```
d = M x1 y1 C cx y1, cx y2, x2 y2
```

（水平方向に丸く曲がる3次ベジェ。中点 `mx=cx`、`my=(y1+y2)/2`）

**描画構造**（各リンク、下→上）:
1. 白アンダーストローク: `<path d="{d}" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round" opacity=".9">`
2. 本線: `<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{width}" stroke-dasharray="{dash}" stroke-linecap="round">`
3. `active` のみ: パケットドット2個
   `<circle r="4.5" fill="#1f5fbf" stroke="#fff" stroke-width="1.5"><animateMotion dur="1.6s" repeatCount="indefinite" path="{d}"/></circle>`
   （2個目は `begin="0.8s"` 付き）
4. `down` のみ: 中点 `(mx,my)` に断線マーク
   `<g transform="translate(mx,my)"><circle r="11" fill="#fff" stroke="#c73a2b" stroke-width="2"/><path d="M -4.5 -4.5 L 4.5 4.5 M 4.5 -4.5 L -4.5 4.5" stroke="#c73a2b" stroke-width="2.2" stroke-linecap="round"/></g>`
5. タグ（ある場合）: `<g transform="translate(mx,ty)"><rect x="-32" y="-10" width="64" height="20" rx="10" fill="{tagBg}" filter="url(#nwsh)"/>` + テキスト `y=4, 10px, 600, #fff`
   `ty = my - (down かつタグあり ? 26 : 16)`

**リンク状態スタイル**:

| 状態 | stroke | width | dash | 付随 |
|---|---|---|---|---|
| `plain`（既定） | `#c3c9d1` | 2.5 | none | — |
| `active`（通信中） | `#1f5fbf` | 3.5 | none | パケットドット×2 |
| `down`（断） | `#c73a2b` | 3.5 | `7 7` | ×マーク |
| `ok`（確認済経路） | `#1f8a5b` | 3.5 | none | — |

### 5.7 状態遷移テーブル（ステップ → ノード/リンク/バッジ/タグ）

初期状態: 全ノード `unknown`、全リンク `plain`、バッジ/タグなし、probing なし。

**Step 2（構成理解）**: 全ノード `ok`、ただし `DNS-01` は `unknown` + バッジ `['確認待ち', amber]`。

**Step 3（自律調査）**: まず全ノードを `unknown` にリセットし、`probeIdx`（0〜6）まで以下を**累積適用**（原文 `seq`）:

| seq index（=probeIdx時点） | 適用内容 |
|---|---|
| 0 | probing: PC-01, APP-01 |
| 1 | PC-01→ok、APP-01→unknown、probing: GW-01 |
| 2 | GW-01→ok、SW-01→ok、リンク `GW-01\|RT-BKUP`→**active**、probing: RT-MAIN |
| 3 | RT-MAIN→**bad**、リンク `GW-01\|RT-MAIN`→**down**、バッジ RT-MAIN=`['異常', red]`、タグ `GW-01\|RT-MAIN`=`['リンク断', red]`、probing: RT-BKUP, APP-01 |
| 4 | APP-01→ok、FW-01→ok、probing: RT-BKUP |
| 5 | RT-BKUP→**bad**、バッジ RT-BKUP=`['ACL異常', red]`、タグ `RT-BKUP\|FW-01`=`['443遮断', red]`、probing: FW-01 |
| 6 | DNS-01→ok、AP-01→ok |

※ probing 配列は累積 push だが、各 seq の実行で前段の probing 対象は状態確定により実質引き継ぎ。`step > 3` では probing を全クリア（`probing.length = 0`）。step 4 以降は `upto=6`（全適用）。

**Step 5（自動復旧）**:
- `applyIdx 0〜2`: probing: RT-BKUP（青パルス）
- `applyIdx >= 3`（step>=5共通）: RT-BKUP→**fixed**、バッジ RT-BKUP=`['修正済', green]`、タグ `RT-BKUP\|FW-01`=`['443許可', green]`

**Step 6（復旧確認）**:
- 検証中（`verifyIdx>=0 && !verifyDone`）: probing: PC-01, APP-01。リンク **active**: `GW-01|RT-BKUP`, `RT-BKUP|FW-01`, `FW-01|APP-01`, `SW-01|GW-01`, `PC-01|SW-01`
- 検証完了（`verifyIdx>=4`）: 上記5リンク→**ok**（緑）。バッジ APP-01=`['業務OK', green]`、RT-MAIN=`['残存課題', amber]`（RT-MAIN は bad のまま、`GW-01|RT-MAIN` は down のまま）

---

## 6. 画面ステップ構成

デモは6ステップ。サイドバー工程名 = `受付・構成図` / `構成理解（Scene Graph）` / `自律調査` / `原因提示・承認` / `自動復旧` / `復旧確認・引き継ぎ`。

### 6.0 ヘッダの状態別値（原文）

**ヘッドライン `headlines`**:

| step | 条件 | 文言 |
|---|---|---|
| 1 | 未アップロード | `構成図のアップロードと症状の申告` |
| 1 | アップロード済 | `構成図を受け取りました。症状を確認して調査を開始します` |
| 2 | — | `VLMが構成図を構造化し、登録機器と照合しています` |
| 3 | probeIdx===0 | `許可範囲のツールで横断切り分けを開始` |
| 3 | probeIdx 1〜6（実行中の見出し、配列順） | `業務通信の到達性を検査` / `拠点GWの経路を確認` / `主回線ルータの状態を確認` / `予備経路経由の通信を検査` / `予備ルータのACLを照合` / `DCファイアウォールのログを確認` |
| 3 | probeIdx>=6 | `複合障害を特定。証拠を整理しています` |
| 4 | — | `修正案を提示し、承認を待っています` |
| 5 | applyIdx<0 | `承認を照合し、適用準備中` |
| 5 | 0<=applyIdx<5 | `承認された差分を適用中` |
| 5 | applyIdx>=5 | `適用完了。復旧確認へ進めます` |
| 6 | 検証未完 | `独立検証器で業務テストを実行` |
| 6 | 検証完了 | `業務復旧を確認。残存課題を引き継ぎます` |

**経過時間 `elapsedMap`**: step1=`00:00`、step2=`00:14`、step3=probeIdx別 `['00:22','00:31','00:38','00:46','00:55','01:04','01:12'][probeIdx]`、step4=`01:20`、step5=`01:41`、step6=検証完了なら`02:03`、未完なら`01:52`。

**SMコード `smCodes`**: 1:`RECEIVED`、2:`INVESTIGATING`、3:`INVESTIGATING`、4: 承認済`APPROVED` / 保留`NEEDS_HUMAN` / 却下`INVESTIGATING` / それ以外`AWAITING_APPROVAL`、5: applyIdx>=5→`APPLIED` / applyIdx>=0→`APPLYING` / それ以外→`APPROVED`、6: 完了→`SERVICE_RESTORED` / 未完→`VERIFYING`。

**業務状態 `biz`**: §4.3 参照。

### 6.1 Step 1: 受付・構成図（`is1`）

2カラム（カード2枚）。左「構成図」カード（`order:{figOrder}`、padding 20px）+ 右「症状の申告」カード（`order:2`）。

**構成図カード**:
- ヘッダ: h2 `構成図` + 右注記 `PNG / JPEG 1枚`
- 未アップロード時: ドロップゾーン（§4.14）。コピー:
  - `ネットワーク構成図をここにドロップ`（14px/600）
  - `または クリックしてサンプル構成図を使用`（12px `#5d6773`）
  - クリックで `uploaded=true`
- アップロード後（`display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap`）:
  - プレビュー枠（`flex:1;min-width:260px;border:1px solid #e3e6ea;border-radius:10px;background:#fbfbfc;padding:12px`）: ラベル `プレビュー（原図）`（11px `#8a94a0`）+ 方眼プレースホルダ（§1.7、`min-height:220px`、中央に `構成図画像（拠点A_構成図.png）` 12px `#8a94a0`）
  - メタ列（`width:220px; gap:8px; font-size:12.5px`、各行 `display:flex;justify-content:space-between`）:
    - `ファイル` → `拠点A_構成図.png`（mono 11.5px）
    - `サイズ` → `1.2 MB · 1920×1080`
    - `版` → `v3（2026-06-12 更新）`
    - 緑ドット（7px）+ `アップロード完了`（`#1f8a5b`、margin-top 4px）

**症状の申告カード**:
- h2 `症状の申告`
- フォーム風表示（§4.15）:
  - `拠点` → `拠点A（東京・営業所）`
  - `対象業務` → `受注システム（https://order.example.local）`
  - `症状` → `9:40頃から受注画面が開かない。社内チャットは使える。機器のランプは点灯している。`
- 注記ボックス: `接続情報・許可範囲は導入時登録済み（拠点A設定 v7）。再入力は不要です。`
- ボタン `調査を開始`（未アップロード時 disabled、bg `#b8c0ca`）→ `go(2)`

### 6.2 Step 2: 構成理解（`is2`）— 構成図カード + Scene Graph パネル

右パネル（`order:2; gap:14px`）:

**VLM 読取結果カード**:
- ヘッダ: h2 `VLM 読取結果` + 右注記（mono 11px）`{{vlmModel}}` = `qwen2.5-vl-32b · local`
- 統計タイル3枚（§4.4）: `抽出ノード` 9 / `抽出リンク` 9 / `確認待ち` 1（琥珀）
- 読取行4件（`gap:6px`、行: `display:flex;align-items:center;gap:10px;font-size:12.5px;padding:7px 10px;border-radius:8px;background:{r.bg}`）:

| id (mono 11.5px, 幅74px) | text | conf | conf色 | 行bg |
|---|---|---|---|---|
| RT-MAIN | `主回線ルータ · GW-01と接続` | 0.97 | green | `#f8f9fb` |
| RT-BKUP | `予備回線ルータ · GW-01と接続` | 0.95 | green | `#f8f9fb` |
| APP-01 | `受注サービス · 10.50.0.20` | 0.93 | green | `#f8f9fb` |
| DNS-01 | `識別子が不鮮明 → 管理者確認待ち（実測で補完）` | 0.61 | amber | `#fdf3e7` |

**Scene Graph ダークパネル**（§4.8）: ヘッダ左 `Scene Graph（JSON・未修正出力）` / 右 `topology v3 · 図由来`。JSON 全文（原文）:

```json
{
  "topology_version": "v3",
  "source": "diagram",
  "nodes": [
    { "id": "PC-01",   "type": "client",   "role": "業務端末",     "zone": "site-A" },
    { "id": "GW-01",   "type": "gateway",  "role": "拠点GW",       "zone": "site-A" },
    { "id": "RT-MAIN", "type": "router",   "role": "主回線",       "zone": "wan" },
    { "id": "RT-BKUP", "type": "router",   "role": "予備回線",     "zone": "wan" },
    { "id": "FW-01",   "type": "firewall", "role": "DC FW",        "zone": "dc" },
    { "id": "APP-01",  "type": "service",  "role": "受注サービス", "addr": "10.50.0.20:443" },
    { "id": "DNS-01",  "type": "dns",      "confidence": 0.61, "needs_review": true }
  ],
  "links": [
    { "from": "GW-01",   "to": "RT-MAIN", "kind": "primary" },
    { "from": "GW-01",   "to": "RT-BKUP", "kind": "backup" },
    { "from": "RT-MAIN", "to": "FW-01" },
    { "from": "RT-BKUP", "to": "FW-01" },
    { "from": "FW-01",   "to": "APP-01" }
  ],
  "business_path": ["PC-01", "SW-01", "GW-01", "RT-MAIN", "FW-01", "APP-01"]
}
```

**ボタン**: `構成を確定して自律調査へ`（青CTA）→ `go(3)`

### 6.3 Step 3: 自律調査（`is3`）— 構成図カード + 調査パネル

右パネル（`order:2; gap:14px`）: 仮説カード → 証拠カード → 次の調査ボックス+ボタン。

**仮説カード**: ヘッダ h2 `仮説` + 右注記 `ステップ {{probeIdx}} / 6`。
仮説なし時（probeIdx===0）: `まだ仮説はありません。最初の検査を実行してください。`（12.5px `#8a94a0`）

仮説の出現条件と文言（原文ロジック）:

| 条件 | id | title | accent | state | note |
|---|---|---|---|---|---|
| probeIdx 1〜2 | H1 | `経路またはフィルタの異常` | amber | `調査中` | `DNS/ICMPは成功、TCP 443のみ失敗` |
| probeIdx===3 | H1 | `主回線リンク断` | red | `支持` | `RT-MAIN Gi0/0 down を実測で確認` |
| probeIdx>=4 | H1 | `主回線リンク断` | red | `支持・ただし単独では説明不足` | `RT-MAIN Gi0/0 down。切替後も業務が再開しないため、第二の要因が存在する` |
| probeIdx===4 | H2 | `予備経路でHTTPSが遮断されている` | amber | `調査中` | `予備経路上で443が無応答。ACLを照合中` |
| probeIdx===5 | H2 | 同上 | red | `支持` | `RT-BKUP ACL 110 ルール30が10.50.0.20:443をdeny` |
| probeIdx>=6 | H2 | 同上 | red | `確定（反証なし）` | 同上（`RT-BKUP ACL 110 ルール30が10.50.0.20:443をdeny`） |

**証拠カード**: h2 `証拠（実測）`。空のとき `証拠はまだありません。`。
証拠 = probes の先頭 `probeIdx` 件を `EV-0{n} · {target}` に改名して**逆順**（新しいものが上）表示。

probes 全6件（原文、逐語）:

| # | t | tool | target | verdict | 色 | out（mono, 改行含む） | reason | next（次の調査文） |
|---|---|---|---|---|---|---|---|---|
| 1 | 00:22 | `probe_path` | `PC-01 → APP-01 · HTTPS` | `失敗` | red | `GET https://order.example.local/ → timeout (10s)`\n`DNS ok 10.50.0.20 · ICMP ok 12ms · TCP:443 no SYN-ACK` | `名前解決とICMPは成功。TCP 443のみ失敗 → 経路上のフィルタか経路異常を疑う` | `拠点GWの経路テーブルを確認し、どの回線を使っているか特定する` |
| 2 | 00:31 | `observe_node` | `GW-01 · 経路` | `注意` | amber | `default via 10.0.2.1 (RT-BKUP)  metric 20`\n`# primary 10.0.1.1 (RT-MAIN) 経路が消えている` | `通常は主回線経由のはず。予備へ切り替わっている → 主回線側の状態を確認` | `主回線ルータ RT-MAIN のインターフェース状態を確認する` |
| 3 | 00:38 | `observe_node` | `RT-MAIN · インターフェース` | `異常` | red | `Gi0/0  line protocol down  (last up 09:38:12)`\n`Gi0/1  up` | `主回線リンク断を確認。仮説H1を支持。ただし予備へ切替済みなら業務は通るはず → 未復旧を説明できない` | `予備経路経由で業務通信が通るかを検査する` |
| 4 | 00:46 | `probe_path` | `PC-01 → APP-01 · via RT-BKUP` | `失敗` | red | `traceroute: GW-01 → RT-BKUP → * * *`\n`TCP:443 no response · TCP:22 (禁止) filtered` | `予備経路上で443が止まっている。RT-BKUP のフィルタを疑う → 仮説H2を追加` | `予備ルータ RT-BKUP の転送ACLを照合する` |
| 5 | 00:55 | `observe_node` | `RT-BKUP · ACL 110` | `異常` | red | `ip access-list extended 110`\n` 30 deny tcp 10.10.0.0 0.0.255.255 host 10.50.0.20 eq 443  (matches: 1,284)`\n` 40 deny tcp any any eq 23` | `ルール30が拠点→受注サービスのHTTPSを遮断。カウンタ増加中 → H2を支持` | `DC側FWのログで拠点からのセッションが到達していないことを確認する（反証の確認）` |
| 6 | 01:04 | `query_evidence` | `FW-01 · セッションログ` | `確認` | green | `sessions from 10.10.1.0/24 to 10.50.0.20:443 since 09:38 → 0`\n`sessions from other sites → normal` | `FW・サービス側に異常なし。原因はRT-BKUPのACLに限定される。H2の反証なし` | （空文字） |

**次の調査ボックス**（`moreProbes = probeIdx<6` のとき表示）: `次の調査：{{nextProbeText}}`
`nextProbeText`: probeIdx===0 なら `業務端末から受注サービスへのHTTPS到達性を検査する`、以降は直前 probe の `next`。

**ボタン**:
- `moreProbes` 時: `次の検査を実行`（青CTA）→ `probeIdx = min(6, probeIdx+1)`
- `probesDone`（probeIdx>=6）時: `根本原因を確定し復旧案へ`（青CTA）→ `go(4)`

### 6.4 Step 4: 原因提示・承認（`is4`）— 構成図カード + （左カラム3カード + iPadパネル）

右セクション: `order:2; display:flex; gap:14px; flex-wrap:wrap; align-items:flex-start`。左カラム `flex:1; min-width:280px; gap:14px`、右に iPad（§7）。

**根本原因カード**: h2 `根本原因（複合障害）`。要因ボックス（§4.13）×2:
- `要因A`: **主回線リンク断**（RT-MAIN Gi0/0 down）。冗長化制御により予備経路へ切替済み。<span color #5d6773>証拠 EV-02, EV-03</span>
  - 原文HTML: `<b>主回線リンク断</b>（RT-MAIN Gi0/0 down）。冗長化制御により予備経路へ切替済み。<span style="color:#5d6773">証拠 EV-02, EV-03</span>`
- `要因B`: 原文 `<b>予備ルータ ACL 110 が受注サービス向け HTTPS を遮断</b>。切替後も業務が再開しない直接原因。<span style="color:#5d6773">証拠 EV-04, EV-05</span>`

**変更計画カード**:
- ヘッダ: h2 `変更計画` + 右注記（mono 11px）`PLAN-0042-v2 · a91f3c`
- 対象行（12px `#5d6773`）: `対象：RT-BKUP · 転送ACL 110 · 方向 in（拠点→サービス）`
- diffブロック（§4.9）、行と色（逐語）:
  - `ip access-list extended 110`（`#8a94a0`）
  - `- 30 deny   tcp 10.10.0.0 0.0.255.255 host 10.50.0.20 eq 443`（`#ff8a7a`）
  - `+ 30 permit tcp 10.10.1.0 0.0.0.255 host 10.50.0.20 eq 443`（`#7fe0a5`）
  - `  40 deny   tcp any any eq 23   (禁止通信・維持)`（`#8a94a0`）
- 影響タイル3枚（§4.5）: `影響`→`拠点A→受注サービスの443のみ` / `復元`→`元ルール30を再投入（登録済）` / `観測前提の鮮度`→`30秒以内に再観測`

**事前検証カード**:
- ヘッダ: h2 `事前検証（検証用環境）` + 右注記（11px green 600）`複製一致 ✓`
- チェック行4件（§4.10、全件 mark `✓` bg green）:

| name | val (mono) |
|---|---|
| `複製環境と対象環境の一致（設定・リンク・サービス）` | `32/32 項目` |
| `業務テスト：HTTPS 受注画面` | `3/3 成功` |
| `禁止通信：TCP 23 / 22` | `遮断維持` |
| `他拠点向け通信の回帰` | `影響なし` |

### 6.5 Step 5: 自動復旧（`is5`）— 構成図カード + 適用パネル

**適用カード**: ヘッダ h2 `承認された差分のみ適用` + 右注記（mono 11px）`EXEC-7f21 · 冪等キー 9c0e`。
適用ステップ5件（原文 `applyDefs`、行スタイル §4.10）:

| # | name | detail (mono) |
|---|---|---|
| 1 | `承認 APR-311 と計画版・ハッシュを照合` | `plan=PLAN-0042-v2 hash=a91f3c expires=10:12` |
| 2 | `観測前提を再確認（30秒以内）` | `RT-MAIN Gi0/0 down · ACL110#30 deny · 業務不通 → 一致` |
| 3 | `対象をロック・適用前状態を永続化` | `RT-BKUP running-config snapshot → EXEC-7f21` |
| 4 | `ACL 110 ルール30 を置換` | `permit tcp 10.10.1.0/24 → 10.50.0.20 eq 443` |
| 5 | `適用結果を読み取りで照合` | `show access-list 110 → 差分一致 · 二重適用なし` |

完了行の時刻表示: `01:${41 + i*3}` → `01:41` / `01:44` / `01:47` / `01:50` / `01:53`。

**下部（状態別）**:
- `applyNotStarted`（applyIdx<0）: ボタン `適用を実行（承認 APR-311 を照合）`（青CTA）→ `runApply()`
- `applyRunning`（0<=applyIdx<5）: スピナー + `適用中… 対象をロックし、前提を再観測しています`
- `applyDone`（applyIdx>=5）: ボタン `復旧確認試験へ`（緑CTA）→ `go(6)`

### 6.6 Step 6: 復旧確認・引き継ぎ（`is6`）— 構成図カード + 検証パネル

**復旧確認カード**: ヘッダ h2 `復旧確認試験（独立検証器）` + 右注記 `利用者と同じ経路 · PC-01 → APP-01`。
検証テスト4件（原文 `verifyDefs`）:

| # | name | detail（完了時のみ表示、mono） |
|---|---|---|
| 1 | `HTTPS 受注画面 取得（3回連続）` | `GET / → 200 · 214ms / 198ms / 205ms` |
| 2 | `期待内容の一致` | `title="受注一覧" · 認証リダイレクト正常` |
| 3 | `禁止通信の遮断維持` | `TCP 23 → filtered · TCP 22 → filtered` |
| 4 | `回帰：他拠点・他サービス` | `拠点B→APP-01 200 · DNS 正常` |

実行中の行 detail は `実行中…`、未実施は空。完了行は右端に `合格`（11px/600 green）。

- `verifyNotStarted`: ボタン `業務テストを実行`（単色 `#1f5fbf`、margin-top 4px）→ `runVerify()`
- `verifyRunning`: スピナー + `検証中…`

**verifyDone 後**:
1. 成功バナー（§4.12）: 見出し `業務復旧 · 主回線の対応は継続`、本文（原文HTML）:
   `受注業務は予備経路で再開しました。状態は <span style="font-family:'IBM Plex Mono',monospace">SERVICE_RESTORED</span>。完全解決ではありません。`
2. **残存課題カード**: h2 `残存課題・引き継ぎ`
   - 残存ボックス（§4.13 琥珀）: ラベル `残存A`、本文（原文）`<b>主回線リンク断</b>（RT-MAIN Gi0/0）。物理断の可能性。担当候補：回線事業者（未確認）`
   - 引き継ぎタイル3枚: `引き継ぎ状態`→`依頼準備済み`（font-weight:600） / `添付証拠`→`EV-02, EV-03, 業務テスト結果` / `再入力`→`不要（同一案件を参照）`
   - ボタン行（`gap:8px; flex-wrap:wrap`）: `引き継ぎ文書を生成`（ダーク、onClick なし＝飾り） / `デモを最初から`（アウトライン）→ 全状態リセット

---

## 7. iPad承認パネル（Step 4 右側）

### 7.1 ベゼルとスクリーン

```css
/* ベゼル */
width:300px; flex:none; background:#0f1420; border-radius:32px; padding:11px;
box-shadow: 0 34px 60px -24px rgba(15,20,32,.5), inset 0 0 0 1px rgba(255,255,255,.1);

/* スクリーン */
background: linear-gradient(180deg,#fbfbfd,#f2f4f7);
border-radius:23px; min-height:560px;
display:flex; flex-direction:column; overflow:hidden;
```

### 7.2 コンテンツ（上から、コピー逐語）

1. **ステータスバー**: `display:flex;justify-content:space-between;padding:8px 16px 0;font-size:10.5px;color:#5d6773;font-weight:600` — 左 `10:07` / 右 `iPad · 承認端末`
2. **タイトルブロック**（`padding:14px 16px 6px`）:
   - `変更承認`（10.5px `#5d6773`）
   - `INC-2026-0042 · 拠点A`（15px/700、margin-top 2px）
   - `PLAN-0042-v2 · 有効期限 5:00`（mono 10.5px `#5d6773`、margin-top 2px）
3. **情報カード4枚**（`padding:0 16px; gap:8px; font-size:12px`。各カード: `background:#fff;border-radius:12px;padding:10px 12px;border:1px solid rgba(17,24,39,.06);box-shadow:0 1px 2px rgba(17,24,39,.04)`、ラベル10.5px `#5d6773`、本文 margin-top 2px line-height 1.5）:

| ラベル | 本文 |
|---|---|
| `変更内容` | `RT-BKUP ACL 110 ルール30：拠点A→受注サービス HTTPS を許可` |
| `想定影響` | `受注業務の再開。他ポート・他拠点の遮断は維持` |
| `事前検証` | `業務テスト 3/3 · 禁止通信 遮断維持 · 合格`（color `#1f8a5b`、font-weight 600） |
| `失敗時の復元` | `元ルールを自動再投入・再検証` |

4. **フッター**（`margin-top:auto; padding:14px 16px 16px; gap:8px`）:
   - 承認者行（11px `#5d6773`、justify-between）: 左 `承認者：田中（変更承認権限）` / 右 状態ラベル（600、色は状態別）

承認状態マップ（原文 `apprMap`）:

| appr | ラベル | 色 |
|---|---|---|
| pending | `承認待ち` | amber `#b9770e` |
| approved | `承認済み` | green `#1f8a5b` |
| rejected | `却下` | red `#c73a2b` |
| hold | `保留` | amber `#b9770e` |

### 7.3 状態別フッターUI

**pending**:
- ボタン `承認して適用へ`: `border:0;border-radius:13px;padding:13px;font-size:14px;font-weight:700;color:#fff;background:linear-gradient(180deg,#2aa06c,#1f8a5b);box-shadow:0 1px 2px rgba(31,138,91,.25),0 10px 20px -10px rgba(31,138,91,.7);transition:transform .15s,box-shadow .15s`（hover: `translateY(-1px)`）→ appr='approved'
- 2ボタン行（`gap:8px`、各 `flex:1;border:1px solid #d6dbe1;border-radius:11px;padding:10px;font-size:13px;font-weight:600;background:#fff`）:
  - `保留`（color `#1b2430`）→ appr='hold' / `却下`（color `#c73a2b`）→ appr='rejected'

**approved**:
- 結果表示: `background:#e6f4ec;border-radius:11px;padding:12px;font-size:12.5px;color:#1f8a5b;font-weight:600;text-align:center` — `承認済み · 10:07:42 · Macへ同期`
- ボタン `自動復旧を開始`（青グラデ、radius 13px、padding 13px、700）→ `go(5)`

**rejected**:
- 結果表示（`background:#fbeeec` / color red、同形）: `却下 · 対象環境は変更されません`
- ボタン `承認待ちへ戻す`（`border:1px solid #d6dbe1;border-radius:11px;padding:10px;font-size:13px;font-weight:600;background:#fff`）→ appr='pending'

**hold**:
- 結果表示（`background:#fdf3e7` / color amber）: `保留中 · 案件は NEEDS_HUMAN`
- ボタン `承認待ちへ戻す`（同上）→ appr='pending'

---

## 8. JSの挙動

### 8.1 状態変数（原文）

```js
state = { step: 1, uploaded: false, probeIdx: 0, appr: 'pending', applyIdx: -1, verifyIdx: -1 };
```

| 変数 | 域 | 意味 |
|---|---|---|
| `step` | 1〜6 | 現在の工程 |
| `uploaded` | bool | 構成図アップロード済みか |
| `probeIdx` | 0〜6 | Step3 で完了した検査数（= 適用済み seq インデックス） |
| `appr` | `'pending' \| 'approved' \| 'rejected' \| 'hold'` | 承認状態 |
| `applyIdx` | -1〜5 | Step5 適用進捗（-1=未開始、0..4=当該行実行中、5=完了） |
| `verifyIdx` | -1〜4 | Step6 検証進捗（-1=未開始、0..3=実行中、4=完了。`verifyDone = verifyIdx>=4`） |

### 8.2 ステップ遷移 `go(n)`（原文ロジック — サイドバーから任意ステップへジャンプ可能）

```js
go(n) {
  const st = { step: n };
  if (n >= 2) st.uploaded = true;
  if (n >= 4) st.probeIdx = 6;
  if (n >= 5 && s.appr !== 'approved') st.appr = 'approved';
  if (n >= 6 && s.applyIdx < 5) st.applyIdx = 5;
  if (n < 5) { st.applyIdx = -1; }
  if (n < 6) { st.verifyIdx = -1; }
  if (n < 4) { st.appr = 'pending'; }
  if (n < 3) { st.probeIdx = 0; }
}
```

前方ジャンプは前提状態を自動充足し、後方ジャンプは後続状態をリセットする（冪等）。

### 8.3 タイマー進行

```js
runApply()  { tick(i): applyIdx=i;  i<5 → 900ms 後に tick(i+1) }   // 0→5、行あたり900ms
runVerify() { tick(i): verifyIdx=i; i<4 → 800ms 後に tick(i+1) }   // 0→4、行あたり800ms
```

タイマーは `timers[]` に蓄積し `componentWillUnmount` で `clearTimeout`。

### 8.4 イベント一覧（UI操作 → 状態変更）

| UI | 操作 | 状態変更 |
|---|---|---|
| ドロップゾーン | click | `uploaded=true` |
| `調査を開始` | click（uploaded時のみ） | `go(2)` |
| `構成を確定して自律調査へ` | click | `go(3)` |
| `次の検査を実行` | click | `probeIdx = min(6, probeIdx+1)` |
| `根本原因を確定し復旧案へ` | click | `go(4)` |
| iPad `承認して適用へ` / `却下` / `保留` / `承認待ちへ戻す` | click | `appr = 'approved' / 'rejected' / 'hold' / 'pending'` |
| iPad `自動復旧を開始` | click | `go(5)` |
| `適用を実行（承認 APR-311 を照合）` | click | `runApply()` |
| `復旧確認試験へ` | click | `go(6)` |
| `業務テストを実行` | click | `runVerify()` |
| `デモを最初から` | click | 全初期化 `{step:1, uploaded:false, probeIdx:0, appr:'pending', applyIdx:-1, verifyIdx:-1}` |
| 工程ボタン（サイドバー） | click | `go(n)` |

### 8.5 SSEイベント駆動 React への対応付け（実装ガイド）

派生値はすべて `(step, uploaded, probeIdx, appr, applyIdx, verifyIdx)` の純関数（`renderVals()`）で計算されている。React 再実装では同6変数を単一ストア（reducer）に置き、SSE イベントを次のように還元すればよい:

- `phase_changed(n)` → `go(n)` と同じ充足/リセット規則を適用
- `probe_completed` → `probeIdx++`（証拠・仮説・トポロジ状態は §5.7 / §6.3 の表から導出）
- `approval_updated(status)` → `appr = status`
- `apply_progress(i)` → `applyIdx = i`（0..5）
- `verify_progress(i)` → `verifyIdx = i`（0..4）

トポロジの見た目（ノード状態 / リンク状態 / バッジ / タグ / probing）は §5.7 の状態遷移テーブルを同じ順で累積適用して求める。

### 8.6 dc-runtime 固有事項（移植時に読み替え）

- `sc-if value="{{x}}"` → 条件レンダリング、`sc-for list="{{xs}}" as="x"` → map レンダリング
- `style-hover="…"` → CSS `:hover`（React では class 化する）
- `data-props`: `layout`（enum、§3.4）と `showTechDetails`（boolean）はエディタ用プロップ。React では設定値 or 固定値にする。

---

## 9. アニメーション一覧

### 9.1 @keyframes（原文逐語）

```css
@keyframes nwpulse{0%{r:30;opacity:.8}100%{r:52;opacity:0}}
@keyframes nwdash{to{stroke-dashoffset:-24}}
@keyframes nwspin{to{transform:rotate(360deg)}}
```

> **注**: `nwdash` は定義されているが、現行のレンダリングコードではリンクの `style` が常に空文字のため**未使用**（破線流しの予備）。`nwpulse` は SVG の `r` プロパティを CSS アニメーションで動かしており、Chromium 系（CSS で geometry プロパティをアニメーション可能）前提。React 移植時は同等挙動を確認するか SMIL/transform に置換する。

### 9.2 適用箇所

| アニメーション | 適用対象 | 指定（原文） |
|---|---|---|
| `nwpulse` | 調査中ノードのパルス円（`r=30, fill:none, stroke:#1f5fbf, stroke-width:2.5`） | `animation: nwpulse 1.4s ease-out infinite` |
| `nwspin` | スピナー（14px 円、`border:2px solid #cfe0f7; border-top-color:#1f5fbf`） | `animation: nwspin .8s linear infinite` |
| SMIL `animateMotion` | active リンク上のパケットドット（`circle r=4.5 fill=#1f5fbf stroke=#fff sw=1.5`）×2 | `dur="1.6s" repeatCount="indefinite" path="{リンクのd}"`、2個目のみ `begin="0.8s"` |
| transition（ボタン） | 青/緑CTA、iPad承認ボタン | `transition: transform .15s, box-shadow .15s`、hover で `translateY(-1px)` + シャドウ強調 |
| transition（ドロップゾーン） | Step1 ドロップ領域 | `transition: background .15s, border-color .15s`、hover で `background:#eef3fb; border-color:#1f5fbf` |
| フィルタ | 調査中ノード `url(#nwglow)` / 異常ノード `url(#nwglowred)` / 通常 `url(#nwsh)` | §5.2 |

---

*（本書終わり — 出典: `NetWalker Demo v2.dc.html` 2026-09-20 時点、コミット 61289ca 相当）*
