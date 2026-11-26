"""在外部辅助数据上预训练 MobileNetV3，再供自采训练脚本加载。

外部数据只用于初始化，不进入自采验证/测试。清单见
`data/manifests/external_aux.csv`，来源与许可逐行记录。

用法：
    PYTHONPATH=src python scripts/pretrain_external.py --epochs 2
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import yaml
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.utils.runlog import RunLogger  # noqa: E402

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class ExternalDataset(Dataset):
    def __init__(self, rows, transform):
        self.rows = rows
        self.transform = transform

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        loaded = load_image(ROOT / row["path"], max_long_edge=256)
        rgb = cv2.cvtColor(loaded.image, cv2.COLOR_BGR2RGB)
        return self.transform(rgb), CLASSES.index(row["label"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/external_aux.csv")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/pretrain-external-01")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--freeze-epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--input-size", type=int, default=160)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(4)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    rows = [
        row
        for row in csv.DictReader(args.manifest.open(encoding="utf-8"))
        if (ROOT / row["path"]).is_file()
    ]
    if len(rows) < 100:
        raise SystemExit(f"外部样本过少: {len(rows)}")
    labels = [CLASSES.index(row["label"]) for row in rows]
    train_rows, val_rows = train_test_split(
        rows, test_size=0.1, random_state=args.seed, stratify=labels
    )
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(
        out_dir.name,
        out_dir,
        "scripts/pretrain_external.py",
        args,
        config,
        root=ROOT,
        notes="外部辅助预训练；仅用于初始化，不进入自采验证/测试；来源见 external_aux.csv",
    )
    logger.log(f"外部预训练 {out_dir.name} 开始，train={len(train_rows)} val={len(val_rows)}")

    train_transform = transforms.Compose(
        [
            transforms.ToPILImage(),
            transforms.RandomResizedCrop(args.input_size, scale=(0.8, 1.0)),
            transforms.RandomRotation(3),
            transforms.ColorJitter(brightness=0.1, contrast=0.1),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )
    val_transform = transforms.Compose(
        [
            transforms.ToPILImage(),
            transforms.Resize(int(round(args.input_size * 256 / 224))),
            transforms.CenterCrop(args.input_size),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )
    train_loader = DataLoader(
        ExternalDataset(train_rows, train_transform),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
    )
    val_loader = DataLoader(
        ExternalDataset(val_rows, val_transform),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )
    counts = np.bincount(
        [CLASSES.index(row["label"]) for row in train_rows], minlength=2
    )
    class_weights = (counts.sum() / (2.0 * np.maximum(counts, 1))).tolist()
    classifier = CnnClassifier(
        backbone="mobilenet_v3_small",
        pretrained=True,
        input_size=args.input_size,
        random_state=args.seed,
    )
    history = classifier.fit(
        train_loader,
        val_loader,
        epochs=args.epochs,
        freeze_epochs=args.freeze_epochs,
        lr_head=1e-3,
        lr_finetune=3e-4,
        class_weights=class_weights,
        patience=2,
        on_epoch=logger.log_epoch,
    )
    val_loss, val_accuracy = classifier.evaluate(val_loader)
    torch.save(
        {
            "state_dict": classifier.model.state_dict(),
            "input_size": args.input_size,
            "classes": CLASSES,
            "source": "external_aux",
        },
        out_dir / "backbone.pt",
    )
    result = {
        "exp_id": out_dir.name,
        "manifest": str(args.manifest),
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "input_size": args.input_size,
        "epochs": len(history["train_loss"]),
        "external_val_accuracy": float(val_accuracy),
        "external_val_loss": float(val_loss),
        "class_weights": class_weights,
        "history": history,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"外部验证 accuracy={val_accuracy:.4f} loss={val_loss:.4f} "
        f"epochs={len(history['train_loss'])}"
    )
    logger.finish(metrics={"external_val_accuracy": val_accuracy}, extra=result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
