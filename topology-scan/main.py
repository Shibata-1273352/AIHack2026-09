# main.py
# ────────────────────────────────────────────────────────────
# 役割：エージェントのメインループ。
#   1. PDFを読み込む
#   2. トポロジーを解析・JSON化
#   3. ユーザーからの質問に答えるチャットループ
#
# 評価項目への対応：
#   ① セキュリティ   → APIキーは.envで管理、コードに直書きしない
#   ② コスト最適化   → OrcaRouterのauto-routingで安いモデルを自動選択
#   ③ 信頼性・堅牢性 → try/exceptでエラー時もクラッシュしない
#   ④ 自律性        → AIが構成図を自力で理解して質問に答える
#   ⑤ アイデア      → ネットワーク障害へのAI自律診断という独自性
# ────────────────────────────────────────────────────────────

import json
import sys
from pdf_parser import pdf_to_images_and_text
from topology_builder import build_full_topology
from orca_client import call_reasoning


def load_topology(pdf_path: str) -> dict:
    """PDFを読み込んでトポロジーデータを返す"""
    print(f"[起動] {pdf_path} を読み込み中...")

    # PDFを画像＋テキストに変換
    pages = pdf_to_images_and_text(pdf_path)
    print(f"[完了] {len(pages)} ページを読み込みました")

    # AIでトポロジーを抽出・統合
    topology = build_full_topology(pages)
    print(f"[完了] ノード {topology['node_count']} 個、リンク {topology['link_count']} 本を認識")

    return topology


def ask_agent(topology: dict, question: str, history: list[dict]) -> str:
    """
    トポロジー情報をコンテキストに含めて、質問に答える。
    
    history: これまでの会話履歴（[{"role": "user/assistant", "content": "..."}]）
    """
    # トポロジー情報をシステムプロンプトに埋め込む
    # → AIが「このネットワークには何があるか」を常に把握した状態で答えられる
    system_prompt = f"""
あなたはネットワーク構成の専門家AIエージェントです。
以下のネットワークトポロジー情報を完全に把握しています。

=== 認識済みトポロジー ===
{json.dumps(topology, ensure_ascii=False, indent=2)}
=========================

このトポロジーに基づいて、正確に質問に答えてください。
情報が不足している場合は「構成図から確認できません」と正直に答えてください。
障害の場合は原因候補と対処手順を具体的に示してください。
"""

    # 会話履歴 + 新しい質問を組み立て
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)  # 過去の会話を引き継ぐ
    messages.append({"role": "user", "content": question})

    # OrcaRouter経由でAIに問い合わせ（コスト最適モデルを自動選択）
    answer = call_reasoning(messages)

    # 会話履歴を更新（次の質問でも文脈を引き継げるように）
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})

    return answer


def main():
    # コマンドライン引数でPDFパスを受け取る
    # 例: python main.py test_topology.pdf
    if len(sys.argv) < 2:
        print("使い方: python main.py <PDFファイルパス>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    # ── PDFを読み込んでトポロジーを構築 ──
    try:
        topology = load_topology(pdf_path)
    except Exception as e:
        print(f"[エラー] PDFの読み込みに失敗しました: {e}")
        sys.exit(1)

    # デバッグ用：認識したトポロジーを保存
    with open("topology_result.json", "w", encoding="utf-8") as f:
        json.dump(topology, f, ensure_ascii=False, indent=2)
    print("[保存] topology_result.json にトポロジーデータを保存しました")

    # ── 対話ループ ──
    print("\n=== ネットワーク構成エージェント起動 ===")
    print("質問を入力してください（終了: 'exit'）\n")

    history = []  # 会話履歴（文脈維持のため）

    while True:
        try:
            question = input("あなた: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n終了します")
            break

        if question.lower() in ("exit", "quit", "終了"):
            print("終了します")
            break

        if not question:
            continue

        # エラーが起きてもループを止めない（堅牢性）
        try:
            answer = ask_agent(topology, question, history)
            print(f"\nエージェント: {answer}\n")
        except Exception as e:
            print(f"[エラー] 応答生成中にエラーが発生しました: {e}")
            print("次の質問を入力してください\n")


if __name__ == "__main__":
    main()