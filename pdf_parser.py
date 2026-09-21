# pdf_parser.py
# ────────────────────────────────────────────────────────────
# 役割：PDFファイルを読み込み、
#   ① テキストを抽出（ページ番号・座標つき）
#   ② 各ページを高解像度PNGに変換してbase64エンコード
#      → OrcaRouterのvision対応モデルに渡せる形にする
# 正確性のため解像度を高めに設定（dpi=200）
# ────────────────────────────────────────────────────────────

import pymupdf as fitz          # PyMuPDFのインポート名はfitz
import base64
from pathlib import Path


def pdf_to_images_and_text(pdf_path: str) -> list[dict]:
    """
    PDFの各ページを辞書のリストで返す。
    
    戻り値の形:
    [
      {
        "page": 1,
        "text": "ページ内のテキスト全文",
        "image_b64": "base64エンコードされたPNG文字列"
      },
      ...
    ]
    """
    doc = fitz.open(pdf_path)
    pages = []

    for page_num, page in enumerate(doc, start=1):
        # ── テキスト抽出（フォントサイズ・座標つき）──
        # "dict"モードで取るとブロック単位で位置情報も得られる
        text = page.get_text("text")  # シンプルにテキストだけ取る

        # ── 画像化（高DPIで構成図の線やラベルを潰さない）──
        # matrix: 2.5倍 ≒ dpi 180相当。構成図の細かいラベルを読むため高め
        mat = fitz.Matrix(2.5, 2.5)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

        # PNG → bytes → base64文字列に変換
        img_bytes = pix.tobytes("png")
        img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

        pages.append({
            "page": page_num,
            "text": text.strip(),
            "image_b64": img_b64,
        })

    doc.close()
    return pages