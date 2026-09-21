"""構成図PNGを生成する（VLM読取のライブ入力 兼 UI表示用）。

管理者が描いた拠点構成図という設定。手描き風ではなくクリーンな業務図。
実行: uv run python scripts/gen_diagram.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "assets" / "topology-diagram.png"

FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Osaka.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


W, H = 1200, 680
BG = (250, 250, 252)
INK = (27, 36, 48)
BLUE = (31, 95, 191)
GRAY = (120, 130, 145)
ZONE = (238, 242, 248)


def box(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
        title: str, sub: str, accent=BLUE) -> tuple[int, int]:
    d.rounded_rectangle([x, y, x + w, y + h], radius=12,
                        fill=(255, 255, 255), outline=accent, width=3)
    f1, f2 = font(26), font(18)
    tw = d.textlength(title, font=f1)
    d.text((x + (w - tw) / 2, y + h / 2 - 30), title, font=f1, fill=INK)
    sw = d.textlength(sub, font=f2)
    d.text((x + (w - sw) / 2, y + h / 2 + 6), sub, font=f2, fill=GRAY)
    return (x + w // 2, y + h // 2)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_zone, f_label, f_head = font(22), font(18), font(30)

    d.text((40, 24), "拠点A ネットワーク構成図（管理番号 NW-A-102）",
           font=f_head, fill=INK)
    d.text((40, 64), "版: 2026-09-20 / 作成: 情報システム部", font=f_label, fill=GRAY)

    # ゾーン背景
    d.rounded_rectangle([40, 110, 400, 640], radius=16, fill=ZONE)
    d.text((60, 124), "拠点A", font=f_zone, fill=GRAY)
    d.rounded_rectangle([430, 110, 790, 640], radius=16, fill=ZONE)
    d.text((450, 124), "WAN", font=f_zone, fill=GRAY)
    d.rounded_rectangle([820, 110, 1160, 640], radius=16, fill=ZONE)
    d.text((840, 124), "データセンター", font=f_zone, fill=GRAY)

    # ノード
    c_client = box(d, 80, 200, 280, 110, "業務端末", "10.0.1.10")
    c_gw = box(d, 80, 430, 280, 110, "拠点GW", "10.0.1.1")
    c_r1 = box(d, 470, 200, 280, 110, "経路ノード r1", "主回線")
    c_r2 = box(d, 470, 430, 280, 110, "経路ノード r2", "予備回線")
    c_srv = box(d, 860, 315, 280, 110, "受注サービス", "order.example.com (10.0.100.10)")

    def edge(a, b, label="", dashed=False, color=INK):
        if dashed:
            # 手動の破線
            import math
            x1, y1 = a
            x2, y2 = b
            dist = math.hypot(x2 - x1, y2 - y1)
            steps = int(dist // 14)
            for i in range(0, steps, 2):
                t0, t1 = i / steps, min((i + 1) / steps, 1)
                d.line([x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0,
                        x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1],
                       fill=color, width=4)
        else:
            d.line([*a, *b], fill=color, width=4)
        if label:
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            tw = d.textlength(label, font=f_label)
            d.rectangle([mx - tw / 2 - 6, my - 14, mx + tw / 2 + 6, my + 14],
                        fill=BG)
            d.text((mx - tw / 2, my - 11), label, font=f_label, fill=BLUE)

    edge(c_client, c_gw, "LAN")
    edge(c_gw, c_r1, "主回線")
    edge(c_gw, c_r2, "予備回線", dashed=True)
    edge(c_r1, c_srv, "")
    edge(c_r2, c_srv, "", dashed=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
