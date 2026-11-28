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
    ("01_ppt_text/IMG_5597.jpeg", "PPT 幕布 · 文字"),
    ("02_ppt_formula/IMG_5541.jpg", "PPT 幕布 · 公式"),
    ("03_paper_text/IMG_20261125_232543.jpg", "A4 纸质 · 文字"),
    ("04_paper_formula/formula_05.jpg", "A4 纸质 · 公式"),
]
RECTIFY_SAMPLE = "01_ppt_text/IMG_5597.jpeg"

# 数据集总览固定抽样：每类 6 张，均已人工核对不含人脸与可识别个人信息。
OVERVIEW_PICKS = {
    "ppt_text": [
        "01_ppt_text/IMG_5515.jpg",
        "01_ppt_text/IMG_5594.jpg",
        "01_ppt_text/IMG_5597.jpeg",
        "01_ppt_text/IMG_5599.JPG",
        "01_ppt_text/IMG_5605.jpeg",
        "01_ppt_text/IMG_5613.jpg",
    ],
    "ppt_formula": [
        "02_ppt_formula/IMG_5527.jpg",
        "02_ppt_formula/IMG_5541.jpg",
        "02_ppt_formula/IMG_5559.jpg",
        "02_ppt_formula/IMG_5588.jpg",
        "02_ppt_formula/IMG_5603.jpg",
        "02_ppt_formula/IMG_6207.jpeg",
    ],
    "paper_text": [
        "03_paper_text/text_07.jpg",
        "03_paper_text/text_08.jpg",
        "03_paper_text/text_11.jpg",
        "03_paper_text/IMG_20261125_233317.jpg",
        "03_paper_text/IMG_20261125_232543.jpg",
        "03_paper_text/IMG20261126022607.jpg",
    ],
    "paper_formula": [
        "04_paper_formula/IMG_20261125_232906.jpg",
        "04_paper_formula/formula_02.jpg",
        "04_paper_formula/formula_05.jpg",
        "04_paper_formula/formula_09.jpg",
        "04_paper_formula/formula_13.jpg",
        "04_paper_formula/formula_page_05.jpg",
    ],
}


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
    """数据总览缩略图：每类固定选取 6 张，共 24 张（均无个人信息）。"""
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
    by_file = {r["file"]: r for r in rows}
    picked = []
    for label in ("ppt_text", "ppt_formula", "paper_text", "paper_formula"):
        picked.extend(by_file[path] for path in OVERVIEW_PICKS[label])
    cols, tw, th, gap = 6, 340, 260, 6
    thumbs = []
    for row in picked:
        loaded = load_image(ROOT / "data/raw_samples" / row["file"], max_long_edge=340)
        thumb = to_pil(loaded.image, long_edge=340)
        thumb.thumbnail((tw - 8, th - 8), Image.LANCZOS)
        thumbs.append(thumb)
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

    loaded = load_image(ROOT / "data/raw_samples" / RECTIFY_SAMPLE, max_long_edge=1600)
    original = services._limit_long_edge(loaded.image, 2000)
    rectified, _quad, status = services._apply_rectify(original, "ppt")
    assert status == "ok", f"rectify failed: {status}"
    scan = services._apply_scan(rectified)
    from PIL import ImageOps

    def fit_box(image, width, height):
        canvas = Image.new("RGB", (width, height), "white")
        copy = image.copy()
        copy.thumbnail((width - 8, height - 8), Image.LANCZOS)
        canvas.paste(copy, ((width - copy.width) // 2, (height - copy.height) // 2))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, 0, width - 1, height - 1], outline="#cccccc")
        return canvas

    cell_w, cell_h = 1100, 820
    top = [
        fit_box(to_pil(original, long_edge=1100), cell_w, cell_h),
        fit_box(to_pil(rectified, long_edge=1100), cell_w, cell_h),
    ]
    scan_src = to_pil(scan, long_edge=2000)
    scan_h = int(round(scan_src.height * (cell_w * 2 + 10) / scan_src.width))
    scan_img = fit_box(scan_src, cell_w * 2 + 10, scan_h)
    font = load_font(32)
    gap, label_h = 10, 40
    width = cell_w * 2 + gap
    height = label_h + cell_h + gap + label_h + scan_h
    canvas = Image.new("RGB", (width, height), "#fbfbf8")
    draw = ImageDraw.Draw(canvas)
    for index, (image, label) in enumerate(zip(top, ["原图（正面 PPT）", "OpenCV 拉正（Canny 50/150）"])):
        x = index * (cell_w + gap)
        draw.text((x + 6, 4), label, fill="#1f3a5f", font=font)
        canvas.paste(image, (x, label_h))
    y2 = label_h + cell_h + gap
    draw.text((6, y2), "扫描件（自适应二值化）", fill="#1f3a5f", font=font)
    canvas.paste(scan_img, (0, y2 + label_h))
    canvas.save(OUT / "rectify_scan_ppt.png", quality=92)
    print("saved rectify_scan_ppt.png", canvas.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
