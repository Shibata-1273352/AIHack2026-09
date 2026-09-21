"""画面に出す平易な日本語（表示層）と、技術表記（技術層）の対応表。

NetWalker の画面はそのままプレゼンになる。決勝は4分発表で審査員に非エンジニアが
含まれるため、**見出しに技術用語を出さない**。技術名は消さず、`tech_*` フィールドや
技術詳細モーダルへ寄せる（二層テキスト）。

ここにはロジックを置かない。辞書と、辞書を引くだけの関数のみ。
LLM への入力（tools.py の evidence summary）はこのモジュールを通さない。
文言を変えると推論の入力が変わり、golden と A/B/R 実測が無効化するため。
"""

from __future__ import annotations

#: LLM が選ぶ行動（DECIDE_SCHEMA の action）→ 画面に出す平易な一文。
PLAIN_ACTIONS: dict[str, str] = {
    "observe_node": "機器の状態を確認します",
    "probe_path": "通信できるか経路を試験します",
    "test_business": "業務通信が使えるか実測します",
    "test_forbidden": "止めるべき通信が止まったままか確認します",
    "propose_fix": "修正案をまとめます",
    "conclude_no_change": "変更は不要と判断します",
}

#: 機器ID → 画面に出す日本語名（構成図・調査ログで共通）。
PLAIN_NODES: dict[str, str] = {
    "client": "業務端末",
    "gw": "拠点ルータ",
    "r1": "主回線ルータ",
    "r2": "予備回線ルータ",
    "srv": "受注サーバ",
}

#: 観測の側面（aspects）→ 平易な言い換え。
PLAIN_ASPECTS: dict[str, str] = {
    "link": "回線の接続",
    "route": "通信の行き先",
    "addr": "住所（アドレス）",
    "nft": "通信ルール",
    "listen": "待ち受け中のサービス",
    "failover": "自動切替の状態",
}


def plain_action(action: str) -> str:
    """LLM が選んだ行動の平易な言い換え。未知の行動はそのまま返す。"""
    return PLAIN_ACTIONS.get(action, action)


def plain_node(node: str) -> str:
    return PLAIN_NODES.get(node, node)


def plain_aspects(aspects: list[str]) -> str:
    return "・".join(PLAIN_ASPECTS.get(a, a) for a in aspects)


def plain_observe(node: str, aspects: list[str]) -> str:
    """observe_node の平易な見出し（例: 「予備回線ルータの通信ルールを確認します」）。"""
    if not aspects:
        return f"{plain_node(node)}の状態を確認します"
    return f"{plain_node(node)}の{plain_aspects(aspects)}を確認します"
