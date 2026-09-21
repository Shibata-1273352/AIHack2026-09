=======
# NetWalker — 拠点ネットワーク障害の自律調査・承認付き復旧エージェント

AIHACK2026 提出プロジェクト。「受注画面が開かない」という非専門家の申告から、
AIエージェントが**実通信を伴う擬似ネットワーク**を調査し、複合障害
（主回線リンク断 + 予備経路のACL誤設定）を特定。検証環境で修正を事前検証し、
**人間の承認**を経て適用、独立検証器で業務復旧を確認するまでを実演する。

要件定義書: [docs/requirements/NetWalker.md](docs/requirements/NetWalker.md)

## 構成

```
Mac (ホスト)
├── sim/       Docker privileged コンテナ内の擬似ネットワーク
│              netns×5 (client—gw—{r1主,r2予備}—srv) ×2系統（対象/検証クローン）
│              nginx HTTPS受注サービス・nftables ACL・冗長化制御デーモン
│              制御API :9000（/agent/*=診断ツール ↔ /admin/*=注入・正解。分離）
├── backend/   FastAPI :8000（uv / Python 3.12）
│              案件状態機械(RECEIVED→…→SERVICE_RESTORED)・承認管理・
│              エージェント(scripted決定木 / OrcaRouter LLM)・VLM構成図読取・
│              OTel風スパン記録(SQLite)・SSE・フロント静的配信
└── frontend/  React + Vite + TS（/console /approve /ops）
```

- **調査はすべて実測**: curl / ip / nft の実コマンド出力が証拠として保存・表示される
- **修正はホワイトリスト制**: r2 の nft ルール削除のみ。`POLICY-*` の削除・全面解除はサーバが拒否
- **承認はサーバ検証**: 計画版+ハッシュ+期限。未承認・失効・ハッシュ不一致・二重送信は適用されない
- **冗長化制御はAIと独立**: リンク断3回連続検知で予備経路へ自動切替（1秒周期）

## 必要なもの

- macOS + Docker Desktop（Apple Silicon 動作確認済み）
- [uv](https://docs.astral.sh/uv/)（`brew install uv`）
- Node.js 20+（フロントエンドのビルド）
- （任意）OrcaRouter API キー — 無くても scripted モードでフル動作

## 起動

```bash
./demo.sh          # Docker起動待ち → sim build/run → backend起動 → URL表示
./demo.sh status   # 状態確認
./demo.sh stop     # 停止
```

初回はイメージビルドと `npm install` が走るため数分かかる。

### OrcaRouter を使う場合（LLM 自律調査 + VLM 構成図読取）

```bash
cp backend/.env.example backend/.env
# ORCAROUTER_API_KEY=<キー> を記入（コミット禁止。.gitignore 済み）
./demo.sh stop && ./demo.sh
```

- `NW_ROUTE_MODE=record` で実行すると実応答を `backend/golden/` に保存し、
  以後 API 障害時はそこへ自動フォールバックする（画面に「golden再生」と明示）
- キー未設定・API障害・予算超過・上限到達時は **scripted 決定木へ自動フォールバック**し、
  実行モードとして画面に表示される。デモは常に成立する
- モデル候補列・単価・予算は `backend/app/llm/route_policy.yaml` で宣言（コード直書きなし）

## デモの流れ

/console は **4K/FHD どちらでもページスクロール無しの一画面ダッシュボード**
（1920×1080 論理ステージを画面へ自動拡縮）。運転操作はコンソール内の
**隠しドロワー（キー `o` または右下の ⚙）** と `/ops` ページの両方から行える。

1. **① 環境リセット** — 正常状態（業務テスト合格・telnet遮断）。構成図に業務パケットが流れる（sim 実測と2秒周期で同期）
2. **② 複合障害を注入** — A: 主回線リンク断（r1側 link down）+ B: r2 に `BAD-ACL-443` drop ルール
   - 注入から約3秒で冗長化制御が予備経路へ切替（ただし障害Bで業務は不通のまま）。**画面のパケットが止まり「業務不通」表示**
3. **③ 申告 → 調査開始** — エージェントが業務テスト→VLM照合→GW観測→r1観測→
   層別プローブ→r2 ACL観測、と証拠を積んで両障害を特定
4. **事前検証** — 対象環境を検証環境へ複製・一致判定→修正適用→業務/回帰テスト
5. **承認** — コンソール右カラムの iPad ベゼル風パネル、または実iPadの
   `http://<MacのIP>:8000/approve`（同一Wi-Fi）。どちらからでも決裁でき、
   サーバの版・ハッシュ・期限照合が二重承認を防ぐ
6. **適用→検証** — 前提再観測(30秒鮮度)→冪等キー付き適用→業務3回連続+禁止遮断維持
7. **SERVICE_RESTORED** — 業務復旧（構成図に緑パケット）。主回線断は残存課題として担当・次作業を記録

画面: `/console`（Mac調査コンソール・一画面）・`/approve`（iPad）・`/ops`（運転席）

リハーサル自動確認: `cd frontend && node scripts/rehearsal.mjs`
（FHD/4K 両解像度で全フェーズのスクショと「スクロール無し」を機械検証。要 `npm install`）

## 検証済みシナリオ

| 条件 | 結果 |
|---|---|
| 障害なし (T-01) | 業務正常を確認し、変更を提案しない |
| A単独 (T-02) | 冗長化制御で業務継続。主回線断を残存課題として報告 |
| B単独 (T-03) | 主回線利用中は業務正常（潜在障害） |
| A+B複合 (T-04) | 二要因を証拠付きで特定→検証→承認→適用→復旧 |
| 承認なし/ハッシュ不一致/期限切れ (T-06/T-07) | 適用拒否（403） |
| POLICY-* 削除・r2以外への変更 | サーバが拒否（M-18） |
| 冪等キー再送 | 二重適用なし（同一実行を再生） |
| LLM障害/キー未設定 (T-10) | scripted へ自動フォールバック、モード表示 |

## 機微情報の扱い（N-01）

- API キーは `backend/.env`（gitignore 対象）のみ。コード・ログ・画面・推論入力に出さない
- 自己署名証明書はコンテナ内で生成、リポジトリに含まない
- デモデータはすべて合成（実在の顧客情報なし）

## 制約・既知の限界

- OTel は簡易実装（SQLite スパン + 独自タイムライン表示）。Collector 連携は未実装
- DGX Spark ローカルLLM（M-16）は未接続。VLM/判断は OrcaRouter または scripted
- 実機・マルチベンダー機器（W-04）は対象外。netns + nftables による Linux 等価環境
- 冗長化制御は自作の簡易デーモン（BGP/VRRP等の実装ではない）

