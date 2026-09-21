# topology_builder.py
# ────────────────────────────────────────────────────────────
# 役割：構成図の画像をAIに渡して、
#   「どのノードがどのノードと接続しているか」
#   「インターフェース名・IPは何か」
# をJSON構造で返させる。
#
# 仕組み：
#   1. PDFから取った画像(base64)をvisionモデルに渡す
#   2. システムプロンプトで「JSON形式で返せ」と指示
#   3. 返ってきたJSONをPythonのdictに変換
#   4. 全ページを統合してトポロジー全体図を組み立てる
# ────────────────────────────────────────────────────────────

import json
import re
from orca_client import call_vision


# AIへの指示（システムプロンプト）
# 詳しく書くほど抽出精度が上がる
TOPOLOGY_EXTRACTION_PROMPT = """
あなたはネットワーク構成図を解析するエキスパートです。
提供された画像からネットワークトポロジー情報を抽出し、
必ず以下のJSON形式のみで返してください。
余計な説明文やマークダウンの```は絶対に含めないこと。

{
  "nodes": [
    {
      "id": "ノードの識別子（例: HQ-CORE-R1）",
      "type": "router|switch|server|pc|cloud|firewall",
      "label": "ラベル名",
      "location": "HQ|BR1|INTERNET など",
      "interfaces": [
        {"name": "Gi0/1", "ip": "10.0.0.1/30 または不明なら null"}
      ]
    }
  ],
  "links": [
    {
      "from_node": "ノードID",
      "from_interface": "インターフェース名",
      "to_node": "ノードID",
      "to_interface": "インターフェース名",
      "link_type": "ethernet|gre_tunnel|serial|fiber"
    }
  ],
  "special": {
    "tunnels": ["GREトンネルなど特殊接続の説明"],
    "segments": ["ネットワークセグメントの説明"]
  }
}
"""


def extract_topology_from_page(page_data: dict) -> dict:
    """
    1ページ分の画像データからトポロジーを抽出する。
    
    page_data: pdf_parser.py の pdf_to_images_and_text() の1要素
    """
    # visionモデルへのメッセージを組み立て
    # OpenAI形式のvisionメッセージ（image_url に base64を埋め込む）
    messages = [
        {
            "role": "system",
            "content": TOPOLOGY_EXTRACTION_PROMPT
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"この構成図を解析してください。\n"
                        f"ページ内のテキスト情報：\n{page_data['text']}\n\n"
                        f"上記テキストも参考にしながら、画像からトポロジーを抽出してください。"
                    )
                },
                {
                    "type": "image_url",
                    "image_url": {
                        # base64画像をdata URIとして渡す
                        "url": f"data:image/png;base64,{page_data['image_b64']}",
                        "detail": "high"  # 高解像度モードで読み取る（正確性重視）
                    }
                }
            ]
        }
    ]

    # AIに問い合わせ
    raw_response = call_vision(messages)

    # JSONのみ取り出す（AIが余分なテキストを返した場合の保険）
    json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
    if not json_match:
        # JSONが見つからない場合はエラー情報を返す（クラッシュさせない）
        print(f"[警告] ページ {page_data['page']}: JSONを抽出できませんでした")
        return {"nodes": [], "links": [], "special": {}, "error": raw_response}

    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError as e:
        print(f"[警告] ページ {page_data['page']}: JSONパースエラー: {e}")
        return {"nodes": [], "links": [], "special": {}, "error": str(e)}


def build_full_topology(pages: list[dict]) -> dict:
    """
    全ページのトポロジーを統合して1つのデータ構造にまとめる。
    複数ページにまたがる構成図でも対応できる。
    """
    all_nodes = {}   # IDで重複排除するためdictで管理
    all_links = []
    all_special = {"tunnels": [], "segments": []}

    for page_data in pages:
        print(f"[解析中] ページ {page_data['page']} を処理中...")
        topo = extract_topology_from_page(page_data)

        # ノードを統合（同じIDのものは上書きしない）
        for node in topo.get("nodes", []):
            node_id = node.get("id", "unknown")
            if node_id not in all_nodes:
                all_nodes[node_id] = node

        # リンクを追加（重複チェックは簡易的に）
        for link in topo.get("links", []):
            all_links.append(link)

        # 特殊情報を統合
        special = topo.get("special", {})
        all_special["tunnels"].extend(special.get("tunnels", []))
        all_special["segments"].extend(special.get("segments", []))

    return {
        "nodes": list(all_nodes.values()),
        "links": all_links,
        "special": all_special,
        "node_count": len(all_nodes),
        "link_count": len(all_links),
    }