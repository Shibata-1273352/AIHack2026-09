# NetWalker ドキュメント

[プロジェクト紹介に戻る](../README.md)

NetWalkerの起動方法、設計、評価と実装の根拠をまとめた入口です。

## 目的から探す

| 目的 | 最初に読む資料 | 続けて読む資料 |
| --- | --- | --- |
| デモを動かす | [環境構築・起動](getting-started/README.md) | [発表用のデモ台本](demo-script.md) |
| 設計を理解する | [アーキテクチャ](architecture.md) | [要件定義](requirements/NetWalker.md)、[UI設計](design/ui-spec.md) |
| 審査の根拠を確認する | [審査5項目との対応](judging.md) | [評価と検証の案内](evaluation/README.md) |
| セキュリティを確認する | [OWASP対応表](security-owasp.md) | [攻撃検証](evidence/T-11.md)、[ゲートウェイ側の記録](evidence/orcarouter-guardrails.md) |
| コードを変更する | [開発ガイド](development/README.md) | [制約と確認状況](limitations.md) |
| 開発の背景・記事を読む | [提出用記事の案内](../articles/README.md) | [本編原稿](../articles/netwalker-aihack2026.md) |

## 資料の読み分け

- **要件定義・UI設計**は目指す仕様です。記載があることだけで実装完了を意味しません。
- **評価結果・証跡**は、記載した条件と日時で確認した結果です。自動テスト・実測ログ・手動確認を区別します。
- **制約と確認状況**には、提出時点で残る未実装・未検証の項目をまとめています。
- **記事原稿**は開発の背景を説明するものです。公開先が確定するまではリポジトリ内の原稿を参照してください。

## ドキュメントの構成

```text
docs/
├── README.md                 この案内
├── getting-started/README.md  環境構築・設定・起動・リセット
├── development/README.md      コード構成・テスト・PDF生成・録画
├── architecture.md           アーキテクチャ・信頼境界・データフロー
├── judging.md                審査5項目と実装・証跡の対応
├── limitations.md            実装範囲と残る制約
├── demo-script.md            発表用のデモ台本
├── security-owasp.md         セキュリティ基準との対応
├── evaluation/               評価の案内・方式比較・モデル検証
├── evidence/                 攻撃検証などの実測記録
├── requirements/             要件定義
└── design/                   UI設計
```
