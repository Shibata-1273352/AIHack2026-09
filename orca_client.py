# orca_client.py
# ────────────────────────────────────────────────────────────
# 役割：OrcaRouterのAPIに接続する共通クライアントを作る。
#
# OrcaRouterはOpenAI互換のAPIゲートウェイ。
# base_urlをapi.orcarouter.ai/v1に変えるだけで
# 200以上のモデルを自動ルーティングしてくれる。
#
# ポイント：
#   - model="orcarouter/auto" → OrcaRouterがタスクに最適なモデルを自動選択
#   - モデルを明示したいときは "anthropic/claude-opus-5" などと指定できる
#   - 正確性が重要なタスク（構成図の読み取り）は高品質モデルに固定するのがベスト
# ────────────────────────────────────────────────────────────

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # .envファイルからAPIキーを読み込む

# OrcaRouterのエンドポイントを向いたOpenAIクライアント
# base_urlをここで切り替えているだけで、あとはOpenAI SDKと同じ使い方
client = OpenAI(
    base_url="https://api.orcarouter.ai/v1",
    api_key=os.getenv("ORCA_API_KEY"),
)

# ── 正確性重視のモデル設定 ──
# 構成図の読み取りはvision対応かつ高精度モデルが必要。
# コスト重視なら "orcarouter/auto" に戻すと自動最適化される。
VISION_MODEL = "anthropic/claude-opus-5"   # 画像読み取り（高精度）
REASONING_MODEL = "orcarouter/auto"         # 障害分析（コスト最適）


def call_vision(messages: list[dict], max_tokens: int = 4096) -> str:
    """
    画像つきのメッセージをvision対応モデルに送る。
    構成図の読み取りに使う。
    """
    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def call_reasoning(messages: list[dict], max_tokens: int = 2048) -> str:
    """
    テキストのみのメッセージをルーティング付きモデルに送る。
    障害分析や回答生成に使う。
    OrcaRouterが自動でコスト最適なモデルを選ぶ。
    """
    response = client.chat.completions.create(
        model=REASONING_MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content