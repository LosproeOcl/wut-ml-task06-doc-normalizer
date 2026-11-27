"""用训练集人工四角标签训练指定载体的四角回归器。

默认训练 PPT 幕布样本；加 --carrier paper 可训练纸质/板书专用模型。
按 doc_page_id 分组切分内部 train/val，避免同一页跨集合。
输出归一化四角坐标 (x1,y1,...,x4,y4)，供后续 ROI/关键点拉正实验使用。

用法：
    PYTHONPATH=src python3 scripts/train_ppt_quad.py
    PYTHONPATH=src python3 scripts/train_ppt_quad.py --carrier paper --out runs/quad-paper-01
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.annotations import ManualCornerStore, scale_points  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class QuadDataset(Dataset):
    def __init__(self, items, input_size: int, train: bool):
        self.items = items
        self.input_size = input_size
        self.train = train
        self.color = transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.05)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        item = self.items[index]
        loaded = load_image(ROOT / "data/raw_samples" / item["file"], max_long_edge=1280)
        image = loaded.image
        points = scale_points(item["points"], loaded.original_size, image.shape)
        height, width = image.shape[:2]
        points = np.asarray(points, dtype=np.float32) / np.array([width, height], dtype=np.float32)
        image = cv2.resize(image, (self.input_size, self.input_size), interpolation=cv2.INTER_AREA)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if self.train:
            from PIL import Image

            image = np.asarray(self.color(Image.fromarray(image)), dtype=np.uint8)
        tensor = torch.from_numpy(image).permute(2, 0, 1).float() / 255.0
        mean = torch.tensor(MEAN).view(3, 1, 1)
        std = torch.tensor(STD).view(3, 1, 1)
        return (tensor - mean) / std, torch.from_numpy(points.reshape(-1))


class QuadNet(nn.Module):
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
            nn.Linear(256, 8),
            nn.Sigmoid(),
        )

    def forward(self, images):
        features = self.features(images)
        return self.head(torch.flatten(self.avgpool(features), 1))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--carrier", choices=("ppt", "paper", "all"), default="ppt"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "runs/quad-ppt-01")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--freeze-epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--input-size", type=int, default=224)
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(4)
    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    assignment = assign_samples(load_split(ROOT / "data/splits/split_v4.json"), samples)
    corners = ManualCornerStore(ROOT / "data/annotations/manual_corners.csv").load()
    by_group: dict[str, list] = defaultdict(list)
    for sample in samples:
        if args.carrier != "all" and not (sample.label or "").startswith(
            args.carrier + "_"
        ):
            continue
        if assignment.get(sample.sample_id) != "train":
            continue
        if sample.sample_id not in corners:
            continue
        by_group[sample.doc_page_id].append(sample)
    groups = sorted(by_group)
    rng = random.Random(args.seed)
    rng.shuffle(groups)
    val_groups = set(groups[: max(1, round(len(groups) * 0.2))])
    train_items, val_items = [], []
    for group, members in by_group.items():
        target = val_items if group in val_groups else train_items
        for sample in members:
            target.append({"sample_id": sample.sample_id, "file": sample.file, "points": corners[sample.sample_id]})
    print(
        f"{args.carrier} 四角标签 train={len(train_items)} val={len(val_items)} "
        f"groups={len(groups)} val_groups={len(val_groups)}"
    )
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    train_loader = DataLoader(QuadDataset(train_items, args.input_size, True), batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(QuadDataset(val_items, args.input_size, False), batch_size=args.batch_size, shuffle=False, num_workers=0)
    model = QuadNet(pretrained=True)
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=1e-3, weight_decay=1e-4)
    for parameter in model.features.parameters():
        parameter.requires_grad = False
    best = 1e9
    best_state = None
    stale = 0
    history = []
    for epoch in range(1, args.epochs + 1):
        if epoch == args.freeze_epochs + 1:
            for parameter in model.features.parameters():
                parameter.requires_grad = True
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
        model.train()
        total = 0.0
        for images, targets in train_loader:
            optimizer.zero_grad(set_to_none=True)
            loss = F.smooth_l1_loss(model(images), targets)
            loss.backward()
            optimizer.step()
            total += float(loss) * len(images)
        model.eval()
        errors = []
        with torch.no_grad():
            for images, targets in val_loader:
                pred = model(images)
                errors.extend(torch.linalg.vector_norm(pred - targets, dim=1).tolist())
        mean_error = float(np.mean(errors)) if errors else 1.0
        history.append({"epoch": epoch, "train_loss": total / max(1, len(train_loader.dataset)), "val_mean_l2": mean_error})
        print(f"epoch {epoch} train={history[-1]['train_loss']:.4f} val_l2={mean_error:.4f}")
        if mean_error < best:
            best = mean_error
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= args.patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    torch.save({"state_dict": model.state_dict(), "input_size": args.input_size}, out_dir / "quad_ppt.pt")
    (out_dir / "metrics.json").write_text(json.dumps({"n_train": len(train_items), "n_val": len(val_items), "best_val_l2": best, "history": history}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"保存 {out_dir / 'quad_ppt.pt'} best_val_l2={best:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
