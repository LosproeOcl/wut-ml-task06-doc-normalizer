"""CNN+BiLSTM 的 5 折交叉验证集成。

训练集做 5 折，每折用其余 4 折训练、留出折早停；5 个折模型对验证集
概率取平均。验证集不再参与早停，减少“挑峰值”偏差。

用法：
    PYTHONPATH=src python scripts/cv_lstm.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from docnorm.utils.runlog import RunLogger  # noqa: E402
from train_cnn_lstm import CnnLstm  # noqa: E402

LABELS = ["text", "formula"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequences", type=Path, default=ROOT / "runs/exp-lstm-01/sequences.npz")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/cv-lstm-01")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--dropout", type=float, default=0.5)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-2)
    parser.add_argument("--feature-noise", type=float, default=0.05)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def metrics(y_true, y_pred):
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
    }


def train_fold(x_train, y_train, x_hold, y_hold, args, seed):
    torch.manual_seed(seed)
    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train)),
        batch_size=args.batch_size,
        shuffle=True,
    )
    hold_loader = DataLoader(
        TensorDataset(torch.from_numpy(x_hold), torch.from_numpy(y_hold)),
        batch_size=args.batch_size,
        shuffle=False,
    )
    counts = np.bincount(y_train, minlength=2)
    class_weights = torch.tensor(
        counts.sum() / (2.0 * np.maximum(counts, 1)), dtype=torch.float32
    )
    model = CnnLstm(x_train.shape[2], hidden=args.hidden, dropout=args.dropout)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    best_accuracy = -1.0
    best_state = None
    stale = 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        for batch, target in train_loader:
            if args.feature_noise > 0:
                batch = batch + torch.randn_like(batch) * args.feature_noise
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(batch), target)
            loss.backward()
            optimizer.step()
        model.eval()
        predictions = []
        truths = []
        with torch.no_grad():
            for batch, target in hold_loader:
                predictions.extend(model(batch).argmax(dim=1).tolist())
                truths.extend(target.tolist())
        accuracy = accuracy_score(truths, predictions)
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_state = {key: value.clone() for key, value in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= args.patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, float(best_accuracy)


def main() -> int:
    args = parse_args()
    torch.set_num_threads(4)
    config = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(
        out_dir.name,
        out_dir,
        "scripts/cv_lstm.py",
        args,
        config,
        root=ROOT,
        notes="CNN+BiLSTM 5 折集成；验证集不参与早停",
    )
    data = np.load(args.sequences)
    features = data["features"]
    labels = data["labels"]
    splits = data["splits"]
    x_train_all = features[splits == "train"]
    y_train_all = labels[splits == "train"]
    x_val = torch.from_numpy(features[splits == "val"])
    y_val = labels[splits == "val"]

    fold_predictions = []
    fold_rows = []
    splitter = StratifiedKFold(
        n_splits=args.folds, shuffle=True, random_state=args.seed
    )
    for fold, (train_index, hold_index) in enumerate(
        splitter.split(x_train_all, y_train_all), start=1
    ):
        model, hold_accuracy = train_fold(
            x_train_all[train_index],
            y_train_all[train_index],
            x_train_all[hold_index],
            y_train_all[hold_index],
            args,
            seed=args.seed + fold,
        )
        model.eval()
        with torch.no_grad():
            probabilities = torch.softmax(model(x_val), dim=1).numpy()
        predictions = probabilities.argmax(axis=1)
        fold_metrics = metrics([LABELS[index] for index in y_val], [LABELS[index] for index in predictions])
        fold_predictions.append(probabilities[:, 1])
        fold_rows.append(
            {
                "fold": fold,
                "hold_accuracy": round(hold_accuracy, 4),
                "val_accuracy": round(fold_metrics["accuracy"], 4),
                "val_macro_f1": round(fold_metrics["macro_f1"], 4),
            }
        )
        logger.log(
            f"fold {fold} hold_acc={hold_accuracy:.4f} "
            f"val_acc={fold_metrics['accuracy']:.4f}"
        )

    mean_probability = np.mean(np.stack(fold_predictions), axis=0)
    predictions = (mean_probability >= 0.5).astype(int)
    true_labels = [LABELS[index] for index in y_val]
    pred_labels = [LABELS[index] for index in predictions]
    result_metrics = metrics(true_labels, pred_labels)
    result = {
        "exp_id": out_dir.name,
        "sequences": str(args.sequences),
        "folds": args.folds,
        "hidden": args.hidden,
        "dropout": args.dropout,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "feature_noise": args.feature_noise,
        "metrics": result_metrics,
        "folds_detail": fold_rows,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sample_ids = []
    source_predictions = Path(args.sequences).parent / "predictions_val.csv"
    if source_predictions.is_file():
        sample_ids = [
            row["sample_id"] for row in csv.DictReader(source_predictions.open())
        ]
    if len(sample_ids) != len(true_labels):
        sample_ids = [str(index) for index in range(len(true_labels))]
    with (out_dir / "predictions_val.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "true_label", "pred_label", "prob_formula"])
        for sample_id, true_label, pred_label, probability in zip(
            sample_ids, true_labels, pred_labels, mean_probability
        ):
            writer.writerow([sample_id, true_label, pred_label, float(probability)])
    print(
        f"CV ensemble accuracy={result_metrics['accuracy']:.4f} "
        f"macro_f1={result_metrics['macro_f1']:.4f} "
        f"confusion={result_metrics['confusion_matrix']}"
    )
    logger.finish(metrics=result_metrics, extra=result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
