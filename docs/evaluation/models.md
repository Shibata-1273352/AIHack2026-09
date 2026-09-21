# 候補モデルの実タスク検証

実測日時: 2026-09-22 00:30:42 / policy `netwalker-v2` / 実行: `backend/scripts/bench_models.py`

同一入力で2タスクを実行し、**構造化出力に本当に対応しているか**と
**実請求額**（OrcaRouter `GET /v1/generation` の `total_cost`）を実測した。
単価が安いことは採用理由にならないので、合否は実タスクの結果で決めている。
合格したものだけを `route_policy.yaml` の候補列と画面の選択肢に載せる。

| モデル | decide（判断） | vlm（構成図読取） | 解決されたモデル | 実費 decide | 実費 vlm | 遅延 decide |
|---|---|---|---|---|---|---|
| `orcarouter/auto` | ✅ 構造化出力OK | ❌ スキーマ不適合 (outcome=schema_violation) | `qwen/qwen3.7-plus` | $0.001278<br><small>実請求額</small> | $0.002228<br><small>実請求額</small> | 13640ms |
| `orcarouter/fusion-flash` | ✅ 構造化出力OK | ✅ 機器5・接続5 | `openai/gpt-oss-120b` | $0.000076<br><small>実請求額</small> | $0.000174<br><small>実請求額</small> | 9963ms |
| `orcarouter/fusion-mini` | ✅ 構造化出力OK | ✅ 機器5・接続5 | `openai/gpt-oss-120b` | $0.000410<br><small>実請求額</small> | $0.000174<br><small>実請求額</small> | 39216ms |
| `orcarouter/free` | ❌ RateLimitError(429) | ❌ APIStatusError(402) | `—` | — | — | — |
| `z-ai/glm-5.3-flash` | ❌ スキーマ不適合 (outcome=schema_violation) | ❌ スキーマ不適合 (outcome=schema_violation) | `z-ai/glm-5.3-flash` | $0.000312<br><small>実請求額</small> | $0.000688<br><small>実請求額</small> | 32587ms |
| `z-ai/glm-5.3-flash-free` | ❌ RateLimitError(429) | ❌ RateLimitError(429) | `—` | — | — | — |
| `qwen/qwen3.8-flash` | ✅ 構造化出力OK | ❌ スキーマ不適合 (outcome=schema_violation) | `qwen/qwen3.8-flash` | $0.001040<br><small>実請求額</small> | $0.001258<br><small>実請求額</small> | 37826ms |
| `deepseek/deepseek-v4.1-flash` | ❌ BadRequestError(400) | ✅ 機器5・接続5 | `deepseek/deepseek-v4.1-flash` | — | $0.000868<br><small>実請求額</small> | — |
| `deepseek/deepseek-v4-flash-free` | ❌ RateLimitError(429) | ❌ RateLimitError(429) | `—` | — | — | — |
| `openai/gpt-5.4-nano` | ✅ 構造化出力OK | ✅ 機器5・接続5 | `openai/gpt-5.4-nano` | $0.000406<br><small>実請求額</small> | $0.000582<br><small>実請求額</small> | 2514ms |
| `minimax/minimax-m3` | ❌ スキーマ不適合 (outcome=schema_violation) | ❌ スキーマ不適合 (outcome=schema_violation) | `minimax/minimax-m3` | $0.001246<br><small>実請求額</small> | $0.001190<br><small>実請求額</small> | 9133ms |
| `google/gemini-3.8-flash` | ❌ BadRequestError(400) | ✅ 機器5・接続5 | `google/gemini-3.8-flash` | — | $0.011502<br><small>実請求額</small> | — |
| `tencent/hy3-free` | ❌ RateLimitError(429) | ❌ RateLimitError(429) | `—` | — | — | — |
| `openai/gpt-4o-mini` | ✅ 構造化出力OK | ❌ 機器5・接続4 | `openai/gpt-4o-mini` | $0.000174<br><small>実請求額</small> | $0.005690<br><small>実請求額</small> | 1474ms |
| `openai/gpt-5` | ✅ 構造化出力OK | ✅ 機器5・接続5 | `openai/gpt-5` | $0.015772<br><small>実請求額</small> | $0.037682<br><small>実請求額</small> | 17201ms |

## 判定

- decide（構造化出力）合格: `orcarouter/auto`, `orcarouter/fusion-flash`, `orcarouter/fusion-mini`, `qwen/qwen3.8-flash`, `openai/gpt-5.4-nano`, `openai/gpt-4o-mini`, `openai/gpt-5`
- vlm（vision + 構造化出力）合格: `orcarouter/fusion-flash`, `orcarouter/fusion-mini`, `deepseek/deepseek-v4.1-flash`, `openai/gpt-5.4-nano`, `google/gemini-3.8-flash`, `openai/gpt-5`

不合格のモデルは候補列にも選択UIにも載せない。落ち方は2通りある。

- **400 を返す**（`response_format` 非対応。`deepseek-v4.1-flash` / `gemini-3.8-flash` の decide）…
  400 は再試行不可なので、候補に入れると調査がその場で落ちる
- **200 を返すがスキーマに適合しない**（`z-ai/glm-5.3-flash` / `minimax-m3` など）…
  応答は課金されるのに採用できない。単価が安くても無駄払いになる

どちらも「単価表だけ見ていては分からない」ので、実タスクで確かめる必要がある。

## この実測から採用を決めたこと

| 判断 | 根拠 |
|---|---|
| **decide の第一候補を `orcarouter/fusion-flash` に** | 合格したなかで**最安**（$0.000076）。しかも判断と構成図読取で**別のモデルに解決される**（`gpt-oss-120b` / `qwen3.7-flash`）＝モデル選択の価値がそのまま見える |
| **vlm の第一候補も `orcarouter/fusion-flash` に** | 旧設定の第一候補 `gpt-4o-mini` は**接続を5本中4本しか読めなかった**。しかも実費は33倍（$0.005690 対 $0.000174） |
| **最安の `z-ai/glm-5.3-flash` は採用しない** | 単価は最安だが decide / vlm とも構造化出力に不合格。**安い＝良い、ではない** |
| **`orcarouter/auto` は decide のみ選択可に** | 構成図読取だけ不合格だったため（画面の選択肢では `vision: false` として扱う） |
| **無料枠は採用しない** | `orcarouter/free` / `*-free` はいずれも 429（レート制限）または 402 で完走できず。「実質0円で復旧まで到達」は**今回の実測では言えない** |
| フォールバックは `openai/gpt-5.4-nano` | 合格モデル中**最速**（decide 2.5s）。Named Router が落ちたときの受け皿 |
