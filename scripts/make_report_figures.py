"""生成课程报告用的模型对比图。

用法：
    PYTHONPATH=src python scripts/make_report_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "reports/figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

MODELS = [
    ("SVM (auto)", "exp-20261126-08", "svm", "#4c72b0"),
    ("Random Forest (auto)", "exp-20261126-08", "rf", "#4c72b0"),
    ("CNN (auto)", "exp-cnn-04", None, "#dd8452"),
    ("CNN (manual always)", "exp-cnn-03", None, "#dd8452"),
    ("CNN (manual fallback)", "exp-cnn-05", None, "#dd8452"),
    ("CNN 320 / mild", "exp-cnn-06", None, "#dd8452"),
    ("CNN EfficientNet-B0", "exp-cnn-07", None, "#dd8452"),
    ("CNN MobileNetV3-L", "exp-cnn-08", None, "#dd8452"),
    ("CNN MobileNetV3-L tuned", "exp-cnn-09", None, "#dd8452"),
    ("Fusion (classic + CNN)", "fusion-exp-01", "fusion_svm", "#8172b2"),
    ("CNN + BiLSTM (best seed)", "exp-lstm-01", None, "#c44e52"),
    ("GA feature selection + SVM", "ga-feature-01", None, "#8172b2"),
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
    ax.barh(y - height / 2, accuracy, height, label="Accuracy", color="#4c72b0")
    ax.barh(y + height / 2, f1, height, label="Macro F1", color="#55a868")
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Validation score (%)")
    ax.set_title("Model comparison on split_v3 validation (n=51)")
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
    policies = ["none", "fallback", "always"]
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
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Manual-corner training policy (split_v3 validation)")
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
        ("SVM (auto, none)", "exp-20261126-08", "svm"),
        ("CNN (manual fallback)", "exp-cnn-05", None),
        ("Fusion (classic + CNN)", "fusion-exp-01", "fusion_svm"),
        ("CNN + BiLSTM (seed 42)", "exp-lstm-01", None),
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
        ax.set_xticks([0, 1], ["text", "formula"])
        ax.set_yticks([0, 1], ["text", "formula"])
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
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
        ("exp-cnn-04", "auto"),
        ("exp-cnn-05", "fallback"),
        ("exp-cnn-06", "320 mild"),
        ("exp-cnn-07", "EfficientNet-B0"),
        ("exp-cnn-08", "MobileNetV3-L"),
        ("exp-cnn-09", "MobileNetV3-L tuned"),
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
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Validation accuracy (%)")
    axes[0].set_title("Validation accuracy")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Validation loss")
    axes[1].set_title("Validation loss")
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
        entries.append(("CNN baseline", cnn[0] * 100, "#4c72b0", False))
    for exp, label in (
        ("exp-lstm-01", "LSTM seed 42"),
        ("exp-lstm-02", "LSTM seed 43"),
        ("exp-lstm-03", "LSTM seed 44"),
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
            entries.append(("3-seed avg + CNN", best["accuracy"] * 100, "#c44e52", False))
    path = ROOT / "runs/cv-lstm-01/metrics.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        metrics = data.get("metrics", {})
        if metrics:
            entries.append(("LSTM 5-fold CV", metrics["accuracy"] * 100, "#8172b2", False))
    path = ROOT / "runs/ensemble-cnn-lstm/metrics.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        best = data.get("summary", {}).get("best_weight") or {}
        if best:
            entries.append(("Ensemble (val-selected)", best["accuracy"] * 100, "#c44e52", True))
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
    ax.set_ylabel("Validation accuracy (%)")
    ax.set_title("CNN + BiLSTM seed variance (n=51)")
    ax.tick_params(axis="x", labelrotation=15)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "lstm_comparison.png", dpi=200)
    plt.close(fig)


def main() -> int:
    model_comparison()
    corner_policy_comparison()
    confusion_panels()
    training_curves()
    lstm_comparison()
    print(f"图表写入 {FIG_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
