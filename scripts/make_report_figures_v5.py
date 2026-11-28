"""生成提交报告所需的代表性图组：四类样本与“原图 / OpenCV 拉正 / 扫描件”并排。

在容器内运行（挂载系统字体以绘制中文标签）：
    docker run --rm -v "$PWD:/app" -v /System/Library/Fonts:/fonts:ro \
      -w /app -e PYTHONPATH=/app/src:/app docnorm:cpu-arm64 \
      python scripts/make_report_figures_v5.py

输出写入 reports/developer_report_assets/：
- dataset_examples.png   2×2：PPT 文字 / PPT 公式 / A4 纸文字 / A4 纸公式
- rectify_scan_ppt.png   正面 PPT 的原图 / OpenCV 拉正（Canny 50/150）/ 扫描件
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/developer_report_assets"
OUT.mkdir(parents=True, exist_ok=True)

FONT_CANDIDATES = (
    "/app/.tmp_font.ttf",
    "reports/developer_report_assets/.tmp_font.ttf",
    "/fonts/STHeiti Medium.ttc",
    "/fonts/Hiragino Sans GB.ttc",
    "/fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
)

SAMPLES = [
    ("01_ppt_text/IMG_6233.jpg", "PPT 幕布 · 文字"),
    ("02_ppt_formula/IMG_6209.jpeg", "PPT 幕布 · 公式"),
    ("03_paper_text/IMG_20261125_232543.jpg", "A4 纸质 · 文字"),
    ("04_paper_formula/formula_05.jpg", "A4 纸质 · 公式"),
]
RECTIFY_SAMPLE = "01_ppt_text/IMG_6233.jpg"


def load_font(size: int = 34):
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def to_pil(array: np.ndarray, long_edge: int = 760) -> Image.Image:
    height, width = array.shape[:2]
    scale = long_edge / max(height, width)
    if scale < 1.0:
        array = cv2.resize(array, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    return Image.fromarray(cv2.cvtColor(array, cv2.COLOR_BGR2RGB))


def compose(panels, labels, columns: int, out: Path, label_height: int = 46) -> None:
    font = load_font()
    widths = [panel.width for panel in panels]
    heights = [panel.height for panel in panels]
    cell_w = max(widths)
    cell_h = max(heights)
    rows = (len(panels) + columns - 1) // columns
    canvas = Image.new(
        "RGB",
        (columns * cell_w + (columns + 1) * 12, rows * (cell_h + label_height) + (rows + 1) * 12),
        "#fbfbf8",
    )
    draw = ImageDraw.Draw(canvas)
    for index, (panel, label) in enumerate(zip(panels, labels)):
        row, col = divmod(index, columns)
        x = 12 + col * (cell_w + 12)
        y = 12 + row * (cell_h + label_height + 12)
        canvas.paste(panel, (x + (cell_w - panel.width) // 2, y + (cell_h - panel.height) // 2))
        text_box = draw.textbbox((0, 0), label, font=font)
        text_w = text_box[2] - text_box[0]
        draw.text((x + (cell_w - text_w) // 2, y + cell_h + 8), label, fill="#1f3a5f", font=font)
    canvas.save(out, quality=92)
    print(f"saved {out.name} size={canvas.size}")


def fig_overview() -> None:
    """数据总览缩略图：每类抽样 6 张，共 24 张（随机种子 42）。"""
    import random

    import sys

    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))
    from docnorm.data.loader import load_image

    excluded = {r["sample_id"] for r in _read_csv(ROOT / "data/manifests/exclusions.csv")}
    rows = [
        r
        for r in _read_csv(ROOT / "data/manifests/sample_manifest_v5.csv")
        if r["sample_id"] not in excluded and r["label"] in {
            "ppt_text", "ppt_formula", "paper_text", "paper_formula"
        }
    ]
    rng = random.Random(42)
    picked = []
    for label in ("ppt_text", "ppt_formula", "paper_text", "paper_formula"):
        pool = [r for r in rows if r["label"] == label]
        picked.extend(rng.sample(pool, min(6, len(pool))))
    thumbs = []
    for row in picked:
        loaded = load_image(ROOT / "data/raw_samples" / row["file"], max_long_edge=340)
        thumbs.append(to_pil(loaded.image, long_edge=340))
    cols, tw, th, gap = 6, 340, 260, 6
    canvas = Image.new(
        "RGB",
        (cols * tw + (cols + 1) * gap, 4 * th + 5 * gap),
        "#fbfbf8",
    )
    for index, thumb in enumerate(thumbs):
        row, col = divmod(index, cols)
        x = gap + col * (tw + gap)
        y = gap + row * (th + gap)
        canvas.paste(thumb, (x + (tw - thumb.width) // 2, y + (th - thumb.height) // 2))
    canvas.save(OUT / "dataset_overview.png", quality=90)
    print(f"saved dataset_overview.png size={canvas.size}")


def _read_csv(path: Path):
    import csv

    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))
    from docnorm.data.loader import load_image
    from web import services

    fig_overview()
    panels, labels = [], []
    for rel, label in SAMPLES:
        loaded = load_image(ROOT / "data/raw_samples" / rel, max_long_edge=900)
        panels.append(to_pil(loaded.image))
        labels.append(label)
    compose(panels, labels, columns=2, out=OUT / "dataset_examples.png")

    loaded = load_image(ROOT / "data/raw_samples" / RECTIFY_SAMPLE, max_long_edge=900)
    original = services._limit_long_edge(loaded.image, 900)
    rectified, _quad, status = services._apply_rectify(original, "ppt")
    assert status == "ok", f"rectify failed: {status}"
    scan = services._apply_scan(rectified)
    panels = [to_pil(original), to_pil(rectified), to_pil(scan)]
    labels = ["原图（正面 PPT）", "OpenCV 拉正（Canny 50/150）", "扫描件（自适应二值化）"]
    compose(panels, labels, columns=3, out=OUT / "rectify_scan_ppt.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
