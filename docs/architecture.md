# NetWalker アーキテクチャ

「受注画面が開かない」という非専門家の申告から、複合障害の特定・事前検証・
人間の承認・適用・独立検証までを一本の流れで行う。設計上の核は次の3点。

1. **調査は実測のみ** — LLM の推測ではなく、`curl` / `ip` / `nft` の実コマンド出力が証拠
2. **LLM は環境に触れない** — 変更操作はシミュレータ側のホワイトリストを必ず通る
3. **適用には人間の承認** — 計画の版・ハッシュ・期限をサーバが照合する

## 全体構成

```mermaid
flowchart TB
    subgraph host["Mac（ホスト）"]
        subgraph fe["frontend/ — React + Vite（backend が静的配信）"]
            console["/console<br/>調査コンソール（4K一画面）"]
            approve["/approve<br/>iPad 承認端末"]
            ops["/ops<br/>デモ運転席"]
        end

        subgraph be["backend/ — FastAPI :8000（uv / Python 3.12）"]
            api["REST + SSE API<br/>main.py"]
            agent["エージェント<br/>agent.py<br/>scripted決定木 / LLM"]
            tools["ツールベルト<br/>tools.py"]
            approval["承認管理<br/>approval.py<br/>版・ハッシュ・期限照合"]
            gateway["モデルゲートウェイ<br/>llm/gateway.py<br/>送信ゲート・費用上限・golden"]
            vlm["構成図読取<br/>vlm.py / topology_documents.py"]
            store[("SQLite<br/>案件・証拠・計画・<br/>承認・スパン・model_run")]
        end

        subgraph sim["sim/ — Docker privileged コンテナ :9000"]
            direction TB
            ctl["制御API ctl.py"]
            subgraph net["netns × 5 × 2系統（対象 t- / 検証クローン v-）"]
                topo["client — gw — r1(主) / r2(予備) — srv<br/>nginx HTTPS · nftables ACL"]
            end
            failover["冗長化制御デーモン<br/>failover.py（AIと独立・1秒周期）"]
        end
    end

    orca["OrcaRouter<br/>（外部LLM/VLM）"]

    console -->|"REST + SSE"| api
    approve -->|"REST + SSE"| api
    ops -->|"REST + SSE"| api
    api --> agent --> tools
    agent --> vlm
    api --> approval
    agent & vlm --> gateway
    gateway -->|"external_allowed のみ"| orca
    api & agent & approval --> store
    tools -->|"/agent/* のみ"| ctl
    api -->|"/admin/*（デモ運転席）"| ctl
    ctl --- net
    failover --- net
```

## 信頼境界

シミュレータの制御APIは**用途の異なる2系統**に分かれており、これが本作の中心的な
信頼境界になっている。

```mermaid
flowchart LR
    subgraph agentside["エージェントが触れる範囲"]
        A1["/agent/observe_node<br/>/agent/probe_path<br/>/agent/test/business<br/>/agent/test/forbidden"]
        A2["/agent/plan/validate<br/>/agent/plan/apply<br/>/agent/plan/rollback"]
    end
    subgraph adminside["エージェントからは不可視"]
        B1["/admin/inject/fault_a · fault_b<br/>障害注入"]
        B2["/admin/ground_truth<br/>正解（注入状態）"]
        B3["/admin/reset · /admin/pulse<br/>初期化・テレメトリ"]
    end

    A2 --> check{{"check_plan<br/>ホワイトリスト検査"}}
    check -->|"node=r2 / table=fw / chain=forward<br/>かつ comment が POLICY-* でない"| apply["nft ルール削除を実行"]
    check -->|"それ以外"| deny["403 拒否"]

    ops["デモ運転席 /ops"] --> B1 & B3
```

- エージェントは**正解を一切参照できない**。`/admin/ground_truth` はデモの答え合わせ専用
- 変更操作は `sim/ctl.py:295 check_plan` を必ず通る。LLM が生成した任意コマンドは実行しない
- `rule_comment` は `[A-Za-z0-9_\-]{1,64}` に限定（コマンド注入対策）
- 冗長化制御 `failover.py` は AI と独立に動く。切替が起きても AI の手柄にしない
  （画面にも「機器が自動切替（AIの操作ではありません）」と明示する）

## 多層防御（ゲートウェイ層 + アプリ層）

安全性は1枚の壁ではなく、**性質の違う6層**で担保する。外側（OrcaRouter）と
内側（NetWalker）に分かれているので、片方をすり抜けても、もう片方の記録に残る。

```mermaid
flowchart TB
    subgraph gw["外側: ゲートウェイ（OrcaRouter）"]
        G1["① Guardrails（内容）<br/>キーワード・正規表現・PII・意味判定<br/>block / mask / flag"]
        G2["Firewall（行動）<br/>inbound / response / MCP / egress<br/><b>シャドーモード＝監視のみ</b>"]
    end
    subgraph app["内側: NetWalker（実際に遮断するのはここ）"]
        N1["② 送信ゲート<br/>data_class が許可外なら<br/>プロバイダ呼出<b>前</b>に遮断"]
        N2["③ 構造化出力スキーマ<br/>型に合わない応答は採用しない"]
        N3["④ 登録機器表との機械照合<br/>図から読んだ機器名を登録IDへ<br/>対応しなければ確認待ち"]
        N4["⑤ 変更操作のホワイトリスト<br/>check_plan（node/table/chain/comment）"]
        N5["⑥ 人の承認<br/>実差分＋複製環境の実測結果を見て決裁"]
    end

    IN["構成図PDF・観測サマリ"] --> N1 --> G1 --> G2 --> LLM["モデル"]
    LLM --> N2 --> N3 --> PLAN["変更計画"] --> N4 --> N5 --> APPLY["対象環境へ適用"]
```

| 層 | 誰が | 止めるもの | 実装 |
|---|---|---|---|
| ① ガードレール | OrcaRouter | 送信内容（注入・PII・ジェイルブレイク） | OrcaRouter 側の設定 |
| ② 送信ゲート | NetWalker | 外部送信不可のデータ | `backend/app/llm/gateway.py:90` |
| ③ スキーマ | NetWalker | 型に合わない応答 | `GRAPH_SCHEMA` / `DECIDE_SCHEMA` |
| ④ 機械照合 | NetWalker | 図と実態の食い違い | `backend/app/vlm.py` `compare_graph` |
| ⑤ ホワイトリスト | NetWalker | 許可範囲外の変更操作 | `sim/ctl.py:295` `check_plan` |
| ⑥ 人の承認 | 人間 | 人が納得しない変更 | `backend/app/approval.py` |

**正直に書くこと**: OrcaRouter のファイアウォールは**シャドーモード（監視のみ）**で
運用している。評価と記録は本番同様に行うが、遮断系の判定は `audit` に格下げされる。
つまり**実際に操作を止めているのは ④⑤⑥**である。ゲートウェイの記録は
**独立した第二の判定**として、NetWalker の判断と突き合わせるために使う。

案件ごとに「どの層が何件を通し、どこで何件を止めたか」は画面の
「技術詳細 → この案件で通った防御層」で確認できる
（`frontend/src/components/DefenseLayers.tsx`）。
共通基準との対応は [security-owasp.md](security-owasp.md)、
実測記録は [evidence/orcarouter-guardrails.md](evidence/orcarouter-guardrails.md)。

## 調査から復旧までのデータフロー

```mermaid
sequenceDiagram
    autonumber
    actor U as 拠点担当者
    participant C as /console
    participant B as backend
    participant S as sim (/agent/*)
    participant L as OrcaRouter
    actor A as 承認者 (iPad)

    U->>C: 「受注画面が開かない」と申告
    C->>B: POST /api/incidents
    B->>B: 案件作成 RECEIVED → INVESTIGATING

    rect rgb(240, 246, 255)
        note over B,L: 調査ループ（最大10ステップ・費用上限 0.50 USD/案件）
        B->>S: 業務テスト・構成図照合・GW観測・層別プローブ・ACL観測
        S-->>B: 実コマンド出力（証拠として保存）
        B->>L: 観測サマリ → 次の行動（構造化出力・data_class検査）
        L-->>B: 次に実行するツール
    end

    B->>S: POST /agent/plan/validate（検証環境へ複製→一致判定→適用→業務/回帰テスト）
    S-->>B: 事前検証の結果
    B->>B: 計画確定 → 承認依頼（版・ハッシュ・期限 300秒）
    B-->>A: SSE で承認待ちを通知
    A->>B: POST /api/incidents/{id}/approval（操作トークン + 計画ハッシュ）
    B->>B: トークン・版・ハッシュ・期限を照合（不一致は403/422）
    B->>S: 前提再観測（30秒鮮度）→ 冪等キー付きで適用
    B->>S: 業務テスト3回連続 + 禁止通信の遮断維持を確認
    B-->>C: SERVICE_RESTORED（主回線断は残存課題として登録）
```

## 各層の責務

| 層 | 責務 | 主なファイル |
|---|---|---|
| sim | 実通信を伴う擬似ネットワーク。型付きツールAPIと変更ホワイトリスト | `sim/ctl.py` `sim/topo.sh` `sim/failover.py` |
| backend / 状態 | 案件状態機械・証拠・計画・承認・スパンの正本（SQLite） | `app/incident.py` `app/db.py` |
| backend / 判断 | 観測→仮説→計画。scripted 決定木と LLM の2実装 | `app/agent.py` |
| backend / 実行 | ツール呼出と証拠化（生出力をそのまま保存） | `app/tools.py` |
| backend / 承認 | 版・ハッシュ・期限・冪等性の検証 | `app/approval.py` |
| backend / モデル | 候補列・費用上限・送信ゲート・golden再生 | `app/llm/gateway.py` `app/llm/route_policy.yaml` |
| backend / 構成図 | 登録機器表との機械照合（PDFアップロード対応） | `app/vlm.py` `app/topology_documents.py` |
| frontend | 調査の可視化・承認UI・デモ運転 | `src/ConsolePage.tsx` `src/components/Approval.tsx` |

## 状態機械

```mermaid
stateDiagram-v2
    [*] --> RECEIVED: 申告
    RECEIVED --> INVESTIGATING: 調査開始
    INVESTIGATING --> VALIDATING_PLAN: 原因特定・修正案作成
    INVESTIGATING --> NEEDS_HUMAN: 判断不能・費用上限
    VALIDATING_PLAN --> AWAITING_APPROVAL: 事前検証 合格
    VALIDATING_PLAN --> NEEDS_HUMAN: 事前検証 不合格
    AWAITING_APPROVAL --> APPLYING: 承認
    AWAITING_APPROVAL --> NEEDS_HUMAN: 却下・期限切れ
    APPLYING --> VERIFYING: 適用完了
    VERIFYING --> SERVICE_RESTORED: 業務3回連続成功 + 禁止遮断維持
    VERIFYING --> NEEDS_HUMAN: 検証不合格（ロールバック）
    SERVICE_RESTORED --> RESOLVED: 残存課題なし
    SERVICE_RESTORED --> [*]: 残存課題を起票して終了
    NEEDS_HUMAN --> [*]
```

`NEEDS_HUMAN` は失敗ではなく**安全な停止**として扱う。自信がないまま適用に進むより、
人間に判断を戻すほうが正しい、という方針を状態機械に埋め込んでいる。

## モデル呼出の制御

```mermaid
flowchart TB
    entry["gateway.call(data_class, budget_usd)"]
    entry --> gate{{"送信ゲート<br/>data_class == external_allowed?"}}
    gate -->|"いいえ"| violation["SendPolicyViolation<br/>（プロバイダ呼出前に遮断・監査記録）"]
    gate -->|"はい"| budget{{"費用上限<br/>使用済み + 予約額 ≤ 上限?"}}
    budget -->|"超過"| exceeded["BudgetExceeded<br/>（新規呼出を停止）"]
    budget -->|"OK"| mode{{"NW_ROUTE_MODE"}}
    mode -->|"mock"| golden["録画再生（外部通信なし）"]
    mode -->|"live / record"| routes["候補列を順に試行<br/>方式A: gpt-5 固定<br/>方式B: orcarouter/fusion-flash（製品のルーティング）<br/>方式B': 検証済み固定モデルを自前で順に"]
    routes -->|"ガードレール遮断(400)"| guard["GuardrailBlocked<br/>NEEDS_HUMAN で安全停止<br/>（候補を替えて再送しない）"]
    routes -->|"成功"| ok["応答（スキーマ検証）<br/>X-Orca-* からルーティング判断を取得"]
    routes -->|"失敗"| fallback["録画再生へフォールバック<br/>（outcome に記録して画面表示）"]
    ok & golden & fallback --> record["model_run 記録<br/>router・戦略・解決先モデル・トークン・レイテンシ"]
    record --> cost["案件終了時に GET /v1/generation<br/>→ <b>確定請求額</b>を埋める"]
```

キー未設定・API障害でも録画再生でデモが成立する。ただし**フォールバックした事実は
隠さず** `outcome` と画面のルート表示に残す。

### 費用の二本立て（誠実性のため分ける）

| | 何を使うか | なぜ |
|---|---|---|
| **呼出前の予算判定** | `route_policy.yaml` の単価表 × トークン数（推定） | 実費は事後にしか出ないため |
| **表示・評価** | `GET /v1/generation` の `total_cost`（**確定請求額**） | 推定で語らないため |

Named Router や無料枠は単価が公開されない。**単価不明を0円扱いにすると費用上限が
無限になる**ため、予算判定には保守的な上振れ単価（`unknown_model_pricing`）を使う
（`route_policy.py` の `budget_cost_usd`）。

### ルーティング判断の可視化

`orcarouter.py` は `with_raw_response` で `X-Orca-Route` / `X-Orca-Router` /
`X-Orca-Resolved-Model` / `X-Orca-Request-Id` を取得する。
画面の調査ログには判断ごとに
「OrcaRouter が balanced 戦略で ◯◯ を選択（fallback 0）」と1行で流れるので、
**判断ごとに違うモデルが選ばれる様子**がそのまま見える。

候補モデルは `backend/scripts/bench_models.py` で実タスク検証してから採用する
（[evaluation/models.md](evaluation/models.md)）。方式A/B/B'/Rの実測比較は
[evaluation/results.md](evaluation/results.md) を参照。

## 関連ドキュメント

- [審査5項目アピール](judging.md) — 実装証拠・デモでの見せ場・実測値
- [A/B/B'/R 比較実測](evaluation/results.md) — コストパフォーマンスの根拠
- [候補モデルの実タスク検証](evaluation/models.md) — 何を採用し、何を落としたか
- [OWASP 対応表](security-owasp.md) — Top 10:2025 / Agentic ASI01–ASI10
- [T-11 攻撃耐性の検証記録](evidence/T-11.md) — プロンプトインジェクション・API直叩き
- [ゲートウェイ側の記録](evidence/orcarouter-guardrails.md) — ガードレール／ファイアウォール
- [要件定義書](requirements/NetWalker.md) / [UI仕様](design/ui-spec.md) / [デモ台本（4分版）](demo-script.md)
