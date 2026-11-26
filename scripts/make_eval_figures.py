"""生成网页双分支接入后的多维度评估图。

数据来源：
- runs/paper-cnn-* / metrics.json
- reports/eval_paper/{base,extctl}_val.csv
- reports/routed_pipeline.json

用法：
    python3 scripts/make_eval_figures.py
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "reports/figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

NAVY = "#1f3a5f"
TEAL = "#2a9d8f"
CORAL = "#e76f51"
GOLD = "#e9c46a"
GRAY = "#8d99ae"
INK = "#293241"
PAPER = "#fbfbf8"


def setup_style() -> None:
    candidates = [
        os.environ.get("CJK_FONT", ""),
        "/fonts/cjk.ttc",
        str(ROOT / "assets/fonts/NotoSansCJKsc-Regular.otf"),
    ]
    for candidate in candidates:
        path = Path(candidate)
        if not candidate or not path.is_file():
            continue
        fm.fontManager.addfont(str(path))
        name = fm.FontProperties(fname=str(path)).get_name()
        plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
        break
    plt.rcParams.update(
        {
            "figure.facecolor": PAPER,
            "axes.facecolor": PAPER,
            "savefig.facecolor": PAPER,
            "axes.edgecolor": "#d8d8d0",
            "axes.linewidth": 0.8,
            "axes.titlesize": 13,
            "axes.titleweight": "semibold",
            "axes.labelsize": 10,
            "xtick.color": "#5c6770",
            "ytick.color": "#5c6770",
            "text.color": INK,
            "axes.labelcolor": INK,
            "font.size": 10,
            "axes.unicode_minus": False,
            "legend.frameon": False,
        }
    )


def load_metrics(run: str) -> dict:
    payload = json.loads((ROOT / "runs" / run / "metrics.json").read_text(encoding="utf-8"))
    return payload.get("metrics", payload)


def read_predictions(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def save(fig, name: str) -> None:
    for suffix in ("png", "svg"):
        fig.savefig(
            FIG_DIR / f"{name}.{suffix}",
            dpi=300,
            bbox_inches="tight",
            facecolor=PAPER,
        )
    plt.close(fig)


def pipeline_comparison() -> None:
    routed = json.loads((ROOT / "reports/routed_pipeline.json").read_text(encoding="utf-8"))
    cnn = load_metrics("exp-cnn-05")
    extctl_f1 = 0.8168498168498168
    rows = [
        ("多数类（全判 text）", 28, 51, 0.3544, GRAY),
        ("单模型 CNN", 41, 51, cnn["macro_f1"], "#6c8ebf"),
        ("纸质稿集成（30 张）", 25, 30, extctl_f1, TEAL),
        ("双分支路由（本次接入）", 45, 51, routed["macro_f1"], NAVY),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    y = np.arange(len(rows))
    accuracy = np.array([row[1] / row[2] * 100 for row in rows])
    f1 = np.array([row[3] * 100 for row in rows])
    colors = [row[4] for row in rows]
    for panel, (ax, values, title) in enumerate(
        zip(axes, (accuracy, f1), ("准确率", "宏平均 F1"))
    ):
        ax.barh(y, values, height=0.56, color=colors, alpha=0.92)
        ax.set_yticks(y, [row[0] for row in rows])
        ax.invert_yaxis()
        ax.set_xlim(0, 104)
        ax.grid(axis="x", color="#e7e7e1", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_title(title, loc="left", pad=10)
        for index, value in enumerate(values):
            if panel == 0:
                ax.text(
                    2.5,
                    index,
                    f"{value:.1f}",
                    va="center",
                    fontsize=9,
                    color="#ffffff",
                    fontweight="semibold",
                )
            else:
                ax.text(
                    value + 1.2,
                    index,
                    f"{value:.1f}",
                    va="center",
                    fontsize=9,
                    color=INK,
                )
    for spine in axes[0].spines.values():
        spine.set_visible(False)
    for spine in axes[1].spines.values():
        spine.set_visible(False)
    for index, row in enumerate(rows):
        low, high = wilson(row[1], row[2])
        axes[0].errorbar(
            row[1] / row[2] * 100,
            index,
            xerr=[
                [row[1] / row[2] * 100 - low * 100],
                [high * 100 - row[1] / row[2] * 100],
            ],
            fmt="none",
            ecolor="#5c6770",
            elinewidth=1.0,
            capsize=3,
        )
    axes[0].set_xlabel("验证集准确率（%，95% Wilson 区间）")
    axes[1].set_xlabel("宏平均 F1（%）")
    fig.suptitle(
        "从单模型到双分支路由：自采验证集表现",
        x=0.06,
        ha="left",
        fontsize=15,
        fontweight="semibold",
        color=INK,
    )
    fig.text(
        0.06,
        0.905,
        "路由链路：载体门控 → 纸质稿 CNN 集成 / PPT CNN；纸质分支单独评估 30 张纸质验证页",
        fontsize=9,
        color="#6c757d",
    )
    fig.text(
        0.06,
        0.01,
        "数据：split_v3 验证集；单模型 CNN 为 exp-cnn-05，路由为 51 张逐页评估。",
        fontsize=8,
        color="#8d99ae",
    )
    fig.tight_layout(rect=(0.04, 0.06, 0.98, 0.86))
    save(fig, "eval_pipeline_comparison")


def seed_stability() -> None:
    seeds = [42, 43, 44]
    base = [
        load_metrics("paper-cnn-01")["accuracy"] * 100,
        load_metrics("paper-cnn-base-43")["accuracy"] * 100,
        load_metrics("paper-cnn-base-44")["accuracy"] * 100,
    ]
    extctl = [
        load_metrics("paper-cnn-extctl-01")["accuracy"] * 100,
        load_metrics("paper-cnn-extctl-43")["accuracy"] * 100,
        load_metrics("paper-cnn-extctl-44")["accuracy"] * 100,
    ]
    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    x = np.arange(len(seeds))
    ax.plot(x, base, color=GRAY, marker="o", markersize=7, linewidth=2, label="全部外部数据")
    ax.plot(x, extctl, color=TEAL, marker="o", markersize=7, linewidth=2, label="SmartDoc + Scientific")
    base_offsets = ((-16, -14), (0, 12), (0, -18))
    ext_offsets = ((-16, 10), (0, 12), (8, 10))
    for values, color, offsets in (
        (base, GRAY, base_offsets),
        (extctl, TEAL, ext_offsets),
    ):
        for index, value in enumerate(values):
            ax.annotate(
                f"{value:.1f}",
                (x[index], value),
                textcoords="offset points",
                xytext=offsets[index],
                ha="center",
                fontsize=9,
                color=color,
            )
        ax.axhline(
            np.mean(values),
            color=color,
            linestyle=(0, (4, 3)),
            linewidth=1,
            alpha=0.65,
        )
        ax.text(
            x[-1] + 0.12,
            np.mean(values),
            f"均值 {np.mean(values):.1f}",
            va="center",
            fontsize=8.5,
            color=color,
        )
    ax.set_xticks(x, [f"种子 {seed}" for seed in seeds])
    ax.set_ylim(60, 92)
    ax.set_ylabel("准确率（%）")
    ax.set_title("种子稳定性：三组同配置训练的纸质验证准确率", loc="left")
    ax.grid(axis="y", color="#e7e7e1", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="upper left", ncol=1)
    fig.text(
        0.02,
        0.01,
        "数据：30 张自采纸质验证页；两组均使用 MobileNetV3-Small 与相同训练轮数。",
        fontsize=8,
        color="#8d99ae",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, "eval_seed_stability")


def weight_ablation() -> None:
    base_balanced = load_metrics("paper-cnn-01")["accuracy"] * 100
    base_none = load_metrics("paper-cnn-base-nw-01")["accuracy"] * 100
    ext_balanced = load_metrics("paper-cnn-extctl-01")["accuracy"] * 100
    ext_none = load_metrics("paper-cnn-extctl-nw-01")["accuracy"] * 100
    rows = [
        ("全部外部数据", base_balanced, base_none, GRAY),
        ("SmartDoc + Scientific", ext_balanced, ext_none, TEAL),
    ]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for index, (label, balanced, none, color) in enumerate(rows):
        ax.plot([none, balanced], [index, index], color=color, linewidth=2, alpha=0.35)
        ax.scatter([none], [index], s=90, color="#ffffff", edgecolor=color, linewidth=2, zorder=3)
        ax.scatter([balanced], [index], s=110, color=color, edgecolor=PAPER, linewidth=2, zorder=4)
        ax.annotate(
            f"{balanced:.1f}",
            (balanced, index),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=9,
            color=color,
            fontweight="semibold",
        )
        ax.annotate(
            f"{none:.1f}",
            (none, index),
            textcoords="offset points",
            xytext=(0, -18),
            ha="center",
            fontsize=9,
            color="#6c757d",
        )
        ax.add_patch(
            FancyArrowPatch(
                (none, index),
                (balanced, index),
                arrowstyle="-|>",
                mutation_scale=12,
                color=color,
                alpha=0.55,
            )
        )
    ax.set_yticks(range(len(rows)), [row[0] for row in rows])
    ax.set_xlim(60, 88)
    ax.set_xlabel("准确率（%）")
    ax.set_title("类别权重消融：关闭平衡权重后增益消失", loc="left")
    ax.grid(axis="x", color="#e7e7e1", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.text(
        0.99,
        0.04,
        "空心点：无类别权重；实心点：平衡权重；两者均为种子 42",
        transform=ax.transAxes,
        ha="right",
        fontsize=8,
        color="#8d99ae",
    )
    fig.tight_layout()
    save(fig, "eval_weight_ablation")


def confusion_panels() -> None:
    base = read_predictions(ROOT / "reports/eval_paper/base_val.csv")
    extctl = read_predictions(ROOT / "reports/eval_paper/extctl_val.csv")

    def matrix(rows):
        labels = ("text", "formula")
        out = np.zeros((2, 2), dtype=int)
        for row in rows:
            out[labels.index(row["label"]), labels.index(row["pred"])] += 1
        return out

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.9))
    for ax, rows, title in zip(
        axes,
        (base, extctl),
        ("单模型：70.0%", "纸质稿集成：83.3%"),
    ):
        cm = matrix(rows)
        ax.imshow(cm, cmap="Blues", vmin=0, vmax=20)
        ax.set_xticks([0, 1], ["判 text", "判 formula"])
        ax.set_yticks([0, 1], ["真 text", "真 formula"])
        ax.set_title(title, loc="left", pad=8)
        for i in range(2):
            for j in range(2):
                ax.text(
                    j,
                    i,
                    str(cm[i, j]),
                    ha="center",
                    va="center",
                    fontsize=16,
                    color="#ffffff" if cm[i, j] > 10 else INK,
                    fontweight="semibold",
                )
        ax.tick_params(length=0)
    fig.suptitle(
        "混淆矩阵：公式召回从 12/20 提升到 17/20",
        x=0.04,
        ha="left",
        fontsize=14,
        fontweight="semibold",
        color=INK,
    )
    fig.text(
        0.04,
        0.01,
        "数据：30 张自采纸质验证页；右侧为 3 个种子的概率平均。",
        fontsize=8,
        color="#8d99ae",
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.9))
    save(fig, "eval_confusion_matrices")


def recall_comparison() -> None:
    base = load_metrics("paper-cnn-01")["confusion_matrix"]
    extctl = load_metrics("paper-cnn-extctl-44")["confusion_matrix"]
    routed = json.loads((ROOT / "reports/routed_pipeline.json").read_text(encoding="utf-8"))
    series = [
        ("单模型", base, GRAY),
        ("纸质稿集成", extctl, TEAL),
        ("双分支路由", routed["confusion_matrix"], NAVY),
    ]
    # confusion rows: true text/formula; cols predicted text/formula
    text_recall = [row[1][0][0] / max(1, sum(row[1][0])) * 100 for row in series]
    formula_recall = [row[1][1][1] / max(1, sum(row[1][1])) * 100 for row in series]
    y = np.arange(len(series))
    height = 0.34
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.barh(y - height / 2, text_recall, height, color=[row[2] for row in series], alpha=0.45, label="text 召回")
    ax.barh(y + height / 2, formula_recall, height, color=[row[2] for row in series], label="formula 召回")
    for index in range(len(series)):
        ax.text(text_recall[index] + 1.2, index - height / 2, f"{text_recall[index]:.1f}", va="center", fontsize=9, color="#6c757d")
        ax.text(formula_recall[index] + 1.2, index + height / 2, f"{formula_recall[index]:.1f}", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, [row[0] for row in series])
    ax.invert_yaxis()
    ax.set_xlim(0, 115)
    ax.set_xlabel("召回率（%）")
    ax.set_title("分类别召回：公式页不再是短板", loc="left")
    ax.grid(axis="x", color="#e7e7e1", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    fig.text(
        0.02,
        0.01,
        "数据：单模型与纸质稿集成为 30 张纸质验证；路由为 51 张验证集。",
        fontsize=8,
        color="#8d99ae",
    )
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    save(fig, "eval_recall_comparison")


def probability_shift() -> None:
    base = {row["sample_id"]: row for row in read_predictions(ROOT / "reports/eval_paper/base_val.csv")}
    extctl = {row["sample_id"]: row for row in read_predictions(ROOT / "reports/eval_paper/extctl_val.csv")}
    ids = [sample_id for sample_id in base if sample_id in extctl]
    fig, ax = plt.subplots(figsize=(6.2, 6.0))
    for sample_id in ids:
        left = float(base[sample_id]["prob_formula"])
        right = float(extctl[sample_id]["prob_formula"])
        label = base[sample_id]["label"]
        color = CORAL if label == "formula" else GRAY
        ax.scatter(left, right, s=46, color=color, alpha=0.8, edgecolor=PAPER, linewidth=1)
    ax.plot([0, 1], [0, 1], color="#c9c9c1", linestyle=(0, (3, 3)), linewidth=1)
    ax.axvline(0.5, color="#c9c9c1", linewidth=1)
    ax.axhline(0.5, color="#c9c9c1", linewidth=1)
    annotation_offsets = {
        "formula_11": (6, 6),
        "formula_12": (6, -12),
        "0731_1": (6, 6),
        "formula_page_06": (6, 6),
        "IMG_20261126_013809": (6, -12),
    }
    for sample_id, offset in annotation_offsets.items():
        if sample_id in base:
            ax.annotate(
                sample_id,
                (float(base[sample_id]["prob_formula"]), float(extctl[sample_id]["prob_formula"])),
                textcoords="offset points",
                xytext=offset,
                fontsize=7,
                color="#6c757d",
            )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("单模型 P(formula)")
    ax.set_ylabel("纸质稿集成 P(formula)")
    ax.set_title("逐样本概率迁移：公式页整体越过 0.5", loc="left")
    ax.grid(color="#eeeeea", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    from matplotlib.lines import Line2D

    ax.legend(
        handles=[
            Line2D([0], [0], marker="o", color="none", markerfacecolor=CORAL, markeredgecolor=PAPER, markersize=7, label="公式页"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor=GRAY, markeredgecolor=PAPER, markersize=7, label="文字页"),
        ],
        loc="lower right",
    )
    fig.text(
        0.02,
        0.01,
        "数据：30 张纸质验证页；右上象限为两模型都判为公式，左上为单模型漏判、集成修复。",
        fontsize=8,
        color="#8d99ae",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, "eval_probability_shift")


def main() -> int:
    setup_style()
    pipeline_comparison()
    seed_stability()
    weight_ablation()
    confusion_panels()
    recall_comparison()
    probability_shift()
    print(f"写入 {FIG_DIR}：eval_*.png / eval_*.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
