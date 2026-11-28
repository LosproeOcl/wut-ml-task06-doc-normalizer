"""生成 v5 验证集/训练过程的指标图（替代 v4 时期旧图）。

数据来源：
- reports/routed_val_v5.json（v5 验证集路由逐样本结果）
- runs/carrier-gate-v5-01/epochs.csv（恢复重建门控训练日志）
- runs/paper-cnn-v5-s45|s47/epochs.csv（恢复重建纸质分支训练日志）
- 报告中冻结的验证/CV 指标

用法：python3 scripts/make_metrics_figures_v5.py
输出：reports/developer_report_assets/{val_metrics_v5,confusion_val_v5,carrier_gate_curves_v5,paper_model_curves_v5}.png
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/developer_report_assets"
OUT.mkdir(parents=True, exist_ok=True)

NAVY = "#1f3a5f"
TEAL = "#2a9d8f"
CORAL = "#e76f51"
GOLD = "#e9c46a"
GRAY = "#8d99ae"
INK = "#293241"
PAPER = "#fbfbf8"


def setup():
    for candidate in [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
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
    plt.rcParams.update({
        "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
        "axes.edgecolor": "#d8d8d0", "axes.linewidth": 0.8, "axes.titlesize": 13,
        "axes.titleweight": "bold", "axes.labelsize": 10.5, "xtick.labelsize": 10,
        "ytick.labelsize": 10, "legend.fontsize": 9, "font.size": 10.5,
    })


def save(fig, name):
    fig.savefig(OUT / name, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("saved", name)


def val_metrics():
    items = [
        ("载体门控（外部）", 100.0, GRAY),
        ("PPT 分支", 95.24, NAVY),
        ("纸质分支", 76.67, TEAL),
        ("双分支路由", 84.31, CORAL),
        ("传统 SVM", 72.55, GOLD),
        ("单模型 CNN", 68.63, GRAY),
    ]
    cv = {
        "PPT 分支": (73.73, 12.42, NAVY),
        "纸质分支": (85.00, 9.23, TEAL),
        "传统 SVM": (75.02, 7.80, GOLD),
        "单模型 CNN": (77.00, 7.91, GRAY),
    }
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.9))
    ax = axes[0]
    names = [n for n, _, _ in items][::-1]
    values = [v for _, v, _ in items][::-1]
    colors = [c for _, _, c in items][::-1]
    ax.barh(np.arange(len(names)), values, color=colors, height=0.55)
    for yi, v in zip(range(len(names)), values):
        ax.text(v + 1.2, yi, f"{v:.1f}%", va="center", fontsize=9.5, color=INK)
    ax.axvline(85, color=CORAL, lw=1.0, ls="--")
    ax.set_yticks(range(len(names)), names)
    ax.set_xlim(0, 112)
    ax.set_xlabel("准确率（%）")
    ax.set_title("v5 验证集与外部门控指标")

    ax = axes[1]
    labels = list(cv)
    means = [cv[k][0] for k in labels]
    stds = [cv[k][1] for k in labels]
    cols = [cv[k][2] for k in labels]
    ax.bar(np.arange(len(labels)), means, yerr=stds, capsize=5, width=0.55, color=cols,
           error_kw={"ecolor": INK, "lw": 1.0})
    for xi, (m, s) in enumerate(zip(means, stds)):
        ax.text(xi, m + s + 1.6, f"{m:.1f}±{s:.1f}", ha="center", fontsize=9.5, color=INK)
    ax.set_xticks(np.arange(len(labels)), labels, rotation=12)
    ax.set_ylim(0, 108)
    ax.set_ylabel("折内准确率（%）")
    ax.set_title("v5 五折分组 CV（均值 ± 标准差）")
    save(fig, "val_metrics_v5.png")


def confusion_val():
    payload = json.loads((ROOT / "reports/routed_val_v5.json").read_text(encoding="utf-8"))
    matrix = np.asarray(payload["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(5.6, 4.2))
    im = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=matrix.max())
    for i in range(2):
        for j in range(2):
            color = "white" if matrix[i, j] > matrix.max() * 0.6 else INK
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center", fontsize=15, color=color)
    ax.set_xticks(range(2), ["预测 文字", "预测 公式"])
    ax.set_yticks(range(2), ["真实 文字", "真实 公式"])
    ax.set_title(f"v5 验证集路由混淆矩阵｜准确率 {payload['accuracy']*100:.2f}%")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    save(fig, "confusion_val_v5.png")


def _read_epochs(name):
    with (ROOT / "runs" / name / "epochs.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def gate_curves():
    rows = _read_epochs("carrier-gate-v5-01")
    epochs = [int(r["epoch"]) for r in rows]
    train = [float(r["train_loss"]) for r in rows]
    val = [float(r["val_loss"]) for r in rows]
    acc = [float(r["val_accuracy"]) for r in rows]
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.plot(epochs, train, "o-", color=NAVY, label="训练损失")
    ax.plot(epochs, val, "s-", color=CORAL, label="验证损失")
    ax.set_xlabel("轮次")
    ax.set_ylabel("交叉熵损失")
    ax.set_xticks(epochs)
    ax2 = ax.twinx()
    ax2.plot(epochs, acc, "^--", color=TEAL, label="验证准确率")
    ax2.set_ylabel("验证准确率")
    ax2.set_ylim(0.9, 1.005)
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines], loc="center right", frameon=False)
    ax.set_title("载体门控训练曲线（v5 恢复重建版，2,149/900）")
    save(fig, "carrier_gate_curves_v5.png")


def paper_curves():
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    for name, color, label in [
        ("paper-cnn-v5-s45", TEAL, "s45"),
        ("paper-cnn-v5-s47", NAVY, "s47"),
    ]:
        rows = _read_epochs(name)
        epochs = [int(r["epoch"]) for r in rows]
        acc = [float(r["val_accuracy"]) for r in rows]
        ax.plot(epochs, acc, "o-", color=color, label=f"{label} 验证准确率")
    ax.set_xlabel("轮次")
    ax.set_ylabel("验证准确率")
    ax.set_ylim(0.4, 1.0)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("纸质分支训练曲线（v5 恢复重建版，s45 / s47）")
    save(fig, "paper_model_curves_v5.png")



def recovery_compare():
    labels = ["合计 72", "自采 42", "外部 30"]
    official = [93.06, 88.10, 100.0]
    recovery = [90.28, 83.33, 100.0]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    ax.bar(x - 0.18, official, width=0.36, color=NAVY, label="正式冻结（原权重）")
    ax.bar(x + 0.18, recovery, width=0.36, color=CORAL, alpha=0.85, label="恢复权重复评")
    for xi, v in zip(x - 0.18, official):
        ax.text(xi, v + 1.0, f"{v:.2f}", ha="center", fontsize=9, color=INK)
    for xi, v in zip(x + 0.18, recovery):
        ax.text(xi, v + 1.0, f"{v:.2f}", ha="center", fontsize=9, color=INK)
    ax.axhline(85, color=GRAY, lw=1.0, ls="--")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 110)
    ax.set_ylabel("准确率（%）")
    ax.set_title("v5 测试集：正式冻结与恢复权重复评对比")
    ax.legend(frameon=False, loc="lower right")
    save(fig, "test_recovery_compare.png")


def main() -> int:
    setup()
    val_metrics()
    confusion_val()
    gate_curves()
    paper_curves()
    recovery_compare()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
