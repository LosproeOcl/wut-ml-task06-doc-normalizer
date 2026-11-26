"""CNN + BiLSTM 复合模型：把卷积特征图当作空间序列。

使用已训练 CNN 的 7×7×576 特征图，按行展开为 49 个空间 token，
经 BiLSTM 编码后做二分类。只训练序列头，不改动 CNN 主干。

用法：
    PYTHONPATH=src python scripts/train_cnn_lstm.py --cnn-run runs/exp-cnn-05
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.annotations import (  # noqa: E402
    ManualCornerStore,
    ManualLabelStore,
    scale_points,
)
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, check_manifest_hash, load_split  # noqa: E402
from docnorm.enhance.clahe import enhance_document  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402
from docnorm.rectify.geometry import DocumentQuad, RectifyError  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402
from docnorm.utils.runlog import RunLogger  # noqa: E402


class CnnLstm(nn.Module):
    def __init__(self, input_dim: int, hidden: int = 128, dropout: float = 0.3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_dim, hidden, batch_first=True, bidirectional=True
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden * 2, 2)

    def forward(self, sequence: torch.Tensor) -> torch.Tensor:
        output, _ = self.lstm(sequence)
        pooled = output.mean(dim=1)
        return self.fc(self.dropout(pooled))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cnn-run", type=Path, default=ROOT / "runs/exp-cnn-05")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--split", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--hidden", type=int, default=128)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-3)
    parser.add_argument("--feature-noise", type=float, default=0.0)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-rectify", action="store_true")
    parser.add_argument("--enhance", action="store_true")
    return parser.parse_args()


def load_items(config: dict, split_path: Path):
    samples = load_manifest(
        ROOT / config["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(split_path)
    check_manifest_hash(split, ROOT / config["data"]["manifest"])
    assignment = assign_samples(split, samples)
    labels = ManualLabelStore(ROOT / "data/annotations/manual_labels.csv").load()
    corners = ManualCornerStore(ROOT / "data/annotations/manual_corners.csv").load()
    items = []
    for sample in samples:
        name = assignment.get(sample.sample_id)
        if name not in {"train", "val"}:
            continue
        label = labels.get(sample.sample_id, sample.content_label) if name == "train" else sample.content_label
        if label is None:
            continue
        items.append(
            {
                "sample_id": sample.sample_id,
                "file": sample.file,
                "label": label,
                "split": name,
                "corners": corners.get(sample.sample_id) if name == "train" else None,
            }
        )
    return items


def rectify_image(image, config, corners, original_size, *, rectify: bool, enhance: bool):
    if rectify:
        quad = detect_document(
            image,
            canny_low=int(config["rectify"]["canny_low"]),
            canny_high=int(config["rectify"]["canny_high"]),
            min_area_ratio=float(config["rectify"]["min_area_ratio"]),
            max_area_ratio=float(config["rectify"]["max_area_ratio"]),
        )
        if quad is None and corners is not None:
            try:
                points = scale_points(corners, original_size, image.shape)
                quad = DocumentQuad(np.asarray(points, dtype=np.float32))
            except (RectifyError, ValueError):
                quad = None
        if quad is not None:
            image = warp_document(
                image,
                quad,
                output_long_edge=int(config["rectify"]["output_long_edge"]),
            )
    if enhance:
        image = enhance_document(
            image,
            clip_limit=float(config["enhance"]["clahe_clip"]),
            tile_grid_size=int(config["enhance"]["clahe_grid"]),
            correct_shadows=bool(config["enhance"]["correct_shadows"]),
            shadow_kernel=int(config["enhance"]["shadow_kernel"]),
            shadow_strength=float(config["enhance"]["shadow_strength"]),
            denoise=bool(config["enhance"]["denoise"]),
        )
    return image


def extract_sequence(classifier: CnnClassifier, image: np.ndarray) -> np.ndarray:
    tensor = classifier._prepare(image).unsqueeze(0)
    with torch.no_grad():
        feature_map = classifier.model.features(tensor)
        # (1, C, H, W) -> (H*W, C)
        sequence = feature_map.flatten(2).squeeze(0).transpose(0, 1)
    return sequence.cpu().numpy()


def evaluate(model, loader, device):
    model.eval()
    predictions = []
    labels = []
    probabilities = []
    loss_total = 0.0
    criterion = nn.CrossEntropyLoss()
    with torch.no_grad():
        for batch, target in loader:
            batch, target = batch.to(device), target.to(device)
            logits = model(batch)
            loss_total += float(criterion(logits, target)) * len(target)
            probabilities.extend(torch.softmax(logits, dim=1).cpu().tolist())
            predictions.extend(logits.argmax(dim=1).cpu().tolist())
            labels.extend(target.cpu().tolist())
    return loss_total / max(len(labels), 1), predictions, labels, probabilities


def main() -> int:
    args = parse_args()
    torch.set_num_threads(4)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    split_path = args.split or ROOT / config["data"]["split"]
    cnn_run = args.cnn_run if args.cnn_run.is_absolute() else ROOT / args.cnn_run
    out_dir = args.out or (ROOT / "runs" / "exp-lstm-01")
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(
        out_dir.name,
        out_dir,
        "scripts/train_cnn_lstm.py",
        args,
        config,
        root=ROOT,
        notes="CNN 特征图 + BiLSTM 空间序列；仅训练序列头",
    )
    logger.log(f"实验 {out_dir.name} 开始")

    classifier = CnnClassifier.load(cnn_run / "cnn.pt", device="cpu")
    classifier.model.eval()
    items = load_items(config, split_path)
    sequences = []
    labels = []
    splits = []
    for index, item in enumerate(items, start=1):
        loaded = load_image(
            ROOT / config["data"]["raw_dir"] / item["file"],
            max_long_edge=int(config["data"]["image_size"]),
        )
        image = rectify_image(
            loaded.image,
            config,
            item["corners"],
            loaded.original_size,
            rectify=not args.no_rectify,
            enhance=args.enhance,
        )
        sequences.append(extract_sequence(classifier, image))
        labels.append(CLASSES.index(item["label"]))
        splits.append(item["split"])
        if index % 50 == 0:
            print(f"序列 {index}/{len(items)}", flush=True)

    lengths = {sequence.shape[0] for sequence in sequences}
    if len(lengths) != 1:
        raise SystemExit(f"序列长度不一致: {lengths}")
    features = np.stack(sequences).astype(np.float32)
    labels = np.asarray(labels, dtype=np.int64)
    splits = np.asarray(splits)
    train_mask = splits == "train"
    val_mask = splits == "val"
    feature_mean = features[train_mask].mean(axis=(0, 1), keepdims=True)
    feature_std = features[train_mask].std(axis=(0, 1), keepdims=True) + 1e-6
    features = (features - feature_mean) / feature_std
    np.savez_compressed(
        out_dir / "sequences.npz",
        features=features,
        labels=labels,
        splits=splits,
    )

    train_dataset = TensorDataset(
        torch.from_numpy(features[train_mask]),
        torch.from_numpy(labels[train_mask]),
    )
    val_dataset = TensorDataset(
        torch.from_numpy(features[val_mask]),
        torch.from_numpy(labels[val_mask]),
    )
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False)

    counts = np.bincount(labels[train_mask], minlength=2)
    class_weights = torch.tensor(
        counts.sum() / (2.0 * np.maximum(counts, 1)), dtype=torch.float32
    )
    model = CnnLstm(features.shape[2], hidden=args.hidden, dropout=args.dropout)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    best_accuracy = -1.0
    best_state = None
    stale = 0
    history = {"train_loss": [], "val_loss": [], "val_accuracy": []}

    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for batch, target in train_loader:
            if args.feature_noise > 0:
                batch = batch + torch.randn_like(batch) * args.feature_noise
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch)
            loss = criterion(logits, target)
            loss.backward()
            optimizer.step()
            running += float(loss.item()) * len(target)
        train_loss = running / len(train_dataset)
        val_loss, predictions, truths, _ = evaluate(model, val_loader, torch.device("cpu"))
        val_accuracy = accuracy_score(truths, predictions)
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_accuracy"].append(val_accuracy)
        logger.log_epoch(
            epoch,
            train_loss=train_loss,
            val_loss=val_loss,
            val_accuracy=val_accuracy,
        )
        if val_accuracy > best_accuracy:
            best_accuracy = val_accuracy
            best_state = {key: value.clone() for key, value in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= args.patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    val_loss, predictions, truths, probabilities = evaluate(model, val_loader, torch.device("cpu"))
    true_labels = [CLASSES[index] for index in truths]
    pred_labels = [CLASSES[index] for index in predictions]
    metrics = {
        "accuracy": float(accuracy_score(true_labels, pred_labels)),
        "macro_f1": float(f1_score(true_labels, pred_labels, average="macro")),
        "confusion_matrix": confusion_matrix(
            true_labels, pred_labels, labels=list(CLASSES)
        ).tolist(),
    }
    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_dim": features.shape[2],
            "hidden": args.hidden,
            "dropout": args.dropout,
            "classes": CLASSES,
        },
        out_dir / "lstm.pt",
    )
    with (out_dir / "predictions_val.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["sample_id", "true_label", "pred_label", "prob_text", "prob_formula"]
        )
        val_items = [item for item in items if item["split"] == "val"]
        for item, true_label, pred_label, probability in zip(
            val_items, true_labels, pred_labels, probabilities
        ):
            writer.writerow(
                [
                    item["sample_id"],
                    true_label,
                    pred_label,
                    float(probability[0]),
                    float(probability[1]),
                ]
            )
    result = {
        "exp_id": out_dir.name,
        "cnn_run": cnn_run.name,
        "split": split_path.name,
        "n_train": int(train_mask.sum()),
        "n_val": int(val_mask.sum()),
        "sequence_length": int(features.shape[1]),
        "input_dim": int(features.shape[2]),
        "hidden": args.hidden,
        "dropout": args.dropout,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "feature_noise": args.feature_noise,
        "epochs": len(history["train_loss"]),
        "metrics": metrics,
        "history": history,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"accuracy={metrics['accuracy']:.4f} macro_f1={metrics['macro_f1']:.4f} "
        f"confusion={metrics['confusion_matrix']}"
    )
    logger.finish(metrics=metrics, extra=result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
