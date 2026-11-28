"""生成 split_v5 一次性评估的多维度评估图。

数据来源：
- reports/final_test_v5.json（逐张预测、分层指标、自助法置信区间）
- runs/cv-v5-{svm,cnn,ppt,paper}-f1..5/metrics.json（5 折分组交叉验证）

用法：
    python3 scripts/make_eval_figures_v5.py
输出：reports/figures/eval_v5_*.png（300 dpi）与同名 SVG。
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

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
    for candidate in [
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ]:
        path = Path(candidate)
        if path.is_file():
            try:
                fm.fontManager.addfont(str(path))
                name = fm.FontProperties(fname=str(path)).get_name()
                plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
                break
            except Exception:
                continue
    plt.rcParams.update(
        {
            "figure.facecolor": PAPER,
            "axes.facecolor": PAPER,
            "savefig.facecolor": PAPER,
            "axes.edgecolor": "#d8d8d0",
            "axes.linewidth": 0.8,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.labelsize": 10.5,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 9.5,
            "font.size": 10.5,
        }
    )


def save(fig, name: str) -> None:
    for suffix in ("png", "svg"):
        fig.savefig(FIG_DIR / f"{name}.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {name}")


def load_payload() -> dict:
    return json.loads((ROOT / "reports/final_test_v5.json").read_text(encoding="utf-8"))


def cv_summary() -> dict:
    families = {"svm": "cv-v5-svm-f", "cnn": "cv-v5-cnn-f", "ppt": "cv-v5-ppt-f", "paper": "cv-v5-paper-f"}
    labels = {
        "svm": "传统 SVM",
        "cnn": "MobileNetV3-Small",
        "ppt": "PPT 分支",
        "paper": "纸质分支",
    }
    out = {}
    for key, prefix in families.items():
        accs, f1s = [], []
        for fold in range(1, 6):
            payload = json.loads(
                (ROOT / f"runs/{prefix}{fold}/metrics.json").read_text(encoding="utf-8")
            )
            if key == "svm":
                metrics = payload["models"]["svm"]
            else:
                metrics = payload["metrics"]
            accs.append(float(metrics["accuracy"]))
            f1s.append(float(metrics["macro_f1"]))
        out[key] = {
            "label": labels[key],
            "mean": st.mean(accs),
            "std": st.stdev(accs),
            "folds": accs,
            "f1_mean": st.mean(f1s),
            "f1_std": st.stdev(f1s),
        }
    return out


def fig_overall(payload: dict) -> None:
    rows = payload["rows"]
    subsets = [
        ("合计 72", payload["final"]["accuracy"], NAVY),
        ("自采 42", payload["final_self"]["accuracy"], TEAL),
        ("外部 30", payload["final_external"]["accuracy"], GOLD),
    ]
    methods = [
        ("双分支路由", payload["final"]["accuracy"], payload["final"]["macro_f1"], NAVY),
        ("传统 SVM", payload["classic_svm"]["accuracy"], payload["classic_svm"]["macro_f1"], CORAL),
        ("单模型 CNN", payload["single_cnn"]["accuracy"], payload["single_cnn"]["macro_f1"], GRAY),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.9))
    ax = axes[0]
    names = [name for name, _, _, _ in methods]
    acc = [value * 100 for _, value, _, _ in methods]
    f1 = [value * 100 for _, _, value, _ in methods]
    x = np.arange(len(names))
    ax.bar(x - 0.18, acc, width=0.36, label="准确率", color=[c for _, _, _, c in methods])
    ax.bar(x + 0.18, f1, width=0.36, label="宏 F1", color=[c for _, _, _, c in methods], alpha=0.55)
    for xi, value in zip(x - 0.18, acc):
        ax.text(xi, value + 1.2, f"{value:.1f}", ha="center", fontsize=9, color=INK)
    for xi, value in zip(x + 0.18, f1):
        ax.text(xi, value + 1.2, f"{value:.1f}", ha="center", fontsize=9, color=INK, alpha=0.75)
    ax.axhline(85, color=CORAL, lw=1.2, ls="--")
    ax.text(len(names) - 0.52, 85.8, "85% 门禁", color=CORAL, fontsize=9)
    ax.set_xticks(x, names)
    ax.set_ylim(0, 104)
    ax.set_ylabel("百分比（%）")
    ax.set_title("v5 测试集（合计 72 张）")
    ax.legend(loc="lower right", frameon=False)

    ax = axes[1]
    labels = [name for name, _, _ in subsets]
    values = [value * 100 for _, value, _ in subsets]
    bars = ax.bar(labels, values, width=0.55, color=[c for _, _, c in subsets])
    for bar, (_, value, _) in zip(bars, subsets):
        ax.text(bar.get_x() + bar.get_width() / 2, value * 100 + 1.2, f"{value * 100:.1f}%", ha="center", fontsize=9.5, color=INK)
    ax.axhline(85, color=CORAL, lw=1.2, ls="--")
    ax.set_ylim(0, 108)
    ax.set_ylabel("准确率（%）")
    ax.set_title("路由准确率分层（自采 / 外部）")
    save(fig, "eval_v5_overall")


def fig_confusion(payload: dict) -> None:
    matrices = [
        ("合计 72 张", payload["final"]["confusion_matrix"], payload["final"]["accuracy"]),
        ("自采 42 张", payload["final_self"]["confusion_matrix"], payload["final_self"]["accuracy"]),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.8))
    labels = ["文字", "公式"]
    for ax, (title, matrix, accuracy) in zip(axes, matrices):
        array = np.asarray(matrix)
        im = ax.imshow(array, cmap="Blues", vmin=0, vmax=max(array.max(), 1))
        for i in range(2):
            for j in range(2):
                color = "white" if array[i, j] > array.max() * 0.6 else INK
                ax.text(j, i, str(array[i, j]), ha="center", va="center", fontsize=14, color=color)
        ax.set_xticks(range(2), [f"预测 {name}" for name in labels])
        ax.set_yticks(range(2), [f"真实 {name}" for name in labels])
        ax.set_title(f"{title}｜准确率 {accuracy * 100:.2f}%")
    fig.colorbar(im, ax=axes, shrink=0.85, pad=0.02)
    save(fig, "eval_v5_confusion")


def fig_recall(payload: dict) -> None:
    categories = ["文字召回", "公式召回"]
    overall = payload["final"]["per_class_recall"]
    self_recall = payload["final_self"]["per_class_recall"]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    x = np.arange(len(categories))
    ax.bar(x - 0.18, [overall[name] * 100 for name in ("text", "formula")], width=0.36,
           label="合计 72", color=NAVY)
    ax.bar(x + 0.18, [self_recall[name] * 100 for name in ("text", "formula")], width=0.36,
           label="自采 42", color=TEAL, alpha=0.85)
    for xi, value in zip(x - 0.18, [overall[name] * 100 for name in ("text", "formula")]):
        ax.text(xi, value + 1.6, f"{value:.1f}", ha="center", fontsize=9.5, color=INK)
    for xi, value in zip(x + 0.18, [self_recall[name] * 100 for name in ("text", "formula")]):
        ax.text(xi, value + 1.6, f"{value:.1f}", ha="center", fontsize=9.5, color=INK)
    ax.axhline(70, color=CORAL, lw=1.2, ls="--")
    ax.text(1.42, 71.5, "70% 下限", color=CORAL, fontsize=9)
    ax.set_xticks(x, categories)
    ax.set_ylim(0, 112)
    ax.set_ylabel("召回率（%）")
    ax.set_title("分类别召回（路由链路）")
    ax.legend(frameon=False, loc="lower left")
    save(fig, "eval_v5_recall")


def fig_distribution() -> None:
    import csv

    excluded = {
        row["sample_id"]
        for row in csv.DictReader(
            (ROOT / "data/manifests/exclusions.csv").open(encoding="utf-8-sig")
        )
    }
    rows = [
        row
        for row in csv.DictReader(
            (ROOT / "data/manifests/sample_manifest_v5.csv").open(encoding="utf-8-sig")
        )
        if row["sample_id"] not in excluded and row["label"] not in {"", "99_unlabeled"}
    ]
    split = json.loads((ROOT / "data/splits/split_v5.json").read_text(encoding="utf-8"))
    group_to_set = {
        group: name for name, groups in split["groups"].items() for group in groups
    }
    order = ["train", "val", "test"]
    labels_cn = {"train": "训练 349", "val": "验证 51", "test": "测试 72"}
    text_counts = [0, 0, 0]
    formula_counts = [0, 0, 0]
    for row in rows:
        index = order.index(group_to_set[row["doc_page_id"]])
        if row["content_label"] if False else row["label"].endswith("text"):
            text_counts[index] += 1
        else:
            formula_counts[index] += 1
    fig, axes = plt.subplots(1, 2, figsize=(9.8, 3.8))
    ax = axes[0]
    y = np.arange(len(order))[::-1]
    ax.barh(y, text_counts, height=0.52, label="文字", color=NAVY)
    ax.barh(y, formula_counts, height=0.52, left=text_counts, label="公式", color=GOLD)
    for yi, (t, f) in zip(y, zip(text_counts, formula_counts)):
        ax.text(t / 2, yi, str(t), ha="center", va="center", color="white", fontsize=10)
        ax.text(t + f / 2, yi, str(f), ha="center", va="center", color=INK, fontsize=10)
    ax.set_yticks(y, [labels_cn[name] for name in order])
    ax.set_xlim(0, 360)
    ax.set_xlabel("样本数")
    ax.set_title("v5 各集合内容构成")
    ax.legend(frameon=False, loc="lower right")

    ax = axes[1]
    lighting_order = ["ceiling", "side_lamp", "natural", "backlight"]
    lighting_cn = ["教室顶灯", "侧向光源", "自然光", "逆光/反光"]
    scene_order = ["classroom", "dorm", "outdoor"]
    scene_cn = ["教室", "宿舍/桌面", "户外"]
    light_counts = [sum(1 for r in rows if r["lighting"] == name) for name in lighting_order]
    scene_counts = [sum(1 for r in rows if r["scene"] == name) for name in scene_order]
    x = np.arange(len(lighting_order))
    ax.bar(x, light_counts, width=0.55, color=TEAL, label="光照")
    for xi, value in zip(x, light_counts):
        ax.text(xi, value + 3, str(value), ha="center", fontsize=9.5, color=INK)
    ax.set_xticks(x, lighting_cn)
    ax.set_ylim(0, max(light_counts) * 1.25)
    ax.set_ylabel("样本数")
    ax2 = ax.twiny()
    ax2.bar(np.arange(len(scene_order)) + 0.0, scene_counts, width=0.0)
    ax2.set_xticks(np.arange(len(scene_order)) + 0.0, [])
    ax2.set_xlim(ax.get_xlim())
    for xi, (name, cn) in enumerate(zip(scene_order, scene_cn)):
        count = scene_counts[xi]
        ax.text(0.02 + xi * 0.0, 0, "", fontsize=1)
    note = "  ".join(f"{cn} {count}" for cn, count in zip(scene_cn, scene_counts))
    ax.set_title(f"采集条件分布（场景：{note}）", fontsize=11)
    save(fig, "eval_v5_distribution")


def fig_cv(summary: dict) -> None:
    order = ["svm", "cnn", "ppt", "paper"]
    labels = [summary[key]["label"] for key in order]
    means = [summary[key]["mean"] * 100 for key in order]
    stds = [summary[key]["std"] * 100 for key in order]
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    colors = [CORAL, NAVY, GOLD, TEAL]
    ax.bar(np.arange(4), means, yerr=stds, capsize=5, width=0.55,
           color=colors, error_kw={"ecolor": INK, "lw": 1.1})
    for xi, (mean, std) in enumerate(zip(means, stds)):
        ax.text(xi, mean + std + 1.6, f"{mean:.1f}±{std:.1f}", ha="center", fontsize=9.5, color=INK)
    ax.axhline(85, color=CORAL, lw=1.0, ls="--", alpha=0.6)
    ax.set_xticks(np.arange(4), labels)
    ax.set_ylim(0, 108)
    ax.set_ylabel("折内准确率均值（%）")
    ax.set_title("v5 五折分组 CV（均值 ± 标准差，5 折）")
    save(fig, "eval_v5_cv")


def fig_ci(payload: dict) -> None:
    items = [
        ("合计 72", payload["final_accuracy_ci95"], payload["final"]["accuracy"], NAVY, ""),
        ("自采 42", payload["final_self_accuracy_ci95"], payload["final_self"]["accuracy"], TEAL, ""),
    ]
    carrier = payload["final_per_carrier"]
    items.append(("纸质 51", None, carrier["paper"]["accuracy"], GOLD, "点估计（n=51）"))
    items.append(("PPT 21", None, carrier["ppt"]["accuracy"], CORAL, "点估计（n=21）"))
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    for index, (label, ci, point, color, note) in enumerate(items):
        if ci:
            low, high = max(0.0, ci[0]) * 100, min(1.0, ci[1]) * 100
            ax.plot([low, high], [index, index], color=color, lw=3.2, alpha=0.75,
                    label="自助法 95% CI" if index == 0 else None)
        ax.plot(point * 100, index, "o", color=color, ms=9)
        offset = "CI [{:.1f}, {:.1f}]".format(ci[0] * 100, ci[1] * 100) if ci else note
        ax.annotate(
            f"{point * 100:.1f}%  {offset}",
            (point * 100, index),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
            fontsize=9.5,
            color=INK,
        )
    ax.axvline(85, color=CORAL, lw=1.2, ls="--")
    ax.text(85.4, 3.42, "85% 门禁", color=CORAL, fontsize=9)
    ax.set_yticks(range(len(items)), [label for label, _, _, _, _ in items])
    ax.set_xlim(55, 105)
    ax.set_ylim(-0.6, 3.8)
    ax.set_xlabel("准确率（%）")
    ax.set_title("v5 测试集准确率与 95% 置信区间")
    ax.legend(frameon=False, loc="lower left")
    save(fig, "eval_v5_ci")


def main() -> int:
    setup_style()
    payload = load_payload()
    fig_overall(payload)
    fig_confusion(payload)
    fig_recall(payload)
    fig_distribution()
    fig_cv(cv_summary())
    fig_ci(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
