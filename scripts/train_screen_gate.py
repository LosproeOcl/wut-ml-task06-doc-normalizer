"""训练“是否为投影幕布”二分类门控。

输入整图，输出 screen / other 概率；用于决定自动四角失败时是否启用
SCB 屏幕框裁剪。训练集为 SCB 正负样本 + 自采 train 的 ppt/paper，
自采 val 不参与训练。

用法：
    PYTHONPATH=src python scripts/train_screen_gate.py
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import yaml
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from torch.utils.data import DataLoader, Dataset
from torchvision import models

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.loader import load_image  # noqa: E402
from docnorm.utils.runlog import RunLogger  # noqa: E402

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
CLASSES = ("other", "screen")


class GateDataset(Dataset):
    def __init__(self, rows, input_size: int, train: bool):
        self.rows = rows
        self.input_size = input_size
        self.train = train

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        loaded = load_image(ROOT / row["path"], max_long_edge=512)
        image = cv2.resize(
            loaded.image, (self.input_size, self.input_size), interpolation=cv2.INTER_AREA
        )
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if self.train and random.random() < 0.5:
            image = image[:, ::-1, :].copy()
        if self.train and random.random() < 0.5:
            factor = random.uniform(0.85, 1.15)
            image = np.clip(image.astype(np.float32) * factor, 0, 255).astype(np.uint8)
        tensor = torch.from_numpy(image).permute(2, 0, 1).float() / 255.0
        mean = torch.tensor(MEAN).view(3, 1, 1)
        std = torch.tensor(STD).view(3, 1, 1)
        tensor = (tensor - mean) / std
        return tensor, torch.tensor(CLASSES.index(row["label"]), dtype=torch.long)


class ScreenGate(nn.Module):
    def __init__(self, pretrained: bool = True):
        super().__init__()
        weights = models.MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
        base = models.mobilenet_v3_small(weights=weights)
        self.features = base.features
        self.avgpool = base.avgpool
        self.head = nn.Sequential(
            nn.Linear(576, 256),
            nn.Hardswish(),
            nn.Dropout(0.2),
            nn.Linear(256, 2),
        )

    def forward(self, images):
        features = self.features(images)
        pooled = self.avgpool(features)
        return self.head(torch.flatten(pooled, 1))


def evaluate(model, loader):
    model.eval()
    predictions = []
    labels = []
    loss_total = 0.0
    criterion = nn.CrossEntropyLoss()
    with torch.no_grad():
        for images, targets in loader:
            logits = model(images)
            loss_total += float(criterion(logits, targets)) * len(targets)
            predictions.extend(logits.argmax(dim=1).tolist())
            labels.extend(targets.tolist())
    return (
        loss_total / max(len(labels), 1),
        float(accuracy_score(labels, predictions)),
        float(f1_score(labels, predictions, average="macro", zero_division=0)),
        confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/screen_gate.csv")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/screen-gate-01")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--freeze-epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--input-size", type=int, default=160)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(4)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(args.manifest.open(encoding="utf-8")))
    train_rows = [row for row in rows if row["split"] == "train"]
    val_rows = [row for row in rows if row["split"] == "val"]
    if not train_rows or not val_rows:
        raise SystemExit(f"训练/验证为空: {len(train_rows)}/{len(val_rows)}")
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(
        out_dir.name,
        out_dir,
        "scripts/train_screen_gate.py",
        args,
        config,
        root=ROOT,
        notes="是否为投影幕布的置信门控；SCB + 自采 train，val 不参与训练",
    )
    logger.log(f"屏幕门控训练开始，train={len(train_rows)} val={len(val_rows)}")

    train_loader = DataLoader(
        GateDataset(train_rows, args.input_size, train=True),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
    )
    val_loader = DataLoader(
        GateDataset(val_rows, args.input_size, train=False),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )
    model = ScreenGate(pretrained=True)
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=1e-3, weight_decay=1e-4)
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    counts = np.bincount([CLASSES.index(row["label"]) for row in train_rows], minlength=2)
    class_weights = torch.tensor(
        counts.sum() / (2.0 * np.maximum(counts, 1)), dtype=torch.float32
    )
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    best_accuracy = -1.0
    best_state = None
    stale = 0
    history = {"train_loss": [], "val_loss": [], "val_accuracy": [], "val_f1": []}
    for epoch in range(1, args.epochs + 1):
        if epoch == args.freeze_epochs + 1:
            for parameter in model.features.parameters():
                parameter.requires_grad = True
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
        model.train()
        running = 0.0
        grad_total = 0.0
        grad_batches = 0
        for images, targets in train_loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = criterion(logits, targets)
            loss.backward()
            grad_sq = sum(
                float(parameter.grad.detach().pow(2).sum().item())
                for parameter in model.parameters()
                if parameter.grad is not None
            )
            grad_total += grad_sq ** 0.5
            grad_batches += 1
            optimizer.step()
            running += float(loss.item()) * len(targets)
        train_loss = running / len(train_rows)
        val_loss, accuracy, macro_f1, confusion = evaluate(model, val_loader)
        lr = float(optimizer.param_groups[0]["lr"])
        param_norm = sum(
            float(parameter.detach().pow(2).sum().item())
            for parameter in model.parameters()
        ) ** 0.5
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_accuracy"].append(accuracy)
        history["val_f1"].append(macro_f1)
        logger.log_epoch(
            epoch,
            train_loss=train_loss,
            val_loss=val_loss,
            val_accuracy=accuracy,
            lr=lr,
            grad_norm=grad_total / max(grad_batches, 1),
            param_norm=param_norm,
        )
        logger.log(
            f"epoch {epoch} train={train_loss:.4f} val={val_loss:.4f} "
            f"acc={accuracy:.4f} f1={macro_f1:.4f} conf={confusion}"
        )
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
    val_loss, accuracy, macro_f1, confusion = evaluate(model, val_loader)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_size": args.input_size,
            "classes": CLASSES,
            "source": "SCB-screen + self-train-ppt/paper",
        },
        out_dir / "screen_gate.pt",
    )
    result = {
        "exp_id": out_dir.name,
        "manifest": str(args.manifest),
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "input_size": args.input_size,
        "epochs": len(history["train_loss"]),
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "confusion_matrix": confusion,
        "history": history,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"screen gate acc={accuracy:.4f} f1={macro_f1:.4f} conf={confusion}")
    logger.finish(
        metrics={"accuracy": accuracy, "macro_f1": macro_f1},
        extra={
            **result,
            "loss": "CrossEntropyLoss(weight=class_weights)",
            "optimizer": "AdamW",
            "lr_head": 1e-3,
            "lr_finetune": 1e-4,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
