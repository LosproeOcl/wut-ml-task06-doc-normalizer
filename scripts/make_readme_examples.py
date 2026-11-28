"""生成 README 用的“原图 → OpenCV 拉正 → 扫描件”效果图（PPT 与纸质各一组）。

在容器内运行：
    docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app/src:/app \
      docnorm:cpu-arm64 python scripts/make_readme_examples.py
输出：docs/assets/readme_ppt_effect.png、docs/assets/readme_paper_effect.png
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/assets"
OUT.mkdir(parents=True, exist_ok=True)

FONT = "/app/.tmp_font.ttf"
if not Path(FONT).is_file():
    FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def to_pil(array: np.ndarray, edge: int = 900) -> Image.Image:
    height, width = array.shape[:2]
    scale = min(1.0, edge / max(height, width))
    if scale < 1.0:
        array = cv2.resize(array, (int(width * scale), int(height * scale)))
    return Image.fromarray(cv2.cvtColor(array, cv2.COLOR_BGR2RGB))


def fit_box(image: Image.Image, width: int, height: int) -> Image.Image:
    canvas = Image.new("RGB", (width, height), "white")
    copy = image.copy()
    copy.thumbnail((width - 8, height - 8), Image.LANCZOS)
    canvas.paste(copy, ((width - copy.width) // 2, (height - copy.height) // 2))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, width - 1, height - 1], outline="#cccccc")
    return canvas


def build(rows, out_name: str, cell_w: int, cell_h: int, title: str) -> None:
    font = ImageFont.truetype(FONT, 24)
    label_h = 26
    row_title_h = 30
    width = cell_w * 3 + 40
    row_h = row_title_h + label_h + cell_h
    height = 50 + len(rows) * row_h
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill="#1f3a5f", font=font)
    for r, (sample, panels) in enumerate(rows):
        y = 50 + r * row_h
        draw.text((10, y), sample, fill="#1f3a5f", font=font)
        for c, (label, image) in enumerate(panels):
            x = 10 + c * cell_w
            draw.text((x + 4, y + row_title_h), label, fill="#333333", font=font)
            canvas.paste(fit_box(image, cell_w - 20, cell_h - 6), (x, y + row_title_h + label_h))
    canvas.save(OUT / out_name, quality=92)
    print("saved", out_name, canvas.size)


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from docnorm.data.loader import load_image
    from web import services

    def process(rel: str):
        loaded = load_image(ROOT / "data/raw_samples" / rel, max_long_edge=1400)
        original = services._limit_long_edge(loaded.image, 1600)
        carrier = "ppt" if rel.startswith(("01_", "02_")) else "paper"
        rectified, _quad, status = services._apply_rectify(original, carrier)
        assert status == "ok", f"{rel}: {status}"
        scan = services._apply_scan(rectified)
        return [
            ("原图", to_pil(original, 1000)),
            ("OpenCV 拉正", to_pil(rectified, 1000)),
            ("扫描件", to_pil(scan, 1000)),
        ]

    ppt_rows = [
        ("PPT 文字 IMG_5597", process("01_ppt_text/IMG_5597.jpeg")),
        ("PPT 公式 IMG_5541", process("02_ppt_formula/IMG_5541.jpg")),
    ]
    paper_rows = [
        ("纸质文字 text_07", process("03_paper_text/text_07.jpg")),
        ("纸质公式 formula_05", process("04_paper_formula/formula_05.jpg")),
    ]
    build(ppt_rows, "readme_ppt_effect.png", 620, 470, "投影幕布样例：原图 → OpenCV 拉正 → 扫描件")
    build(paper_rows, "readme_paper_effect.png", 560, 640, "纸质/板书样例：原图 → OpenCV 拉正 → 扫描件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
