# 提出記事（§14.2）

記事の本体は **`articles/`** にある（Zenn CLI 準拠。`published: false` のまま）。
以前この場所に置いていた下書きは、内容と実測値が二重管理になるため
`articles/` へ統合した。**数値の正本は `articles/` と
[evaluation/results.md](evaluation/results.md)** である。

| ファイル | 役割 |
|---|---|
| [`articles/netwalker-aihack2026.md`](../articles/netwalker-aihack2026.md) | **本編**（提出用）。課題・デモ・実測・画面を作り直した話・見つけたバグ・限界 |
| [`articles/netwalker-architecture.md`](../articles/netwalker-architecture.md) | アーキテクチャ編。LLMに環境を触らせない設計、複製環境での事前検証、モデル呼出の制御 |
| [`articles/netwalker-security.md`](../articles/netwalker-security.md) | セキュリティ編。実際に攻撃した記録、OWASP Agentic ASI01–ASI10 と Top 10:2025 の対応 |

本編からアーキテクチャ編・セキュリティ編へリンクする構成にしている。

## 公開手順

```bash
# 記事間リンクとリポジトリURLのプレースホルダを置換する
sed -i '' 's/ZENN_USERNAME/<あなたのZennユーザー名>/g; s|GITHUB_OWNER/GITHUB_REPO|<owner>/<repo>|g' articles/*.md

npx zenn-cli@latest preview          # リポジトリ直下で確認
# 内容を確認してから各記事の published: true にする
```

画像は Zenn の規約どおり `images/` に置いている
（`images/netwalker-topology.png` は刷新したデモPDFから書き出したもの）。

## 関連

- [デモ台本（4分版）](demo-script.md) — 発表の時間配分と質疑の想定問答
- [審査5項目アピール](judging.md) — 実装証拠と実測値の索引
- [A/B/B'/R 比較実測](evaluation/results.md) / [候補モデルの実タスク検証](evaluation/models.md)
