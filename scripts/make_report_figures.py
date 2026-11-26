"""生成课程报告用的模型对比图。

用法：
    PYTHONPATH=src python scripts/make_report_figures.py
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

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "reports/figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)


def setup_cjk_font() -> str | None:
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
        plt.rcParams["axes.unicode_minus"] = False
        return name
    print("警告：未找到中文字体，图上中文可能显示为方块")
    return None


setup_cjk_font()

MODELS = [
    ("SVM（自动检测）", "exp-20261126-08", "svm", "#4c72b0"),
    ("随机森林（自动检测）", "exp-20261126-08", "rf", "#4c72b0"),
    ("CNN（自动检测）", "exp-cnn-04", None, "#dd8452"),
    ("CNN（人工四角全量）", "exp-cnn-03", None, "#dd8452"),
    ("CNN（人工四角失败回退）", "exp-cnn-05", None, "#dd8452"),
    ("CNN 320 输入（弱增强）", "exp-cnn-06", None, "#dd8452"),
    ("CNN EfficientNet-B0", "exp-cnn-07", None, "#dd8452"),
    ("CNN MobileNetV3-Large", "exp-cnn-08", None, "#dd8452"),
    ("CNN MobileNetV3-Large 正则化", "exp-cnn-09", None, "#dd8452"),
    ("融合（传统特征 + CNN）", "fusion-exp-01", "fusion_svm", "#8172b2"),
    ("CNN + BiLSTM（最佳种子）", "exp-lstm-01", None, "#c44e52"),
    ("CNN（外部预训练-2400）", "exp-cnn-ext-01", None, "#55a868"),
    ("CNN（外部预训练-600）", "exp-cnn-ext-02", None, "#55a868"),
    ("遗传算法特征选择 + SVM", "ga-feature-01", None, "#8172b2"),
]


def read_metrics(exp: str, model: str | None) -> tuple[float, float] | None:
    path = ROOT / "runs" / exp / "metrics.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if model is None:
        metrics = data.get("metrics", {})
        return float(metrics.get("accuracy", 0)), float(metrics.get("macro_f1", 0))
    metrics = (data.get("models") or {}).get(model)
    if not metrics:
        return None
    return float(metrics["accuracy"]), float(metrics["macro_f1"])


def model_comparison() -> None:
    rows = []
    for label, exp, model, color in MODELS:
        values = read_metrics(exp, model)
        if values is not None:
            rows.append((label, values[0], values[1], color))
    if not rows:
        return
    labels = [row[0] for row in rows]
    accuracy = np.array([row[1] for row in rows]) * 100
    f1 = np.array([row[2] for row in rows]) * 100
    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(9, 5.6))
    height = 0.38
    ax.barh(y - height / 2, accuracy, height, label="准确率", color="#4c72b0")
    ax.barh(y + height / 2, f1, height, label="宏平均 F1", color="#55a868")
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("验证集得分（%）")
    ax.set_title("split_v3 验证集模型对比（n=51）")
    for index, value in enumerate(accuracy):
        ax.text(value + 0.8, index - height / 2, f"{value:.1f}", va="center", fontsize=8)
    for index, value in enumerate(f1):
        ax.text(value + 0.8, index + height / 2, f"{value:.1f}", va="center", fontsize=8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, frameon=False)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(FIG_DIR / "model_comparison.png", dpi=200)
    plt.close(fig)


def corner_policy_comparison() -> None:
    policies = ["不使用", "失败回退", "全部使用"]
    classic_exp = ["exp-20261126-08", "exp-20261126-07", "exp-20261126-05"]
    cnn_exp = ["exp-cnn-04", "exp-cnn-05", "exp-cnn-03"]
    classic = [read_metrics(exp, "svm") for exp in classic_exp]
    cnn = [read_metrics(exp, None) for exp in cnn_exp]
    if any(value is None for value in classic + cnn):
        return
    x = np.arange(len(policies))
    width = 0.36
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    ax.bar(x - width / 2, [v[0] * 100 for v in classic], width, label="SVM", color="#4c72b0")
    ax.bar(x + width / 2, [v[0] * 100 for v in cnn], width, label="MobileNetV3-Small", color="#dd8452")
    ax.set_xticks(x, policies)
    ax.set_ylim(0, 100)
    ax.set_ylabel("准确率（%）")
    ax.set_title("人工四角训练策略（split_v3 验证集）")
    for index, value in enumerate(classic):
        ax.text(index - width / 2, value[0] * 100 + 1, f"{value[0]*100:.1f}", ha="center", fontsize=8)
    for index, value in enumerate(cnn):
        ax.text(index + width / 2, value[0] * 100 + 1, f"{value[0]*100:.1f}", ha="center", fontsize=8)
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "corner_policy_comparison.png", dpi=200)
    plt.close(fig)


def confusion_panels() -> None:
    panels = [
        ("SVM（自动检测）", "exp-20261126-08", "svm"),
        ("CNN（人工四角失败回退）", "exp-cnn-05", None),
        ("融合（传统特征 + CNN）", "fusion-exp-01", "fusion_svm"),
        ("CNN + BiLSTM（种子 42）", "exp-lstm-01", None),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.8))
    for ax, (title, exp, model) in zip(axes, panels):
        path = ROOT / "runs" / exp / "metrics.json"
        if not path.is_file():
            ax.axis("off")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if model is None:
            matrix = np.array(data["metrics"]["confusion_matrix"])
        else:
            matrix = np.array(data["models"][model]["confusion_matrix"])
        ax.imshow(matrix, cmap="Blues")
        ax.set_xticks([0, 1], ["文字", "公式"])
        ax.set_yticks([0, 1], ["文字", "公式"])
        ax.set_xlabel("预测")
        ax.set_ylabel("真实")
        ax.set_title(title)
        for row in range(2):
            for col in range(2):
                ax.text(col, row, str(matrix[row, col]), ha="center", va="center",
                        color="white" if matrix[row, col] > matrix.max() / 2 else "black")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "confusion_matrices.png", dpi=200)
    plt.close(fig)


def training_curves() -> None:
    runs = [
        ("exp-cnn-04", "自动检测"),
        ("exp-cnn-05", "失败回退"),
        ("exp-cnn-06", "320 弱增强"),
        ("exp-cnn-07", "EfficientNet-B0"),
        ("exp-cnn-08", "MobileNetV3-Large"),
        ("exp-cnn-09", "MobileNetV3-Large 正则化"),
        ("exp-lstm-01", "CNN + BiLSTM"),
    ]
    available = [item for item in runs if (ROOT / "runs" / item[0] / "metrics.json").is_file()]
    if not available:
        return
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for exp, label in available:
        data = json.loads((ROOT / "runs" / exp / "metrics.json").read_text(encoding="utf-8"))
        history = data["history"]
        epochs = np.arange(1, len(history["val_accuracy"]) + 1)
        axes[0].plot(epochs, np.array(history["val_accuracy"]) * 100, marker="o", markersize=3, label=label)
        axes[1].plot(epochs, history["val_loss"], marker="o", markersize=3, label=label)
    axes[0].set_xlabel("轮次")
    axes[0].set_ylabel("验证准确率（%）")
    axes[0].set_title("验证准确率")
    axes[1].set_xlabel("轮次")
    axes[1].set_ylabel("验证损失")
    axes[1].set_title("验证损失")
    for ax in axes:
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "training_curves.png", dpi=200)
    plt.close(fig)


def lstm_comparison() -> None:
    entries = []
    cnn = read_metrics("exp-cnn-05", None)
    if cnn:
        entries.append(("CNN 基线", cnn[0] * 100, "#4c72b0", False))
    for exp, label in (
        ("exp-lstm-01", "LSTM 种子 42"),
        ("exp-lstm-02", "LSTM 种子 43"),
        ("exp-lstm-03", "LSTM 种子 44"),
    ):
        value = read_metrics(exp, None)
        if value:
            entries.append((label, value[0] * 100, "#c44e52", False))
    path = ROOT / "runs/ensemble-cnn-lstm-seeds/metrics.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data.get("summary", {})
        best = summary.get("best_weight") or {}
        if best:
            entries.append(("3 种子平均 + CNN", best["accuracy"] * 100, "#c44e52", False))
    path = ROOT / "runs/cv-lstm-01/metrics.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        metrics = data.get("metrics", {})
        if metrics:
            entries.append(("LSTM 5 折 CV", metrics["accuracy"] * 100, "#8172b2", False))
    path = ROOT / "runs/ensemble-cnn-lstm/metrics.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        best = data.get("summary", {}).get("best_weight") or {}
        if best:
            entries.append(("集成（验证集选权重）", best["accuracy"] * 100, "#c44e52", True))
    if not entries:
        return
    labels = [entry[0] for entry in entries]
    values = [entry[1] for entry in entries]
    colors = [entry[2] for entry in entries]
    fig, ax = plt.subplots(figsize=(7.8, 4.2))
    bars = ax.bar(labels, values, color=colors)
    for bar, entry in zip(bars, entries):
        if entry[3]:
            bar.set_hatch("//")
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{bar.get_height():.1f}", ha="center", fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_ylabel("验证准确率（%）")
    ax.set_title("CNN + BiLSTM 种子方差（n=51）")
    ax.tick_params(axis="x", labelrotation=18, labelsize=9)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    fig.savefig(FIG_DIR / "lstm_comparison.png", dpi=200)
    plt.close(fig)


def _read_epochs(exp: str) -> list[dict]:
    path = ROOT / "runs" / exp / "epochs.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def diagnostics_plot(exp: str, title: str, output: str) -> None:
    rows = _read_epochs(exp)
    if not rows or "lr" not in rows[0] or "grad_norm" not in rows[0]:
        return
    epochs = [int(row["epoch"]) for row in rows]
    train_loss = [float(row["train_loss"]) for row in rows if row["train_loss"]]
    val_loss = [float(row["val_loss"]) for row in rows if row["val_loss"]]
    lr = [float(row["lr"]) for row in rows if row["lr"]]
    grad = [float(row["grad_norm"]) for row in rows if row["grad_norm"]]
    fig, axes = plt.subplots(2, 2, figsize=(9, 5.4))
    axes[0, 0].plot(epochs[:len(train_loss)], train_loss, label="训练损失")
    axes[0, 0].plot(epochs[:len(val_loss)], val_loss, label="验证损失")
    axes[0, 0].set_title("损失")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].plot(epochs[:len(lr)], lr, color="#4c72b0")
    axes[0, 1].set_title("学习率")
    axes[0, 1].set_ylim(0, max(lr) * 1.15 if lr else 1)
    axes[1, 0].plot(epochs[:len(grad)], grad, color="#c44e52")
    axes[1, 0].set_title("梯度范数")
    axes[1, 0].set_yscale("log")
    metric_key = "val_iou" if rows[0].get("val_iou") else "val_accuracy"
    metric = [float(row[metric_key]) for row in rows if row.get(metric_key)]
    axes[1, 1].plot(epochs[:len(metric)], metric, color="#55a868")
    axes[1, 1].set_title("验证 IoU" if metric_key == "val_iou" else "验证准确率")
    for ax in axes.flat:
        ax.set_xlabel("轮次")
        ax.grid(alpha=0.25)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(FIG_DIR / output, dpi=200)
    plt.close(fig)


def carrier_gate_curves() -> None:
    diagnostics_plot(
        "carrier-gate-01",
        "PPT / A4 纸质稿场景门控训练诊断",
        "carrier_gate_curves.png",
    )


def paper_model_curves() -> None:
    diagnostics_plot(
        "paper-cnn-01",
        "纸质稿专用内容模型训练诊断",
        "paper_model_curves.png",
    )


def screen_gate_curves() -> None:
    diagnostics_plot(
        "screen-gate-01",
        "屏幕存在性门控训练诊断（SCB + 自采 train）",
        "screen_gate_curves.png",
    )


def screen_detector_curves() -> None:
    exp = "screen-detector-02" if (ROOT / "runs/screen-detector-02/epochs.csv").is_file() else "screen-detector-01"
    diagnostics_plot(
        exp,
        "屏幕检测器训练诊断（SCB screen 框）",
        "screen_detector_curves.png",
    )


def external_comparison() -> None:
    entries = [
        ("无外部（种子 42）", "exp-cnn-05", "#4c72b0"),
        ("无外部（种子 43）", "exp-cnn-10", "#4c72b0"),
        ("外部 2400（种子 42）", "exp-cnn-ext-01", "#dd8452"),
        ("外部 600（种子 42）", "exp-cnn-ext-02", "#55a868"),
        ("外部 600（种子 43）", "exp-cnn-ext-03", "#c44e52"),
    ]
    labels, values, colors = [], [], []
    for label, exp, color in entries:
        value = read_metrics(exp, None)
        if value:
            labels.append(label)
            values.append(value[0] * 100)
            colors.append(color)
    if not values:
        return
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(labels, values, color=colors)
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{bar.get_height():.1f}", ha="center", fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_ylabel("验证准确率（%）")
    ax.set_title("外部预训练对照（自采 split_v3 验证集）")
    ax.tick_params(axis="x", labelrotation=15, labelsize=9)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(FIG_DIR / "external_comparison.png", dpi=200)
    plt.close(fig)


def main() -> int:
    model_comparison()
    corner_policy_comparison()
    confusion_panels()
    training_curves()
    lstm_comparison()
    external_comparison()
    screen_detector_curves()
    screen_gate_curves()
    carrier_gate_curves()
    paper_model_curves()
    print(f"图表写入 {FIG_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
