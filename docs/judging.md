# 審査5項目 — 実装証拠と実測値

大会資料の5項目（セキュリティ / コストパフォーマンス / 信頼性・堅牢性 / 自律性 /
アイデア・独創性、各0〜10点）に対し、**コードの位置・デモでの見せ場・実測値**を対応付ける。
要件定義書 §13.1 の証拠設計を提出物の形にしたもの。

数値はすべて実測。推定値・目標値は含めない。

---

## 1. セキュリティ

**主張**: 権限を限定し、承認された差分だけを適用する。**攻撃して効くことを確認済み**。

| 防御 | 実装 | 検証 |
|---|---|---|
| 変更操作のホワイトリスト（M-18） | `sim/ctl.py:295 check_plan` | `POLICY-*` 削除 → 403（検証・適用とも） |
| 変更系APIの認証（M-09/N-02） | `backend/app/main.py:35 require_token` | トークン無し・不一致 → 403、正 → 200 |
| 外部送信ゲート（T-13/T-19） | `backend/app/llm/gateway.py:28,89` | `test_send_gate.py` 4本（mock/record/live 全モードで遮断） |
| 承認ゲート（T-06/T-07） | `backend/app/approval.py:47 decide` | `test_approval.py` 9本 |
| プロンプトインジェクション対策 | `backend/app/vlm.py:67` + `GRAPH_SCHEMA` + `vlm.py:145 compare_graph` | 攻撃PDF → 命令無視・正しい抽出 |
| パストラバーサル対策 | `backend/app/main.py:323` | `../` `%2e%2e` `..%2f` → 404 |
| 機微情報（N-01） | `backend/app/config.py` の `SecretStr` | キーはレスポンス・ログ・推論入力に出さない |
| ガードレール遮断の安全停止 | `backend/app/llm/orcarouter.py` `GuardrailBlocked` | 遮断を異常終了にせず `NEEDS_HUMAN` で止め、画面に防御動作として表示 |
| 依存の固定（サプライチェーン） | `backend/uv.lock` をコミット | OWASP A03 |

**共通基準との対応表**: [security-owasp.md](security-owasp.md)
（**OWASP Top 10:2025** と **OWASP Top 10 for Agentic Applications 2026（ASI01–ASI10）**。
実装の file:line・証拠・**正直な未対応**を並べている）

とくに **ASI09 Human-Agent Trust Exploitation**（AIの自信ありげな要約で人間に危険な承認を
させる）に対しては、承認画面で**実際に流す差分そのもの**と**複製環境での変更前後の実測結果**を
見せてから承認させる、という直球の答えを実装済み。

**多層防御**: 外側（OrcaRouter のガードレール／ファイアウォール）と
内側（NetWalker の送信ゲート・スキーマ・機械照合・変更ホワイトリスト・人の承認）の
6層。案件ごとに「どこで何件を止めたか」を画面に件数で出す。
**ファイアウォールはシャドーモード（監視のみ）**で、実際に操作を止めているのは
NetWalker 側である旨も画面と資料に明記している
（[evidence/orcarouter-guardrails.md](evidence/orcarouter-guardrails.md)）。

**実測**: 4通りの攻撃を実行し記録 → [evidence/T-11.md](evidence/T-11.md)

```
構成図PDFへの命令埋め込み  → 命令無視・5機器5接続を正しく抽出（comparison ok）
API直叩きで POLICY 削除    → 403（validate / apply とも）
無認証で承認・注入・リセット → 403
静的配信のパストラバーサル  → 404
```

**デモでの見せ場**: 攻撃PDFをその場でアップロードし、抽出結果が命令に従わないことを見せる。
続けて「モデルが従わなかったこと」ではなく、**登録機器表との機械照合が最後のゲート**である
ことを説明する（モデルの善良さに依存しない設計）。

**補足**: いちばん効いている防御は、LLM が何を出力しても環境に触れないこと。
修正操作は `check_plan` を必ず通り、対象は r2 の nft ルール1件削除に限定される。

---

## 2. コストパフォーマンス

**主張**: モデル選択の効果を、同一条件の実測で示す。

**実測**: T-04複合障害 × 3方式 × 3試行 = 9試行すべて成功 → [evaluation/results.md](evaluation/results.md)

| 方式 | 成功 | 平均所要 | 平均LLM呼出 | 平均費用 | 成功1件あたり |
|---|---|---|---|---|---|
| A 高性能モデル固定（gpt-5） | 3/3 | 124.7s | 5.3 | $0.0597 | $0.0597 |
| **B 段階別選択（既定）** | 3/3 | **72.4s** | 12.0 | **$0.0146** | **$0.0146** |
| R 固定ランブック | 3/3 | 32.2s | 1.0 | $0.0057 | $0.0057 |

**いちばん言いたいこと**: A（gpt-5固定）は判断回数が少ない（5.3 対 12呼出）のに、
**費用は B の4.1倍、所要時間は1.7倍**。高性能モデルの「手数の少なさ」は単価と遅延を
埋め合わせなかった。トークン総量は逆に A のほうが少ない（12,196 対 93,155）ため、
**単価差が支配的**という結論になる。

R は最安だが、想定済みの障害しか扱えない（判断が決定木に固定）。
3方式を並べて初めて「なぜ段階別選択か」が実測で言える。

| 仕組み | 実装 |
|---|---|
| 候補列を設定で宣言（モデル名を直書きしない、M-17） | `backend/app/llm/route_policy.yaml` |
| 方式切替 | `NW_ROUTE_VARIANT=a\|b` → `route_policy.py:63` |
| 費用の算出 | 単価表 × 実トークン（原価が返らないため）。単価不明は 0 と偽らず非加算 |
| 費用上限（N-04） | 案件 0.50 USD / 構成図PDF 0.20 USD の**2本立て**。上限到達**前**に呼出停止 |
| 再現手順 | `cd backend && uv run python scripts/eval_abr.py --trials 3` |

**デモでの見せ場**: 技術詳細の「AI呼出の明細」に、判断ごとの解決先モデル・
ルーティング戦略・**実請求額**が並ぶ。「いま何円使ったか」が画面で分かる。
画面上部からモデルを切り替えられ、案件に「どのモデルをなぜ使ったか」が記録される。

### OrcaReplay（製品側の記録・再生エンジン）の位置づけ

要件 §512 は「**OrcaReplay には依存せず**、自前ハーネスから方式を選択できること」を
必須としている。そのため比較実測の正本は `backend/scripts/eval_abr.py` と
`backend/golden/` に置いた。

**今回のビルドでは OrcaReplay を使用していない**（未評価）。役割が
`backend/golden/`（録画・再生）と重なるため、導入するなら置き換えではなく
上乗せ（`orca compare last --models a,b,c` によるモデル横断比較を補助として併用）に
なるが、実測していないことを実測したように書かないため、ここでは位置づけの記述に留める。

---

## 3. 信頼性・堅牢性

**主張**: 失敗・不明・復元不能を正しく扱い、**分からないときに止まれる**。

| 仕組み | 実装 | 検証 |
|---|---|---|
| `NEEDS_HUMAN` は失敗でなく安全な停止 | `backend/app/incident.py` の状態機械 | 判断上限・費用上限・検証不合格・却下で遷移 |
| 事前検証（検証環境へ複製→一致判定→適用→業務/回帰テスト） | `sim/ctl.py:457 plan_validate` | 不合格なら承認依頼を出さない |
| 適用直前の前提再観測（30秒鮮度） | `backend/app/agent.py:560` | 観測が古ければ適用しない |
| 冪等キー付き適用 | `backend/app/tools.py:116 apply_plan` | 連打しても適用は一回 |
| 業務復旧の判定は3回連続成功 | `sim/ctl.py:235-252` | 1回の成功で「直った」と言わない |
| 禁止通信の遮断維持を確認 | `test_forbidden` | 直す過程で別の穴を開けていないか |
| API障害・キー未設定 | `gateway.py` の golden フォールバック | mock モードで**外部通信なし・$0 で完走**を確認 |
| 処理中のリセット・旧案件承認 | `backend/app/runtime.py` | `test_demo_reset.py` 4本（409で拒否） |
| 却下で行き止まりにしない（M-12 / §14.3） | `agent.open_handoff` / `main.py` の `/handoff` `/reinvestigate` | 却下→引き継ぎ起票→受領・保留を記録、または障害を入れ直さず調べ直し |
| 費用上限が単価非公開モデルで無限にならない | `route_policy.py` `budget_cost_usd` | Named Router・無料枠でも保守的に見積って上限が効く |
| 構成図の読取が表記ゆれで壊れない | `vlm.py` `_map_label` | 複数行ラベルでも行単位で照合し、曖昧なら確認待ちのまま |

**実測**:
- 自動テスト **38本** green（`test_approval` 9 / `test_model_select` 8 /
  `test_handoff` 8 / `test_topology_documents` 5 / `test_demo_reset` 4 /
  `test_send_gate` 4）
- A/B/R **9試行すべて SERVICE_RESTORED**、NEEDS_HUMAN率 0%
- golden 再生のみ（`NW_ROUTE_MODE=mock`）で llm デモが完走。12呼出すべて記録応答・費用$0

**正直に開示する限界**（README「制約・既知の限界」と同一）:
T-21（再起動後の状態照合）未実装 / CI 未導入 / `check_plan` の単体テストは未整備で
実測ログで代替 / `plan_hash` に `incident_id` を含まない。

**デモでの見せ場**: 復旧後に「主回線の断線は直していない」と**残存課題として起票**して終わる。
全部直ったと言わないことが、この項目の中身そのもの。

---

## 4. 自律性

**主張**: 固定手順を持たず、観測結果に応じて次の調査が変わる。

| 仕組み | 実装 |
|---|---|
| 観測履歴 → 次の行動を構造化出力で決定 | `backend/app/agent.py:389`（`DECIDE_SCHEMA`） |
| 行動の選択肢は型で限定 | observe_node / probe_path / test_business / test_forbidden / propose_fix / conclude_no_change |
| 判断ステップ上限 10（N-04） | `backend/app/agent.py:387` |
| 仮説の生成・証拠紐付け・決着 | `add_hypothesis` / `update_hypothesis`（`agent.py:35,45`） |
| LLM出力の裏取り | 提案ルールの実在を観測で確認してから計画化（`agent.py:467-476`） |
| 成功の捏造防止 | `conclude_no_change` はサーバ側で業務テストを再実行して検証（`agent.py:440`） |

**実測**（[evaluation/results.md](evaluation/results.md) の試行内訳）:
- 同じ複合障害でも**モデルによって手数が変わる**: gpt-5 は4〜6呼出、gpt-4o-mini は12呼出。
  どちらも同じ結論（r2 の `BAD-ACL-443` 削除）に到達し、9試行すべて復旧まで完走した
- 判断が LLM でも決定木でも、確定した計画は同一（scripted と llm で
  `plan_hash = 5cb08eb5880c1c9d` が一致）。**経路は変わるが結論は揺れない**
- ツール実行回数も方式で異なる（A 13.3回 / B 27回 / R 15回）＝**手順が固定でない証拠**

**デモでの見せ場**: **調査ログが積み上がる**ので、
「業務通信を実測 → 構成図を照合 → 拠点ルータ → 主回線の断線 → 予備回線を層別に確認 →
原因発見」という推論の流れがそのまま読める。
手順書を読み上げているのではなく、**観測した結果に応じて次の手が変わっている**ことが
画面で確認できる。単独障害と複合障害では辿る経路が実際に変わる。

各行には「その判断にどのモデルがなぜ選ばれたか」も1行で出るので、
**判断ごとにモデルが選び直されている**様子まで見える。

---

## 5. アイデア・独創性

**主張**: 構成図を起点に、たらい回しから業務再開までを一案件で進める。

**原体験**: 「受注画面が開かない」→ 情シス「回線は生きています」→
回線事業者「弊社設備は正常です」。**誰も嘘をついていないのに復旧しない**。
デモの複合障害（A: 主回線断で予備へ自動切替 / B: 予備経路のACL誤設定）は、
この状況を最小構成で再現したもの。切替は正常に動いているので両者の回答は正しい。

| 独自性 | 実装 |
|---|---|
| 手元の構成図PDFから入れる | `backend/app/topology_documents.py`（1〜3頁・10MB・暗号化拒否） |
| 図を鵜呑みにせず登録機器表と機械照合 | `vlm.py:145 compare_graph`（機器だけでなく**接続**も照合） |
| 非専門家の言葉が入口 | 「受注画面が開かない」から開始 |
| 承認は実機iPadで | `/approve`（同一Wi-Fi）。コンソール内パネルとサーバ側で二重承認を防止 |
| 業務目線の復旧判定 | ping疎通でなく**受注画面が3回連続で開くこと** |
| 根拠付きの引き継ぎ | 残存課題を担当候補つきで起票。**却下も行き止まりにしない**（却下理由・証拠・却下した計画を引き継ぎレコードに残し、受領／保留を記録） |
| 「AIが動く前」を隠さない | 障害注入直後に**装置が自力で切り替えた履歴**を実データで表示。「AIではありません」と明示したうえで「それでも業務は止まったまま」につなぐ |
| 非専門家に伝わる画面 | 見出しは平易な日本語、技術名は `<small>` と技術詳細モーダルへ。4分発表で読み解きに時間を使わせない |

**実測**: 実キーの gpt-4o-mini で、PDFから5機器・5接続を抽出し登録構成と全件一致
（`comparison.ok = true`）。攻撃PDFでも抽出は正しいまま。

**デモでの見せ場**: 構成図PDFをドラッグ&ドロップ → 原図と抽出結果を並べて表示 →
「登録構成と一致」を確認してから調査開始。資料はあるが現状と合っているか分からない、
という実際によくある状態から始められる。

---

## 再現手順（審査員が手元で確認する場合）

```bash
./demo.sh                      # sim + backend 起動（トークン付きURLを表示）
cd backend

# 自動テスト 38本
uv run python -m unittest test_demo_reset test_topology_documents test_send_gate \
                          test_approval test_model_select test_handoff -v

# A/B/B'/R 比較の再実測（要APIキー。--variants R なら安価）
uv run python scripts/eval_abr.py --trials 2 --conditions T04,C0,C1

# 候補モデルの実タスク検証（何を採用し、何を落としたか）
uv run python scripts/bench_models.py

# 攻撃PDFの生成（T-11の再現）
cd ../frontend && node scripts/gen-demo-pdf.mjs --attack
```

外部通信なしで動かす場合は `NW_ROUTE_MODE=mock`（録画再生・費用0）。

## 関連

- [アーキテクチャ](architecture.md) — 構成図・信頼境界・多層防御・データフロー
- [OWASP 対応表](security-owasp.md) — Top 10:2025 / Agentic ASI01–ASI10
- [A/B/B'/R 比較実測](evaluation/results.md) / [生データ](evaluation/results.json)
- [候補モデルの実タスク検証](evaluation/models.md)
- [T-11 攻撃耐性の検証記録](evidence/T-11.md) /
  [ゲートウェイ側の記録](evidence/orcarouter-guardrails.md)
- [デモ台本（4分版）](demo-script.md)
- [要件定義書 §13.1](requirements/NetWalker.md)
