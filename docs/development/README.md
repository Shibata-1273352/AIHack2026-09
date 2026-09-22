# 開発ガイド

[プロジェクト紹介](../../README.md) / [ドキュメント一覧](../README.md)

まず[起動ガイド](../getting-started/README.md)でデモ環境を用意してください。
この資料では、ソースの入口とテスト・生成・録画の手順をまとめています。

## ソース構成

| 場所 | 役割 |
| --- | --- |
| [backend/app/main.py](../../backend/app/main.py) | FastAPI、案件・承認・構成図のAPI、イベント配信、静的配信 |
| [backend/app/agent.py](../../backend/app/agent.py) | LLMまたは固定手順による調査、修正前検証、適用・復旧確認 |
| [backend/app/topology_documents.py](../../backend/app/topology_documents.py) / [vlm.py](../../backend/app/vlm.py) | PDF画像化、ページ別解析、グラフ統合、登録機器との照合 |
| [backend/app/llm/](../../backend/app/llm/) | OrcaRouter接続、送信制限、モデル選択、費用・予算管理 |
| [backend/app/approval.py](../../backend/app/approval.py) | 計画の版・ハッシュ・期限と承認の照合 |
| [backend/app/tools.py](../../backend/app/tools.py) | 許可した診断・検証・変更操作をシミュレータへ渡す窓口 |
| [frontend/src/](../../frontend/src/) | React / TypeScriptの調査・承認・運転席画面 |
| [sim/](../../sim/) | 対象環境と検証環境のネットワーク、業務サービス、変更操作の制限 |

PDFの画像化とページ別抽出は、チームメンバーの初期実装（コミット`3231bda`）を参考に、既存のモデル呼出・証拠保存・調査APIへ統合しています。
設計全体は[アーキテクチャ](../architecture.md)、目標仕様は[要件定義](../requirements/NetWalker.md)を参照してください。

## フロントエンドのビルド

リポジトリ直下から実行します。

```bash
cd frontend
npm ci
npm run build
```

ビルド結果は`backend/static/`へ出力され、バックエンドから配信されます。
`demo.sh`は成果物が存在する場合には再ビルドしないため、画面のソースを変更したらこの手順を実行してください。
開発サーバーを使う場合は、バックエンドを起動した状態で`npm run dev`を実行します。

## バックエンドの回帰テスト

リポジトリ直下から実行します。既存の6モジュールを明示して実行する例です。

```bash
cd backend
uv sync
uv run python -m unittest test_demo_reset test_topology_documents \
  test_send_gate test_approval test_model_select test_handoff -v
```

承認拒否、外部送信の制限、PDFの不正入力、リセットの競合、モデル切替、引き継ぎを確認します。
実測ログ・手動確認を含む検証範囲は[評価ガイド](../evaluation/README.md)、未検証事項は[制約](../limitations.md)を参照してください。

## 画面のリハーサルと録画

デモサーバーを起動し、`demo.sh`に表示された操作トークンを渡します。
各スクリプトは環境のリセット・障害注入・承認を行うため、ほかの実演と同時に実行しないでください。
実推論モードで動かすとAPI利用料が発生します。

```bash
cd frontend
npm ci
npx playwright install chromium
APPROVAL_TOKEN=<起動時のトークン> node scripts/rehearsal.mjs
APPROVAL_TOKEN=<起動時のトークン> node scripts/record-demo.mjs
```

- `rehearsal.mjs`：FHD / 4Kの各工程を撮影し、横方向のはみ出しと繰り返し実行を確認します。
- `record-demo.mjs`：実UIの通し操作を1920×1080・無音で録画します。出力は`docs/media/netwalker-demo.webm`。ffmpegがあればMP4も生成します。

動画はGitの管理対象外です。公開先が確定したらトップREADMEに視聴リンクを追加してください。
発表の構成は[デモ台本](../demo-script.md)にあります。

## デモPDFの生成

リポジトリ直下から実行します。HTML/CSSをPlaywrightでPDF化します。

```bash
cd frontend
node scripts/gen-demo-pdf.mjs
node scripts/gen-demo-pdf.mjs --attack
```

通常版は現行の5機器・5接続、主経路と予備経路、インターフェース/IPを表します。
`--attack`はプロンプトインジェクションの検証用です。検証結果は[攻撃検証の記録](../evidence/T-11.md)を参照してください。

PDFを変更するとハッシュが変わり、録画応答のキー`pdf-v1-<sha256>-1`も変わります。
PDF確定後は、実キーで抽出結果を確認し、`NW_ROUTE_MODE=record`で再収録した後、`mock`でも確認してください。
構成図の複数行ラベルは、一意の登録機器に対応するときだけ照合し、曖昧なものは確認待ちにします。

## 機微情報と提出物

APIキーを含む`.env`、操作トークン、実行時DB、証明書は公開しないでください。
記事のプレビュー・公開準備は[記事ガイド](../../articles/README.md)にまとめています。
モデル比較の再実行は[評価ガイド](../evaluation/README.md)を参照してください。
