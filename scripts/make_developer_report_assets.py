"""生成开发历程报告所需图表（数据样本、标注示例、架构、指标、混淆矩阵）。"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from matplotlib.font_manager import FontProperties
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/developer_report_assets"
OUT.mkdir(parents=True, exist_ok=True)

CJK = FontProperties(fname="/System/Library/Fonts/STHeiti Medium.ttc")
CJK_BOLD = FontProperties(fname="/System/Library/Fonts/STHeiti Medium.ttc")
PIL_FONT = "/System/Library/Fonts/STHeiti Medium.ttc"


def contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail(size, Image.LANCZOS)
    return image


def dataset_examples() -> None:
    items = [
        ("PPT 文字", ROOT / "data/raw_samples/01_ppt_text/IMG_5597.jpeg", "4032×3024"),
        ("PPT 公式", ROOT / "data/raw_samples/02_ppt_formula/IMG_5596.jpeg", "4032×3024"),
        (
            "纸质文字（含人工四角）",
            ROOT / "reports/annotation_examples/10_522530a208.jpg",
            "",
        ),
        (
            "板书公式（含人工四角）",
            ROOT / "reports/annotation_examples/23_8ba8df668b.jpg",
            "",
        ),
    ]
    tile_w, tile_h = 620, 470
    canvas = Image.new("RGB", (tile_w * 2, tile_h * 2), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(PIL_FONT, 26)
    small = ImageFont.truetype(PIL_FONT, 19)
    for index, (label, path, resolution) in enumerate(items):
        with Image.open(path) as raw:
            image = contain(raw, (tile_w - 30, tile_h - 80))
        x = (index % 2) * tile_w
        y = (index // 2) * tile_h
        canvas.paste(image, (x + (tile_w - image.width) // 2, y + 58))
        draw.text((x + 18, y + 14), label, fill=(20, 20, 20), font=font)
        if resolution:
            draw.text(
                (x + tile_w - 160, y + 18),
                resolution,
                fill=(110, 110, 110),
                font=small,
            )
        draw.rectangle(
            [x + 2, y + 2, x + tile_w - 3, y + tile_h - 3], outline=(210, 210, 210), width=2
        )
    canvas.save(OUT / "dataset_examples.png", quality=92)


def annotation_examples() -> None:
    files = [
        ("板书文字：整块黑板", "00_05160fce8d.jpg"),
        ("纸质公式：单页", "10_522530a208.jpg"),
        ("板书公式：面板", "23_8ba8df668b.jpg"),
    ]
    tile_w, tile_h = 520, 500
    canvas = Image.new("RGB", (tile_w * 3, tile_h), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(PIL_FONT, 24)
    for index, (label, name) in enumerate(files):
        with Image.open(ROOT / "reports/annotation_examples" / name) as raw:
            image = contain(raw, (tile_w - 20, tile_h - 55))
        x = index * tile_w
        canvas.paste(image, (x + (tile_w - image.width) // 2, 45))
        draw.text((x + 12, 10), label, fill=(20, 20, 20), font=font)
        draw.rectangle([x + 1, 1, x + tile_w - 2, tile_h - 2], outline=(210, 210, 210), width=2)
    canvas.save(OUT / "annotation_examples.png", quality=92)


def box(ax, xy, width, height, text, face, edge="#4a5a6a", size=11):
    rect = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.35,rounding_size=1.2",
        linewidth=1.3,
        edgecolor=edge,
        facecolor=face,
    )
    ax.add_patch(rect)
    ax.text(
        xy[0] + width / 2,
        xy[1] + height / 2,
        text,
        ha="center",
        va="center",
        fontproperties=CJK,
        fontsize=size,
        color="#17202a",
    )


def arrow(ax, start, end, style="-|>", dashed=False, color="#52616b"):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle=style,
        mutation_scale=12,
        linewidth=1.3,
        color=color,
        linestyle="--" if dashed else "-",
    )
    ax.add_patch(patch)


def architecture() -> None:
    fig, ax = plt.subplots(figsize=(11, 7.2))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    blue = "#dce8f7"
    green = "#dff0e2"
    orange = "#fde8cf"
    gray = "#ececec"
    purple = "#e8e0f5"

    box(ax, (2, 84), 20, 10, "上传图像\nEXIF 转正 · 长边 2000", blue, size=13)
    box(
        ax,
        (27, 84),
        40,
        10,
        "载体门控 · MobileNetV3-Small 160\nTTA ±12° · 阈值 0.3",
        green,
        size=13,
    )

    box(ax, (4, 62), 25, 9, "分类拉正（OpenCV）\nPPT 90/250", orange, size=13)
    box(ax, (34, 62), 26, 9, "PPT 分类\nMobileNetV3-Small 224", blue, size=12)
    box(ax, (67, 62), 28, 9, "文字 / 公式\n概率 + 置信度", green, size=13)

    box(ax, (4, 45), 25, 9, "分类拉正（OpenCV）\n纸质 50/150", orange, size=13)
    box(ax, (34, 45), 26, 9, "纸质分类\n3×MobileNetV3 集成", blue, size=12)
    box(ax, (67, 45), 28, 9, "文字 / 公式\n概率 + 置信度", green, size=13)

    box(ax, (34, 29), 26, 8, "传统 SVM 兜底\n模型缺失时回退", gray, size=12)

    box(ax, (4, 11), 25, 9, "学习四角\nquad-ppt-02 / quad-paper-01", purple, size=12)
    box(ax, (34, 11), 26, 9, "显示 / 导出拉正\n扫描件 + PDF", orange, size=13)
    box(ax, (67, 11), 28, 9, "矫正图 / 扫描件 / PDF\n可切换 OpenCV 视图", green, size=12)

    arrow(ax, (22, 89), (27, 89))

    ax.plot([47, 47, 16], [84, 78, 78], color="#52616b", linewidth=1.4)
    ax.plot([16, 16], [78, 54], color="#52616b", linewidth=1.4)
    arrow(ax, (16, 78), (16, 71))
    arrow(ax, (16, 62), (16, 54))
    ax.text(18, 75, "PPT", fontproperties=CJK, fontsize=12, color="#3354aa")
    ax.text(18, 58, "纸质", fontproperties=CJK, fontsize=12, color="#2f7d32")

    arrow(ax, (29, 66.5), (34, 66.5))
    arrow(ax, (60, 66.5), (67, 66.5))
    arrow(ax, (29, 49.5), (34, 49.5))
    arrow(ax, (60, 49.5), (67, 49.5))

    ax.plot([64, 64.5], [84, 78], color="#52616b", linewidth=1.3, linestyle="--")
    ax.plot([64.5, 64.5], [78, 33], color="#52616b", linewidth=1.3, linestyle="--")
    arrow(ax, (64.5, 33), (60, 33), dashed=True)

    ax.plot([2.5, 2.5], [84, 15.5], color="#52616b", linewidth=1.3, linestyle="--")
    arrow(ax, (2.5, 15.5), (4, 15.5), dashed=True)
    ax.text(3.8, 48, "显示路径", fontproperties=CJK, fontsize=11, color="#6b4fa0", rotation=90)

    arrow(ax, (29, 15.5), (34, 15.5))
    arrow(ax, (60, 15.5), (67, 15.5))

    ax.text(
        50,
        2.5,
        "分类与显示解耦：分类器只看 OpenCV 拉正视图；学习四角只服务显示/PDF。",
        ha="center",
        fontproperties=CJK,
        fontsize=11,
        color="#43505c",
    )
    fig.tight_layout()
    fig.savefig(OUT / "architecture.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def metrics_chart() -> None:
    labels = [
        "传统 SVM",
        "MobileNetV3 单模型",
        "路由（旧标签）",
        "路由（旧模型/修正标签）",
        "当前路由",
        "PPT 分支",
        "纸质分支",
    ]
    values = [76.47, 80.39, 88.24, 84.31, 86.27, 95.24, 80.00]
    colors = ["#9aa7b4", "#9aa7b4", "#c9d3df", "#c9d3df", "#d97706", "#2f7d32", "#3354aa"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    y = np.arange(len(labels))
    bars = ax.barh(y, values, color=colors, height=0.58)
    ax.set_yticks(y, labels, fontproperties=CJK, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("准确率（%）", fontproperties=CJK, fontsize=11)
    ax.grid(axis="x", color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, values):
        ax.text(
            value + 1.2,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.2f}%",
            va="center",
            fontproperties=CJK,
            fontsize=10,
        )
    ax.set_title(
        "验证集 51 张：版本与分支准确率对比（旧标签/旧模型仅作历史对照）",
        fontproperties=CJK,
        fontsize=12,
        pad=12,
    )
    fig.tight_layout()
    fig.savefig(OUT / "metrics.png", dpi=220, facecolor="white")
    plt.close(fig)


def confusion() -> None:
    matrix = np.array([[24, 4], [3, 20]])
    fig, ax = plt.subplots(figsize=(4.6, 4.0))
    image = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks([0, 1], ["预测 text", "预测 formula"], fontproperties=CJK)
    ax.set_yticks([0, 1], ["真实 text", "真实 formula"], fontproperties=CJK)
    for i in range(2):
        for j in range(2):
            ax.text(
                j,
                i,
                str(matrix[i, j]),
                ha="center",
                va="center",
                fontproperties=CJK,
                fontsize=18,
                color="white" if matrix[i, j] > 20 else "#1f2937",
            )
    ax.set_title("当前路由链路验证集混淆矩阵", fontproperties=CJK, fontsize=12)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(OUT / "confusion.png", dpi=220, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    dataset_examples()
    annotation_examples()
    architecture()
    metrics_chart()
    confusion()
    print("assets written to", OUT)
