"""CNN 与 CNN+BiLSTM 的概率级/路由级复合评估。

只使用验证集，测试集不参与。

用法：
    PYTHONPATH=src python scripts/ensemble_cnn_lstm.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from docnorm.utils.runlog import RunLogger  # noqa: E402
from train_cnn_lstm import CnnLstm  # noqa: E402

LABELS = ["text", "formula"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cnn-run", type=Path, default=ROOT / "runs/exp-cnn-05")
    parser.add_argument(
        "--lstm-runs",
        type=Path,
        nargs="+",
        default=[ROOT / "runs/exp-lstm-01"],
        help="一个或多个 LSTM 实验；概率取平均",
    )
    parser.add_argument("--out", type=Path, default=ROOT / "runs/ensemble-cnn-lstm")
    return parser.parse_args()


def metrics(y_true, y_pred):
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
    }


def main() -> int:
    args = parse_args()
    cnn_run = args.cnn_run if args.cnn_run.is_absolute() else ROOT / args.cnn_run
    lstm_runs = [
        path if path.is_absolute() else ROOT / path for path in args.lstm_runs
    ]
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
    logger = RunLogger(
        out_dir.name,
        out_dir,
        "scripts/ensemble_cnn_lstm.py",
        args,
        config,
        root=ROOT,
        notes="CNN 与 CNN+BiLSTM 的概率平均/置信度路由；仅验证集，权重/路由在验证集上选择，结果偏乐观",
    )

    cnn_rows = {
        row["sample_id"]: row
        for row in csv.DictReader((cnn_run / "predictions_val.csv").open())
    }
    sample_ids = None
    lstm_probabilities = []
    results_base = {}
    for run in lstm_runs:
        rows = list(csv.DictReader((run / "predictions_val.csv").open()))
        run_ids = [row["sample_id"] for row in rows]
        if sample_ids is None:
            sample_ids = run_ids
        elif run_ids != sample_ids:
            raise SystemExit(f"验证集顺序不一致: {run}")
        payload = torch.load(run / "lstm.pt", map_location="cpu")
        model = CnnLstm(
            int(payload["input_dim"]),
            int(payload["hidden"]),
            float(payload["dropout"]),
        )
        model.load_state_dict(payload["state_dict"])
        model.eval()
        data = np.load(run / "sequences.npz")
        features = data["features"]
        splits = data["splits"]
        val_features = torch.from_numpy(features[splits == "val"])
        with torch.no_grad():
            logits = model(val_features)
            proba = torch.softmax(logits, dim=1).numpy()[:, 1]
        if len(proba) != len(sample_ids):
            raise SystemExit(f"LSTM 验证集数量不一致: {run} {len(proba)} vs {len(sample_ids)}")
        lstm_probabilities.append(proba)
        pred = ["formula" if value >= 0.5 else "text" for value in proba]
        results_base[run.name] = metrics(
            [cnn_rows[sample_id]["true_label"] for sample_id in sample_ids], pred
        )
    lstm_prob = np.mean(np.stack(lstm_probabilities), axis=0)
    y_true = [cnn_rows[sample_id]["true_label"] for sample_id in sample_ids]
    cnn_prob = np.array(
        [float(cnn_rows[sample_id]["prob_formula"]) for sample_id in sample_ids]
    )
    lstm_pred = ["formula" if value >= 0.5 else "text" for value in lstm_prob]
    cnn_pred = ["formula" if value >= 0.5 else "text" for value in cnn_prob]

    results = {"weights": {}, "routes": {}, "base": {}}
    results["base"]["cnn"] = metrics(y_true, cnn_pred)
    results["base"]["lstm_seeds"] = results_base
    results["base"]["lstm_average"] = metrics(y_true, lstm_pred)
    for weight in np.linspace(0, 1, 21):
        prob = weight * lstm_prob + (1 - weight) * cnn_prob
        pred = ["formula" if value >= 0.5 else "text" for value in prob]
        results["weights"][f"{weight:.2f}"] = metrics(y_true, pred)
    for threshold in np.linspace(0.5, 0.95, 19):
        # CNN 不确定时交给 LSTM
        pred = [
            lstm_pred[index]
            if abs(cnn_prob[index] - 0.5) < (threshold - 0.5)
            else cnn_pred[index]
            for index in range(len(sample_ids))
        ]
        results["routes"][f"cnn_uncertain_{threshold:.2f}"] = metrics(y_true, pred)
        # 两模型分歧且 LSTM 较自信时采用 LSTM
        pred = []
        for index in range(len(sample_ids)):
            if cnn_pred[index] == lstm_pred[index]:
                pred.append(cnn_pred[index])
            elif lstm_prob[index] >= threshold:
                pred.append("formula")
            else:
                pred.append("text")
        results["routes"][f"disagree_lstm_{threshold:.2f}"] = metrics(y_true, pred)

    best_weight = max(
        results["weights"].items(), key=lambda item: (item[1]["accuracy"], item[1]["macro_f1"])
    )
    best_route = max(
        results["routes"].items(), key=lambda item: (item[1]["accuracy"], item[1]["macro_f1"])
    )
    summary = {
        "base": results["base"],
        "best_weight": {"weight_lstm": best_weight[0], **best_weight[1]},
        "best_route": {"name": best_route[0], **best_route[1]},
    }
    (out_dir / "metrics.json").write_text(
        json.dumps({"summary": summary, "grid": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"CNN acc={results['base']['cnn']['accuracy']:.4f} "
        f"LSTM avg acc={results['base']['lstm_average']['accuracy']:.4f} "
        f"best_weight={best_weight[0]} acc={best_weight[1]['accuracy']:.4f} "
        f"best_route={best_route[0]} acc={best_route[1]['accuracy']:.4f}"
    )
    for name, value in results_base.items():
        print(f"  {name} acc={value['accuracy']:.4f}")
    logger.finish(metrics=summary, extra={"grid": results})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
