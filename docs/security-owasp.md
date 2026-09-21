# OWASP 対応表（Top 10:2025 / Agentic Applications 2026）

NetWalker のセキュリティ設計を、審査員が照合できる共通基準に紐付ける。
**実装（file:line）・証拠・正直な未対応**を並べる。「できていないこと」を隠すと、
できていることの信頼も落ちる。

対象は2つ。

- **OWASP Top 10:2025**（Web アプリケーション一般）
- **OWASP Top 10 for Agentic Applications 2026（ASI01–ASI10）** — 本作がまさに
  該当する新基準。エージェント特有のリスクを扱う

Agentic のほうは、**ゲートウェイ層（OrcaRouter）とアプリ層（NetWalker）の二層**で書く。
片方だけでは守れないし、二層あることが本作の防御の形だからである。

> **前提の明示**: OrcaRouter 側の **ファイアウォールはシャドーモード（監視のみ）** で
> 運用している。本番同様に評価・記録するが、遮断系の判定は `audit` に格下げされる。
> つまり**実際に操作を遮断しているのは NetWalker 側**（`check_plan` のホワイトリストと
> 承認ゲート）である。ゲートウェイの記録は、同じツール呼出に対する
> **独立した第二の判定**として突き合わせに使う。

---

## 1. OWASP Top 10:2025

| # | カテゴリ | NetWalker の対応 | 実装 | 正直な限界 |
|---|---|---|---|---|
| **A01** | Broken Access Control | 変更系API（承認・障害注入・リセット・モデル選択・引き継ぎ・再調査）は共有トークンを定数時間比較。エージェントは `/agent/*` しか呼べず `/admin/*` へ到達できない | `backend/app/main.py:35` `require_token` / `backend/app/tools.py:32` / `sim/ctl.py` の経路分離 | 共有トークンのみ。利用者ごとの認可は無い（A07 参照） |
| **A02** | Security Misconfiguration | SPA 配信のパストラバーサル対策、CORS は localhost のみ、APIキーは `SecretStr` で画面・ログ・推論入力へ出さない | `backend/app/main.py:322` `is_relative_to` / `main.py:28` CORS / `backend/app/config.py:23` | デモ用に `--host 0.0.0.0` で待ち受ける（同一Wi-Fi前提） |
| **A03** | Software Supply Chain Failures | `uv.lock` をコミットして依存を固定（本改修で対応）。シミュレータは Debian slim のピン留めイメージ | `backend/uv.lock` / `sim/Dockerfile` | npm 側は `package-lock.json` のみ。SBOM・署名検証は未実施 |
| **A04** | Cryptographic Failures | 業務テストは自己署名ではなく**配布した CA で検証した実TLS**（`--cacert`）。キーはリポジトリに入れない | `sim/ctl.py:605` の `--cacert` / `.gitignore` の `*.key` `*.pem` | デモ用の証明書であり公開CAではない |
| **A05** | Injection | LLM が生成した文字列をコマンドとして実行しない。操作は型付きアダプタのみで、`subprocess.run` は**リスト引数**（シェルを経由しない） | `sim/ctl.py:50` `sh()` / `sim/ctl.py:295` `check_plan` / `backend/app/agent.py` の DECIDE_SCHEMA | — |
| **A06** | Insecure Design | 「調べる」と「変える」を分離し、変更は必ず ①複製環境での事前検証 ②人の承認 ③適用直前の前提再観測 を通す | `backend/app/agent.py` `_compose_and_validate_plan` / `_apply_and_verify` | — |
| **A07** | Authentication Failures | 操作トークンで変更系を保護。承認は計画の版・ハッシュ・期限・承認者をサーバ側で照合 | `backend/app/approval.py:47` `decide` | **未対応を明示**: 利用者認証が無い（共有トークンのみ）。誰が承認したかは自己申告の氏名で、本人確認はしていない |
| **A08** | Software or Data Integrity Failures | 承認対象は計画のハッシュで同定し、古い画面からの承認を拒否。適用は冪等キーで二重実行を防ぐ。適用前ルールセット全文を保存して復元できる | `backend/app/approval.py:55` / `sim/ctl.py:502` `plan_apply` | — |
| **A09** | Security Logging and Alerting Failures | 全ツール呼出を証拠として保存、状態遷移・AI呼出・承認を実行記録（スパン）として残す。送信ゲート違反・ガードレール遮断も監査記録に残る | `backend/app/tools.py:40` `_evidence` / `backend/app/otel.py` / `backend/app/llm/gateway.py:_record_run` | **未対応を明示**: 記録はあるが**通知が無い**。異常を人へ push する経路は未実装 |
| **A10** | Mishandling of Exceptional Conditions | 想定外は「止まる」方向へ倒す。事前検証不合格・前提変化・上限到達・ガードレール遮断はいずれも `NEEDS_HUMAN` で安全停止し、適用後の検証不合格では登録済みの復元を実行する | `backend/app/agent.py` の各 `NEEDS_HUMAN` 遷移 / `_final_verify` のロールバック / `gateway.py` の golden フォールバック | — |

### A10 について（2025年の新カテゴリ）

本作の設計思想が正面から答える項目なので補足する。NetWalker は
**「分からない」「前提が変わった」を成功に偽装しない**。

- 事前検証で複製が本番と一致しなければ、承認待ちへ進まない（`clone_mismatch`）
- 適用直前に対象ルールが消えていたら、古い計画を適用せず停止する（T-20）
- 判断10ステップ・読取20回・案件費用の上限に達したら、決められた手順へ退避するか停止する
- LLM 応答がスキーマに適合しなければ採用しない
- `conclude_no_change`（変更不要）と AI が言っても、サーバ側で業務テストを実行して裏を取る
  （`backend/app/agent.py` の `conclude_no_change` 分岐）

---

## 2. OWASP Top 10 for Agentic Applications 2026（ASI01–ASI10）

| # | 項目 | ゲートウェイ層（OrcaRouter） | アプリ層（NetWalker） |
|---|---|---|---|
| **ASI01** | Agent Goal Hijack | 入力ガードレール（キーワード・正規表現・PII・LLMによる意味判定）。ヒットは Matches フィードに全件記録。**入力段の遮断は課金されない** | 構成図PDF内のテキストを**データとして扱う**旨をシステムプロンプトで明示し、抽出結果は登録機器表と機械照合する。攻撃PDFでの実測記録: [T-11.md](evidence/T-11.md) / ゲートウェイ側の記録: [orcarouter-guardrails.md](evidence/orcarouter-guardrails.md) |
| **ASI02** | Tool Misuse | Firewall の response/MCP 面で、モデルが出したツール呼出を評価・記録（**シャドーモード＝監視のみ**） | **実際の遮断はここ**。`sim/ctl.py:295` `check_plan` が `node=r2` / `table=fw` / `chain=forward` のルール削除だけを許可し、`POLICY-*` の削除・`flush`・policy 変更を拒否する |
| **ASI03** | Identity & Privilege Abuse | APIキー単位の利用枠と記録 | 変更対象を予備回線ルータの1ルールに限定。読取は登録済みノード・宛先ホワイトリストのみ（`sim/ctl.py:38` `PROBE_DSTS`） |
| **ASI04** | Resource Overload | ルータ側のレート制限 | 判断10ステップ・読取20回・案件費用上限。**単価非公開のモデルでも上限が効くよう保守的に見積る**（`route_policy.py` `budget_cost_usd`） |
| **ASI05** | Unexpected Code Execution (RCE) | — | LLM が生成したコマンドを実行しない。型付きアダプタ経由のみで、シェルを介さない（`sim/ctl.py:50`） |
| **ASI06** | Memory & Context Poisoning | 入力ガードレールが注入文面を検知・記録 | 図から読んだ情報は「実測で裏付けるまで確定扱いにしない」。仮説は証拠IDに紐付き、AIが提案したルールは**実在確認してから**計画に載せる（`agent.py` の rule_line 存在確認） |
| **ASI07** | Insecure Agent Communication（外部送信） | egress 評価（監視） | **送信ゲート**: `data_class` が `external_allowed` 以外はプロバイダ呼出**前に**遮断し、違反を監査記録に残す（`backend/app/llm/gateway.py:90`）。許可リスト方式なので未知の値も遮断（`test_send_gate.py`） |
| **ASI08** | Cascading Failures | フォールバック段数の記録（`X-Orca-Fallback-Level`） | 失敗は連鎖させず停止させる。検証不合格→復元→`NEEDS_HUMAN`。LLM不通時は決められた手順へ退避し、その事実を画面に残す |
| **ASI09** | **Human-Agent Trust Exploitation** | 出力ガードレール（監視） | **本作の直球の答え**。AIの自信ありげな要約で承認させない。承認画面には ①**実際に流す差分そのもの**（1行） ②複製環境での**変更前後の実測結果** ③影響 ④復元方法 ⑤計画ハッシュ を出し、「承認した1件以外は何も変更されません」と明示する（`frontend/src/components/Approval.tsx` / `CloneCheck.tsx`） |
| **ASI10** | Rogue Agents | cap-cost による上限 | 判断10ステップ上限・案件費用上限・読取20回上限。人の承認なしには一切変更しない。却下しても行き止まりにせず、引き継ぎレコードを起票して次へ渡す（M-12 / §14.3） |

### ASI09 をもう少し詳しく

エージェントの最大の危険は「もっともらしい要約を見せて、人間に危険な承認をさせる」ことである。
NetWalker はここを**要約で説得しない**設計にしている。

1. 承認カードの主役は要約文ではなく、**実際に流す変更の差分**である
2. その差分は、**本番と同一であることを機械照合した複製環境**で先に適用済みで、
   変更前（業務NG / 禁止通信は遮断）と変更後（業務OK / 禁止通信は遮断のまま）の
   実測結果を並べて出す
3. 承認は計画のハッシュに紐付く。「人間が特定のハッシュの計画を承認した」ことが記録に残る
4. 却下は失敗ではなく**正常な安全動作**として扱い、「ネットワークには何も変更していません」を
   最初に明示したうえで、次に進む道（調べ直す／引き継ぐ）を出す

---

## 3. 二層で見ることの意味

同じツール呼出に対して、**ゲートウェイの記録**と**NetWalker の判断**を突き合わせられる。
片方がすり抜けても、もう片方の記録に残る。

画面の「技術詳細 → この案件で通った防御層」で、①ガードレール ②送信ゲート
③構造化出力スキーマ ④登録機器表との照合 ⑤変更ホワイトリスト ⑥人の承認 の
それぞれが何件を通し、どこで何件を止めたかを件数で確認できる
（`frontend/src/components/DefenseLayers.tsx`）。

関連文書: [architecture.md](architecture.md) / [judging.md](judging.md) /
[T-11.md](evidence/T-11.md) / [orcarouter-guardrails.md](evidence/orcarouter-guardrails.md)
