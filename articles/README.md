# 提出用記事

[プロジェクト紹介](../README.md) / [ドキュメント一覧](../docs/README.md)

NetWalkerの課題、開発内容、設計上の判断を説明するZenn形式の記事原稿です。
公開済み記事へのリンクではなく、リポジトリ内の原稿へのリンクを掲載しています。

| 原稿 | 内容 |
| --- | --- |
| [本編](netwalker-aihack2026.md) | 課題・作ったもの・デモ・実測結果・開発の経緯 |
| [アーキテクチャ編](netwalker-architecture.md) | 構成、調査と変更の制御、検証、モデル呼出 |
| [セキュリティ編](netwalker-security.md) | 攻撃検証、防御の実装、対応範囲と制約 |

## プレビュー

リポジトリ直下で実行します。

```bash
npx zenn-cli@latest preview
```

## 公開前の確認

1. 記事内の`ZENN_USERNAME`を公開先のユーザー名、`GITHUB_OWNER/GITHUB_REPO`を`Shibata-1273352/AIHack2026-09`へ置き換える。
2. 記事間リンク、画像、評価数値と根拠資料の整合性を確認する。
3. 公開する記事だけ、先頭の`published: false`を`published: true`へ変更する。
4. 公開後にこのページへ公開URLを記載し、トップREADMEからも案内する。

APIキー・操作トークンが記事や画像に含まれていないことを確認してください。
評価結果は[評価資料](../docs/evaluation/README.md)、実装範囲は[制約と確認状況](../docs/limitations.md)を参照します。
