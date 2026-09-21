# NetWalker — 拠点ネットワーク障害の自律調査・承認付き復旧エージェント

AIHACK2026 提出プロジェクト。「受注画面が開かない」という非専門家の申告から、
AIエージェントが**実通信を伴う擬似ネットワーク**を調査し、複合障害
（主回線リンク断 + 予備経路のACL誤設定）を特定。検証環境で修正を事前検証し、
**人間の承認**を経て適用、独立検証器で業務復旧を確認するまでを実演する。

- **アーキテクチャ**: [docs/architecture.md](docs/architecture.md)（構成図・信頼境界・データフロー）
- **審査5項目アピール**: [docs/judging.md](docs/judging.md)（実装証拠・実測値の索引）
- **デモ台本（4分版）**: [docs/demo-script.md](docs/demo-script.md)
- **A/B/B'/R 比較実測**: [docs/evaluation/results.md](docs/evaluation/results.md)
- **候補モデルの実タスク検証**: [docs/evaluation/models.md](docs/evaluation/models.md)
- **OWASP 対応表（Top 10:2025 / Agentic ASI01–ASI10）**: [docs/security-owasp.md](docs/security-owasp.md)
- **攻撃耐性の検証記録**: [docs/evidence/T-11.md](docs/evidence/T-11.md)
  / [ゲートウェイ側の記録](docs/evidence/orcarouter-guardrails.md)
- **要件定義書**: [docs/requirements/NetWalker.md](docs/requirements/NetWalker.md)

## 提出用記事（Zenn）

`articles/` に Zenn CLI 準拠の記事を3本置いている（`published: false` のまま）。

| ファイル | 役割 |
|---|---|
| `articles/netwalker-aihack2026.md` | **本編**（提出用）。全体像・デモ・審査5項目・実測値 |
| `articles/netwalker-architecture.md` | アーキテクチャ編（本編からリンク） |
| `articles/netwalker-security.md` | セキュリティ編（本編からリンク） |

公開前に、記事間リンクとリポジトリURLのプレースホルダを置換すること。

```bash
# Zenn のユーザー名（または Publication 名）と GitHub の owner/repo に置換する
sed -i '' 's/ZENN_USERNAME/<あなたのZennユーザー名>/g; s|GITHUB_OWNER/GITHUB_REPO|<owner>/<repo>|g' articles/*.md
# 内容を確認してから published: true にする
```

プレビュー: `npx zenn-cli@latest preview`（リポジトリ直下で実行）

## デモ動画（ライブの予備）

```bash
./demo.sh                                  # 表示された token を控える
cd frontend
APPROVAL_TOKEN=<token> node scripts/record-demo.mjs
# → docs/media/netwalker-demo.mp4（ffmpeg があれば）/ .webm
```

実UI・実シミュレータ・実モデルで通し実演を1920×1080で録画する（無音）。
[demo-script.md](docs/demo-script.md) の4分版の配分に合わせ、各場面で読む時間を取っている。
動画ファイルは `.gitignore` 対象（リポジトリを重くしないため）。

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

/console は文字サイズを維持するレスポンシブなデモ画面です。
構成図・現在の通信状態・工程別の説明を表示し、証拠とタイムラインは「技術詳細」から確認できます。
画面右上の **「デモをリセット」** で環境と案件表示を初期化できます。
過去の案件・証拠は保存され、旧案件への承認は拒否されます。
調査・適用の実行中はリセット不可、承認待ち・終了後には利用できます。

1. **① 環境リセット** — 正常状態（業務テスト合格・telnet遮断）。構成図に業務パケットが流れる（sim 実測と2秒周期で同期）
2. **① 複合障害を再現** — A: 主回線リンク断（r1側 link down）+ B: r2 に `BAD-ACL-443` drop ルール
   - 注入から約3秒で冗長化制御が予備経路へ切替（ただし障害Bで業務は不通のまま）。**画面のパケットが止まり「業務不通」表示**
3. **② 申告して調査を開始** — エージェントが業務テスト→構成照合→GW観測→r1観測→
   層別プローブ→r2 ACL観測、と証拠を積んで両障害を特定
4. **事前検証** — 対象環境を検証環境へ複製・一致判定→修正適用→業務/回帰テスト
5. **承認** — コンソール右カラムの承認カード、または実iPadの
   `http://<MacのIP>:8000/approve`（同一Wi-Fi）。どちらからでも決裁でき、
   サーバの版・ハッシュ・期限照合が二重承認を防ぐ
6. **適用→検証** — 前提再観測(30秒鮮度)→冪等キー付き適用→業務3回連続+禁止遮断維持
7. **SERVICE_RESTORED** — 業務復旧（構成図に緑パケット）。主回線断は残存課題として担当・次作業を記録

画面: `/console`（Mac調査コンソール・一画面）・`/approve`（iPad）・`/ops`（運転席）

リハーサル自動確認: `cd frontend && node scripts/rehearsal.mjs`
（FHD/4K 両解像度で全フェーズを撮影し、横方向のはみ出しを検証。小さい画面では縦スクロール可。要 `npm install`）

回帰テスト一式: `cd backend && uv run python -m unittest test_demo_reset test_topology_documents test_send_gate test_approval -v`（22件）

## シナリオ別の確認状況

「証跡」列は根拠の種類を示す。**自動テスト**＝リポジトリ内のテストで機械的に再現できるもの。
**実測ログ**＝実行結果を文書として残したもの。**手動確認**＝デモ操作で確認したが自動化していないもの。

| 条件 | 結果 | 証跡 |
|---|---|---|
| A+B複合 (T-04) | 二要因を証拠付きで特定→検証→承認→適用→復旧 | 実測ログ: [results.md](docs/evaluation/results.md)（3方式×3試行） |
| 承認なし/ハッシュ不一致/期限切れ/二重承認 (T-06/T-07) | 適用拒否 | 自動テスト: `backend/test_approval.py`（9件） |
| POLICY-* 削除・r2以外への変更 | サーバが拒否（M-18） | 実測ログ: [T-11.md](docs/evidence/T-11.md#攻撃2-api-直叩きによる禁止ルールの削除承認llmを迂回) |
| 構成図PDFへの命令埋め込み (T-11) | 命令を無視し図の内容のみ抽出 | 実測ログ: [T-11.md](docs/evidence/T-11.md) |
| 変更系APIの無認証実行 (M-09/N-02) | 403 | 実測ログ: [T-11.md](docs/evidence/T-11.md#攻撃3-変更系apiの無認証実行m-09n-02) |
| 外部送信不可データのLLM送信 (T-13/T-19) | プロバイダ呼出前に遮断 | 自動テスト: `backend/test_send_gate.py`（4件） |
| 構成図PDFの不正入力（暗号化・ページ超過・スキーマ不一致） | 解析失敗を明示し調査開始を拒否 | 自動テスト: `backend/test_topology_documents.py`（5件） |
| 処理中のリセット・注入・旧案件への承認 | 409 で拒否・履歴は保持 | 自動テスト: `backend/test_demo_reset.py`（4件） |
| 障害なし (T-01) | 業務正常を確認し、変更を提案しない | 手動確認 |
| A単独 (T-02) | 冗長化制御で業務継続。主回線断を残存課題として報告 | 手動確認 |
| B単独 (T-03) | 主回線利用中は業務正常（潜在障害） | 手動確認 |
| 冪等キー再送 | 二重適用なし（同一実行を再生） | 手動確認 |
| LLM障害/キー未設定 (T-10) | golden 再生へフォールバックし、その事実を表示 | 手動確認 |

## セキュリティ

- **変更系APIの認証（M-09/N-02）**: `APPROVAL_TOKEN` を設定すると、承認・障害注入・
  リセットに `X-Netwalker-Token` ヘッダが必須になる（定数時間比較・不一致は403）。
  `demo.sh` が起動ごとにトークンを生成し、案内URLの `?token=` に埋め込む。
  未設定時は開発モードとして認証なしで動く
- **変更操作のホワイトリスト（M-18）**: `sim/ctl.py` の `check_plan` を必ず通る。
  LLM が生成した任意コマンドは実行しない。`POLICY-*` ルールの削除は常に拒否
- **外部送信ゲート（T-13/T-19）**: `data_class` が `external_allowed` 以外のデータは
  プロバイダ呼出**前**に遮断し、違反を `model_run` に監査記録する
- **プロンプトインジェクション対策**: 図中・抽出テキストの命令はデータとして扱う旨を
  システムプロンプトで指示し、出力を JSON Schema に固定した上で、
  **登録機器表との機械照合**を最終ゲートにする（モデルの善良さに依存しない）
- **多層防御（ゲートウェイ＋アプリ）**: OrcaRouter 側のガードレール／ファイアウォールと、
  NetWalker 側の送信ゲート・スキーマ・機械照合・変更ホワイトリスト・人の承認。
  案件ごとに「どの層が何件を通し、どこで止めたか」を画面に件数で出す。
  **ファイアウォールはシャドーモード（監視のみ）**で、実際に操作を止めているのは
  NetWalker 側であることも明記している
- **ガードレール遮断は安全停止**: ゲートウェイが送信内容を遮断した場合、
  異常終了ではなく `NEEDS_HUMAN` で止め、「ゲートウェイが遮断しました（AIには渡っていません）」と表示する
- 共通基準との対応表: [docs/security-owasp.md](docs/security-owasp.md)
  （OWASP Top 10:2025 / Agentic Applications 2026 ASI01–ASI10。**未対応も明記**）
- 攻撃の実測記録: [docs/evidence/T-11.md](docs/evidence/T-11.md)
  / [ゲートウェイ側](docs/evidence/orcarouter-guardrails.md)

### 機微情報の扱い（N-01）

- API キーは `backend/.env`（gitignore 対象）のみ。コード・ログ・画面・推論入力に出さない
- 自己署名証明書はコンテナ内で生成、リポジトリに含まない
- デモデータはすべて合成（実在の顧客情報なし）

## 費用の考え方

費用は**二本立て**で扱う。混ぜると誠実さを失うため、画面でも区別して出す。

- **表示・評価は実請求額**。OrcaRouter の `GET /v1/generation?id=<X-Orca-Request-Id>` が
  返す `total_cost`（USD・確定額）を案件終了時にまとめて引く。推定ではない
- **呼出前の予算判定は単価表**（`route_policy.yaml`）。実費は事後にしか出ないため。
  Named Router や無料枠は単価が公開されないので、**単価不明を0円扱いにして上限が
  無限になる穴**を塞ぐため保守的に上振れ見積りする（`unknown_model_pricing`）
- 上限は2本立て。**案件あたり 0.50 USD**（`per_incident_usd`）と、
  **構成図PDF 1件あたり 0.20 USD**（`per_document_usd`）。PDF解析は案件成立前に発生するため別枠
- 上限に達する前に新規呼出を止める（`BudgetExceeded`）。超過してから気づく作りにしない
- 方式別の実測費用は [docs/evaluation/results.md](docs/evaluation/results.md)

### モデルの選び方（安い＝良い、ではない）

候補モデルは `backend/scripts/bench_models.py` で**実タスク**（判断1ステップと
構成図読取）に通し、合格したものだけを候補列と画面の選択肢に載せている。

実測（2026-09-22）では、**単価が最安のモデルは構造化出力に不合格**だった。
また旧設定の第一候補は構成図の接続を5本中4本しか読めなかった。
結果は [docs/evaluation/models.md](docs/evaluation/models.md)。

画面上部の「AIモデル」から切り替えられる（検証に合格したモデルのみ・
処理中は不可・次の案件から適用・メモリ上書きで永続化しない）。

## 制約・既知の限界

誠実な開示のため、**実装していないもの・自動検証していないもの**を明記する。

- **T-21（再起動後の状態照合）は未実装**。プロセス再起動時に進行中案件を
  外部状態と突き合わせる処理は入れていない（DBの案件は残るが、sim側の実状態との
  再同期は手動リセット前提）
- **CI は未導入**。テストはローカル実行（`python -m unittest`）のみ
- `check_plan`（sim側ホワイトリスト）の単体テストは未整備。実測ログ（T-11.md）で代替
- `plan_hash` は計画本体のみのハッシュで、`incident_id` を含まない。
  案件跨ぎの取り違えは別途 `plan_id` 照合で防いでいる
- OTel は簡易実装（SQLite スパン + 独自タイムライン表示）。Collector 連携は未実装
- DGX Spark ローカルLLM（M-16）は未接続。VLM/判断は OrcaRouter または scripted
- 実機・マルチベンダー機器（W-04）は対象外。netns + nftables による Linux 等価環境
- 冗長化制御は自作の簡易デーモン（BGP/VRRP等の実装ではない）

## 構成図PDFからの調査

コンソールの「デモPDFで試す」、またはPDF選択・ドロップで解析を開始します。
原図と抽出結果を確認し、「登録構成と一致」になったら障害再現・調査へ進めます。
PDF未選択の場合は従来の組み込み構成図を使います。

- デモPDF: `backend/assets/netwalker-demo-topology.pdf`。現行シミュレータの5機器・5接続、主経路と予備経路、インターフェース/IPを記載。障害の答えは記載していません。
- 1〜3ページ・10MB以下の暗号化されていないPDFに対応。各ページを画像化し、OrcaRouterへ画像と抽出テキストを送信します。
- チームのPDF画像化・ページ別抽出の実装（`3231bda`）を参考に、既存gateway・証跡・調査APIへ統合しました。
- 機器だけでなく接続も登録表と照合。不一致・不正応答・途中ページの失敗は明示し、そのPDFでは調査開始できません。登録構成の自動上書きはしません。
- 解析結果を案件の証拠と判断入力に引き継ぎます。リセット後も同じ画面内の選択は保持され、再推論せず利用できます。画面を再読込した場合は再選択してください。
- APIキーはルートまたは`backend/.env`の`ORCAROUTER_API_KEY`（互換名`ORCA_API_KEY`）から読み込みます。キーはレスポンスに含みません。
- PDF再生成: `cd frontend && node scripts/gen-demo-pdf.mjs`（HTML/CSS を Playwright で印刷。
  アプリと同じ配色・フォントで作るのでデザイン言語が統一される）
- 攻撃PDF（プロンプトインジェクション検証用）の生成: `node scripts/gen-demo-pdf.mjs --attack`
- 回帰確認: `cd backend && uv run python -m unittest test_demo_reset test_topology_documents -v`。

> **PDFを作り直したら golden を録り直すこと。** 録画キーが
> `pdf-v1-<sha256>-1` なので、PDFが変わると mock モードで空応答になり解析に失敗する。
> 順序: PDF確定 → 実キーで5機器5接続の一致を確認 → `NW_ROUTE_MODE=record` で再収録 → mock で再確認。

実接続確認（2026-09-22）では、Named Router 経由（`orcarouter/fusion-flash` →
`qwen/qwen3.7-flash`）で5機器・5接続の抽出と登録構成の一致を確認しました
（命令文を埋め込んだ攻撃PDFでも抽出結果は正しいまま — [T-11.md](docs/evidence/T-11.md)）。

なお図の1機器が複数行（機器ID・和名・IPアドレス）で描かれていると、読取結果も
複数行ラベルで返ることがある。登録機器表との照合は**行単位でも突き合わせ、
一意に1台へ収束するときだけ**対応付ける（曖昧なものは確認待ちのまま）。
