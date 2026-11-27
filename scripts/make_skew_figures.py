"""生成空间偏度调研图：准确率-角度、门控召回、合成偏度示例。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "reports/figures"
NAVY, TEAL, CORAL, GRAY, INK, PAPER = "#1f3a5f", "#2a9d8f", "#e76f51", "#8d99ae", "#293241", "#fbfbf8"


def setup() -> None:
    for candidate in (os.environ.get("CJK_FONT", ""), "/fonts/cjk.ttc", str(ROOT / "assets/fonts/NotoSansCJKsc-Regular.otf")):
        path = Path(candidate)
        if candidate and path.is_file():
            fm.fontManager.addfont(str(path))
            name = fm.FontProperties(fname=str(path)).get_name()
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
    plt.rcParams.update({
        "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
        "axes.edgecolor": "#d8d8d0", "axes.linewidth": 0.8, "axes.titlesize": 13,
        "axes.titleweight": "semibold", "axes.labelsize": 10, "font.size": 10,
        "text.color": INK, "axes.labelcolor": INK, "xtick.color": "#5c6770",
        "ytick.color": "#5c6770", "axes.unicode_minus": False, "legend.frameon": False,
    })


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def save(fig, name: str) -> None:
    for suffix in ("png", "svg"):
        fig.savefig(FIG / f"{name}.{suffix}", dpi=300, bbox_inches="tight", facecolor=PAPER)
    plt.close(fig)


def accuracy_figure() -> None:
    base = load("reports/spatial_skew.json")
    opt = load("reports/spatial_skew_thr_0.3.json")
    angles = [0, 10, 20, 30, 40]
    classifier = [base["classifier"][str(a)]["accuracy"] * 100 for a in angles]
    pipeline = [base["pipeline"][str(a)]["accuracy"] * 100 for a in angles]
    optimized = [opt["pipeline"][str(a)]["accuracy"] * 100 for a in angles]
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.plot(angles, classifier, color=TEAL, marker="o", linewidth=2.2, label="内容模型（拉正后加偏度）")
    ax.plot(angles, pipeline, color=GRAY, marker="o", linewidth=2.2, label="完整链路（原门控）")
    ax.plot(angles, optimized, color=NAVY, marker="o", linewidth=2.4, label="完整链路（门控 TTA + 阈值 0.3）")
    for values, color, offsets in ((classifier, TEAL, (0, 7)), (pipeline, GRAY, (0, -15)), (optimized, NAVY, (0, 7))):
        for index, angle in enumerate(angles):
            if angle in (30, 40):
                ax.annotate(f"{values[index]:.1f}", (angle, values[index]), textcoords="offset points", xytext=offsets, ha="center", fontsize=8, color=color)
    ax.set_xticks(angles, [f"{a}°" for a in angles])
    ax.set_ylim(68, 100)
    ax.set_ylabel("PPT 内容准确率（%）")
    ax.set_xlabel("合成空间偏度")
    ax.set_title("偏度压力测试：瓶颈在载体门控，而非内容模型", loc="left")
    ax.grid(axis="y", color="#e7e7e1", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="lower left")
    fig.text(0.02, 0.01, "数据：21 张 PPT 自采验证页，合成梯形透视；不新增样本。", fontsize=8, color=GRAY)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, "spatial_skew_accuracy")


def gate_figure() -> None:
    base = load("reports/gate_skew.json")
    aug = load("reports/gate_skew_aug.json")
    angles = [0, 10, 20, 30, 40]
    series = [
        ("原门控 @0.5", [base[str(a)]["raw_thresholds"]["0.5"]["ppt_recall"] * 100 for a in angles], GRAY, "--"),
        ("原门控 TTA @0.3", [base[str(a)]["tta_thresholds"]["0.3"]["ppt_recall"] * 100 for a in angles], TEAL, "-"),
        ("偏度增广门控 TTA @0.2", [aug[str(a)]["tta_thresholds"]["0.2"]["ppt_recall"] * 100 for a in angles], NAVY, "-"),
    ]
    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    for label, values, color, style in series:
        ax.plot(angles, values, color=color, marker="o", linewidth=2.2, linestyle=style, label=label)
    ax.set_xticks(angles, [f"{a}°" for a in angles])
    ax.set_ylim(50, 102)
    ax.set_ylabel("PPT 召回率（%）")
    ax.set_xlabel("合成空间偏度")
    ax.set_title("载体门控在偏度下的 PPT 召回", loc="left")
    ax.grid(axis="y", color="#e7e7e1", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="lower left")
    fig.text(0.02, 0.01, "纸质召回在全部阈值/角度下保持 100%；TTA 为 -12/0/12 度旋转平均。", fontsize=8, color=GRAY)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, "spatial_skew_gate")


def examples_figure() -> None:
    from docnorm.data.loader import load_image
    from web import services

    path = ROOT / "data/raw_samples/02_ppt_formula/IMG_4598.jpeg"
    image = load_image(path, max_long_edge=1280).image
    rectified, _quad, _status = services._apply_rectify(image)
    panels = []
    for angle in (0, 20, 40):
        if angle == 0:
            warped = rectified
        else:
            h, w = rectified.shape[:2]
            shift = min(w * 0.35, h * 0.55 * np.tan(np.radians(angle)))
            src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
            dst = np.float32([[shift, 0], [w - shift, 0], [w, h], [0, h]])
            matrix = cv2.getPerspectiveTransform(src, dst)
            warped = cv2.warpPerspective(rectified, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)
        panels.append((angle, warped))
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.2))
    for ax, (angle, panel) in zip(axes, panels):
        ax.imshow(cv2.cvtColor(panel, cv2.COLOR_BGR2RGB))
        ax.set_title(f"合成偏度 {angle}°", loc="left", fontsize=11)
        ax.axis("off")
    fig.suptitle("空间偏度压力测试示例（PPT 样张，仅示意）", x=0.03, ha="left", fontsize=14, fontweight="semibold", color=INK)
    fig.tight_layout(rect=(0, 0.04, 1, 0.9))
    save(fig, "spatial_skew_examples")


def main() -> int:
    setup()
    accuracy_figure()
    gate_figure()
    examples_figure()
    print("写入 reports/figures/spatial_skew_*.png/svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
