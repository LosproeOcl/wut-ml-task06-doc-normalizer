"""在 SCB-Dataset 的 screen 框上训练轻量投影幕布检测器。

输出归一化 bbox（cx, cy, w, h 转 xyxy），供分类前的屏幕裁剪兜底使用。
外部数据只用于屏幕定位，不进入文字/公式分类评估。

用法：
    PYTHONPATH=src python scripts/train_screen_detector.py \
      --manifest data/manifests/scb_screen.csv --out runs/screen-detector-01
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
import torch.nn.functional as F
import yaml
from torch.utils.data import DataLoader, Dataset
from torchvision import models

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.loader import load_image  # noqa: E402
from docnorm.utils.runlog import RunLogger  # noqa: E402

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class ScreenDataset(Dataset):
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
        box = np.array(
            [float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])],
            dtype=np.float32,
        )
        if self.train and random.random() < 0.5:
            image = image[:, ::-1, :].copy()
            box = np.array([1.0 - box[2], box[1], 1.0 - box[0], box[3]], dtype=np.float32)
        if self.train and random.random() < 0.5:
            factor = random.uniform(0.85, 1.15)
            image = np.clip(image.astype(np.float32) * factor, 0, 255).astype(np.uint8)
        tensor = torch.from_numpy(image).permute(2, 0, 1).float() / 255.0
        mean = torch.tensor(MEAN).view(3, 1, 1)
        std = torch.tensor(STD).view(3, 1, 1)
        tensor = (tensor - mean) / std
        return tensor, torch.from_numpy(box)


class ScreenRegressor(nn.Module):
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
            nn.Linear(256, 4),
            nn.Sigmoid(),
        )
        with torch.no_grad():
            self.head[-2].bias.copy_(torch.tensor([0.0, 0.0, -0.5, -0.5]))
            self.head[-2].weight.mul_(0.1)

    def forward(self, images):
        features = self.features(images)
        pooled = self.avgpool(features)
        vector = torch.flatten(pooled, 1)
        raw = self.head(vector)
        cx, cy, width, height = raw.unbind(dim=1)
        x1 = (cx - width / 2).clamp(0, 1)
        y1 = (cy - height / 2).clamp(0, 1)
        x2 = (cx + width / 2).clamp(0, 1)
        y2 = (cy + height / 2).clamp(0, 1)
        return torch.stack([x1, y1, x2, y2], dim=1)


def box_iou(pred, target):
    inter_x1 = torch.maximum(pred[:, 0], target[:, 0])
    inter_y1 = torch.maximum(pred[:, 1], target[:, 1])
    inter_x2 = torch.minimum(pred[:, 2], target[:, 2])
    inter_y2 = torch.minimum(pred[:, 3], target[:, 3])
    inter = (inter_x2 - inter_x1).clamp(min=0) * (inter_y2 - inter_y1).clamp(min=0)
    area_pred = (pred[:, 2] - pred[:, 0]).clamp(min=0) * (pred[:, 3] - pred[:, 1]).clamp(min=0)
    area_target = (target[:, 2] - target[:, 0]).clamp(min=0) * (target[:, 3] - target[:, 1]).clamp(min=0)
    union = area_pred + area_target - inter
    return inter / union.clamp(min=1e-6)


def evaluate(model, loader):
    model.eval()
    losses = []
    ious = []
    centers = []
    with torch.no_grad():
        for images, boxes in loader:
            pred = model(images)
            loss = F.smooth_l1_loss(pred, boxes) + (1 - box_iou(pred, boxes)).mean()
            losses.append(float(loss) * len(images))
            iou = box_iou(pred, boxes)
            ious.extend(iou.tolist())
            centers.extend(
                (
                    (pred[:, 0] + pred[:, 2]) / 2 - (boxes[:, 0] + boxes[:, 2]) / 2
                ).abs().tolist()
            )
    count = max(len(ious), 1)
    ious_tensor = torch.tensor(ious)
    return (
        sum(losses) / count,
        float(ious_tensor.mean()),
        float((ious_tensor >= 0.5).float().mean()),
        float(np.mean(centers)) if centers else 1.0,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/scb_screen.csv")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/screen-detector-01")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--freeze-epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--input-size", type=int, default=224)
    parser.add_argument("--max-train", type=int, default=1200)
    parser.add_argument("--max-val", type=int, default=400)
    parser.add_argument("--patience", type=int, default=5)
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
    random.Random(args.seed).shuffle(train_rows)
    random.Random(args.seed + 1).shuffle(val_rows)
    train_rows = train_rows[: args.max_train]
    val_rows = val_rows[: args.max_val]
    if not train_rows or not val_rows:
        raise SystemExit(f"训练/验证为空: {len(train_rows)}/{len(val_rows)}")

    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(
        out_dir.name,
        out_dir,
        "scripts/train_screen_detector.py",
        args,
        config,
        root=ROOT,
        notes="SCB-Dataset screen 框上的轻量屏幕检测器；仅用于分类前裁剪",
    )
    logger.log(f"屏幕检测训练开始，train={len(train_rows)} val={len(val_rows)}")

    train_loader = DataLoader(
        ScreenDataset(train_rows, args.input_size, train=True),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
    )
    val_loader = DataLoader(
        ScreenDataset(val_rows, args.input_size, train=False),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )
    model = ScreenRegressor(pretrained=True)
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=1e-3, weight_decay=1e-4)
    for parameter in model.features.parameters():
        parameter.requires_grad = False

    best_iou = -1.0
    best_state = None
    stale = 0
    history = {"train_loss": [], "val_loss": [], "val_iou": [], "val_recall": []}
    for epoch in range(1, args.epochs + 1):
        if epoch == args.freeze_epochs + 1:
            for parameter in model.features.parameters():
                parameter.requires_grad = True
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
        model.train()
        running = 0.0
        grad_total = 0.0
        grad_batches = 0
        for images, boxes in train_loader:
            optimizer.zero_grad(set_to_none=True)
            pred = model(images)
            loss = F.smooth_l1_loss(pred, boxes) + (1 - box_iou(pred, boxes)).mean()
            loss.backward()
            grad_sq = sum(
                float(parameter.grad.detach().pow(2).sum().item())
                for parameter in model.parameters()
                if parameter.grad is not None
            )
            grad_total += grad_sq ** 0.5
            grad_batches += 1
            optimizer.step()
            running += float(loss.item()) * len(images)
        train_loss = running / len(train_rows)
        grad_norm = grad_total / max(grad_batches, 1)
        lr = float(optimizer.param_groups[0]["lr"])
        param_norm = sum(
            float(parameter.detach().pow(2).sum().item())
            for parameter in model.parameters()
        ) ** 0.5
        val_loss, val_iou, recall, center_error = evaluate(model, val_loader)
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_iou"].append(val_iou)
        history["val_recall"].append(recall)
        logger.log_epoch(
            epoch,
            train_loss=train_loss,
            val_loss=val_loss,
            val_accuracy=recall,
            val_iou=val_iou,
            lr=lr,
            grad_norm=grad_norm,
            param_norm=param_norm,
        )
        logger.log(
            f"epoch {epoch} train={train_loss:.4f} val={val_loss:.4f} "
            f"iou={val_iou:.4f} recall@0.5={recall:.4f} center={center_error:.4f}"
        )
        if val_iou > best_iou:
            best_iou = val_iou
            best_state = {key: value.clone() for key, value in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= args.patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    val_loss, val_iou, recall, center_error = evaluate(model, val_loader)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_size": args.input_size,
            "architecture": "mobilenet_v3_small_screen_regressor",
            "source": "SCB-Dataset-teacher/screen",
        },
        out_dir / "screen_detector.pt",
    )
    result = {
        "exp_id": out_dir.name,
        "manifest": str(args.manifest),
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "input_size": args.input_size,
        "epochs": len(history["train_loss"]),
        "val_iou": val_iou,
        "val_recall_iou50": recall,
        "val_center_error": center_error,
        "history": history,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"screen detector IoU={val_iou:.4f} recall@0.5={recall:.4f} "
        f"center_error={center_error:.4f}"
    )
    logger.finish(
        metrics={"val_iou": val_iou, "val_recall_iou50": recall},
        extra={
            **result,
            "loss": "SmoothL1(xyxy) + (1 - IoU)",
            "optimizer": "AdamW",
            "lr_head": 1e-3,
            "lr_finetune": 1e-4,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
