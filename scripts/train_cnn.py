"""MobileNetV3 迁移学习训练与验证。

只使用训练集拟合、验证集评估；测试集留待最终评估。
用法：
    PYTHONPATH=src python scripts/train_cnn.py --exp-id exp-cnn-01
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
import yaml
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, check_manifest_hash, load_split  # noqa: E402
from docnorm.data.annotations import ManualCornerStore, ManualLabelStore, scale_points  # noqa: E402
from docnorm.rectify.geometry import DocumentQuad, RectifyError  # noqa: E402
from docnorm.enhance.clahe import enhance_document  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class DocumentDataset(Dataset):
    def __init__(
        self,
        items,
        config,
        transform,
        *,
        rectify: bool,
        enhance: bool,
        corner_overrides: dict[str, list[list[float]]] | None = None,
    ):
        self.items = items
        self.config = config
        self.transform = transform
        self.rectify = rectify
        self.enhance = enhance
        self.corner_overrides = corner_overrides or {}

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int):
        item = self.items[index]
        loaded = load_image(
            ROOT / self.config["data"]["raw_dir"] / item["file"],
            max_long_edge=int(self.config["data"]["image_size"]),
        )
        image = loaded.image
        if self.rectify:
            quad = None
            points = self.corner_overrides.get(item["sample_id"])
            if points is not None:
                try:
                    points = scale_points(points, loaded.original_size, image.shape)
                    quad = DocumentQuad(np.asarray(points, dtype=np.float32))
                except (RectifyError, ValueError):
                    quad = None
            if quad is None:
                quad = detect_document(
                    image,
                    canny_low=int(self.config["rectify"]["canny_low"]),
                    canny_high=int(self.config["rectify"]["canny_high"]),
                    min_area_ratio=float(self.config["rectify"]["min_area_ratio"]),
                    max_area_ratio=float(self.config["rectify"]["max_area_ratio"]),
                )
            if quad is not None:
                image = warp_document(
                    image,
                    quad,
                    output_long_edge=int(self.config["rectify"]["output_long_edge"]),
                )
        if self.enhance:
            image = enhance_document(
                image,
                clip_limit=float(self.config["enhance"]["clahe_clip"]),
                tile_grid_size=int(self.config["enhance"]["clahe_grid"]),
                correct_shadows=bool(self.config["enhance"]["correct_shadows"]),
                shadow_kernel=int(self.config["enhance"]["shadow_kernel"]),
                shadow_strength=float(self.config["enhance"]["shadow_strength"]),
                denoise=bool(self.config["enhance"]["denoise"]),
            )
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return self.transform(rgb), CLASSES.index(item["label"])


def build_transform(train: bool):
    if train:
        return transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
                transforms.RandomRotation(5),
                transforms.RandomPerspective(distortion_scale=0.15, p=0.3),
                transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
                transforms.ToTensor(),
                transforms.Normalize(MEAN, STD),
            ]
        )
    return transforms.Compose(
        [
            transforms.ToPILImage(),
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--exp-id", default=None)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--freeze-epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--no-rectify", action="store_true")
    parser.add_argument("--no-enhance", action="store_true")
    parser.add_argument("--no-pretrained", action="store_true")
    args = parser.parse_args()

    torch.manual_seed(42)
    np.random.seed(42)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True, warn_only=True)

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    samples = load_manifest(
        ROOT / config["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(ROOT / config["data"]["split"])
    check_manifest_hash(split, ROOT / config["data"]["manifest"])
    assignment = assign_samples(split, samples)
    overrides = {
        sample_id: label
        for sample_id, label in ManualLabelStore(
            ROOT / "data/annotations/manual_labels.csv"
        ).load().items()
        if assignment.get(sample_id) == "train"
    }
    corners = {
        sample_id: points
        for sample_id, points in ManualCornerStore(
            ROOT / "data/annotations/manual_corners.csv"
        ).load().items()
        if assignment.get(sample_id) == "train"
    }
    if overrides:
        print(f"应用训练集人工标签 {len(overrides)} 条")
    if corners:
        print(f"应用训练集人工四角 {len(corners)} 条")

    items = {"train": [], "val": []}
    for sample in samples:
        label = overrides.get(sample.sample_id, sample.content_label)
        if label is None:
            continue
        name = assignment[sample.sample_id]
        if name in items:
            items[name].append(
                {
                    "sample_id": sample.sample_id,
                    "file": sample.file,
                    "label": label,
                }
            )

    rectify = not args.no_rectify
    enhance = not args.no_enhance
    train_dataset = DocumentDataset(
        items["train"],
        config,
        build_transform(True),
        rectify=rectify,
        enhance=enhance,
        corner_overrides=corners,
    )
    val_dataset = DocumentDataset(
        items["val"],
        config,
        build_transform(False),
        rectify=rectify,
        enhance=enhance,
        corner_overrides=corners,
    )
    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0
    )

    counts = np.bincount(
        [CLASSES.index(item["label"]) for item in items["train"]], minlength=2
    )
    class_weights = (counts.sum() / (2.0 * np.maximum(counts, 1))).tolist()
    print(
        f"train={len(train_dataset)} val={len(val_dataset)} "
        f"class_weights={class_weights} rectify={rectify} enhance={enhance}"
    )

    exp_id = args.exp_id or f"exp-cnn-{datetime.now():%Y%m%d-%H%M}"
    out_dir = ROOT / "runs" / exp_id
    out_dir.mkdir(parents=True, exist_ok=True)

    classifier = CnnClassifier(
        backbone=str(config["classify"]["backbone"]),
        pretrained=not args.no_pretrained,
    )
    started = time.perf_counter()
    history = classifier.fit(
        train_loader,
        val_loader,
        epochs=args.epochs,
        freeze_epochs=args.freeze_epochs,
        lr_head=float(config["classify"]["lr_stage1"]),
        lr_finetune=float(config["classify"]["lr_stage2"]),
        class_weights=class_weights,
    )
    train_seconds = time.perf_counter() - started

    classifier.model.eval()
    predictions = []
    probabilities = []
    labels = []
    with torch.no_grad():
        for images, targets in val_loader:
            logits = classifier.model(images)
            probabilities.append(torch.softmax(logits, dim=1).numpy())
            predictions.extend(logits.argmax(dim=1).tolist())
            labels.extend(targets.tolist())
    probabilities = np.vstack(probabilities)
    true_labels = [CLASSES[index] for index in labels]
    predicted_labels = [CLASSES[index] for index in predictions]

    metrics = {
        "accuracy": float(accuracy_score(true_labels, predicted_labels)),
        "macro_f1": float(f1_score(true_labels, predicted_labels, average="macro")),
        "confusion_matrix": confusion_matrix(
            true_labels, predicted_labels, labels=list(CLASSES)
        ).tolist(),
        "classification_report": classification_report(
            true_labels,
            predicted_labels,
            labels=list(CLASSES),
            output_dict=True,
            zero_division=0,
        ),
    }
    classifier.save(out_dir / "cnn.pt")

    with (out_dir / "predictions_val.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["sample_id", "true_label", "pred_label", "prob_text", "prob_formula"]
        )
        for index, sample in enumerate(items["val"]):
            writer.writerow(
                [
                    sample["sample_id"],
                    true_labels[index],
                    predicted_labels[index],
                    float(probabilities[index, 0]),
                    float(probabilities[index, 1]),
                ]
            )

    result = {
        "exp_id": exp_id,
        "split": Path(config["data"]["split"]).name,
        "n_train": len(train_dataset),
        "n_val": len(val_dataset),
        "rectify": rectify,
        "enhance": enhance,
        "epochs": len(history["train_loss"]),
        "train_seconds": round(train_seconds, 2),
        "metrics": {key: round(value, 4) if isinstance(value, float) else value
                    for key, value in metrics.items() if key != "classification_report"},
        "history": history,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "config.snapshot.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(
        f"accuracy={metrics['accuracy']:.4f} macro_f1={metrics['macro_f1']:.4f} "
        f"confusion={metrics['confusion_matrix']} seconds={train_seconds:.1f}"
    )
    print(f"结果写入 {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
