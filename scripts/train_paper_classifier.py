"""纸质稿专用内容分类器：自采 paper + 外部 A4 数据。

只用于“纸质稿”分支；验证集为自采 paper val，PPT 分支仍用现有 CNN。
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
import yaml
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.annotations import ManualCornerStore, scale_points  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402
from docnorm.rectify.geometry import DocumentQuad, RectifyError  # noqa: E402
from docnorm.rectify.quad import QuadRegressor  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402
from docnorm.utils.runlog import RunLogger  # noqa: E402
from scripts.train_cnn import build_transform  # noqa: E402


class PaperDataset(Dataset):
    def __init__(
        self,
        rows,
        config: dict,
        transform,
        train: bool,
        quad_model=None,
        quad_policy: str = "off",
    ):
        self.rows = rows
        self.config = config
        self.transform = transform
        self.train = train
        self.corners = ManualCornerStore(ROOT / "data/annotations/manual_corners.csv").load()
        self.quad_model = quad_model
        self.quad_policy = quad_policy

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        loaded = load_image(ROOT / row["path"], max_long_edge=int(self.config["data"]["image_size"]))
        image = loaded.image
        if row["source"] == "self-paper":
            quad = None
            if self.quad_policy == "primary" and self.quad_model is not None:
                quad = self.quad_model.predict(image)
            if quad is None:
                quad = detect_document(
                    image,
                    canny_low=int(self.config["rectify"]["canny_low"]),
                    canny_high=int(self.config["rectify"]["canny_high"]),
                    min_area_ratio=float(self.config["rectify"]["min_area_ratio"]),
                    max_area_ratio=float(self.config["rectify"]["max_area_ratio"]),
                )
            if (
                quad is None
                and self.quad_policy == "fallback"
                and self.quad_model is not None
            ):
                quad = self.quad_model.predict(image)
            if quad is None and self.train and row["sample_id"] in self.corners:
                try:
                    points = scale_points(
                        self.corners[row["sample_id"]], loaded.original_size, image.shape
                    )
                    quad = DocumentQuad(np.asarray(points, dtype=np.float32))
                except (RectifyError, ValueError):
                    quad = None
            if quad is not None:
                image = warp_document(
                    image,
                    quad,
                    output_long_edge=int(self.config["rectify"]["output_long_edge"]),
                )
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return self.transform(rgb), CLASSES.index(row["label"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/paper_content.csv")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/paper-cnn-01")
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--freeze-epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--input-size", type=int, default=224)
    parser.add_argument("--patience", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--class-weight-mode",
        choices=("balanced", "none"),
        default="balanced",
        help="balanced：按训练集类别频次加权；none：不加权，用于消融类别权重影响",
    )
    parser.add_argument(
        "--quad-model",
        type=Path,
        default=None,
        help="纸质四角回归权重；提供后按 --quad-policy 参与自采纸质拉正",
    )
    parser.add_argument(
        "--quad-policy",
        choices=("off", "primary", "fallback"),
        default="off",
        help="primary 学习四角优先；fallback 仅 OpenCV 失败时用学习四角",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(4)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    quad_model = None
    if args.quad_model is not None:
        if not args.quad_model.is_file():
            raise SystemExit(f"四角模型不存在: {args.quad_model}")
        quad_model = QuadRegressor.from_checkpoint(args.quad_model)
    if args.quad_policy != "off" and quad_model is None:
        raise SystemExit("--quad-policy 需要同时提供 --quad-model")
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
        "scripts/train_paper_classifier.py",
        args,
        config,
        root=ROOT,
        notes="纸质稿专用内容分类；自采 paper + 外部 A4，自采 val 只评估",
    )
    logger.log(f"纸质稿模型训练开始，train={len(train_rows)} val={len(val_rows)}")
    train_loader = DataLoader(
        PaperDataset(
            train_rows,
            config,
            build_transform(True, input_size=args.input_size, augment="default"),
            train=True,
            quad_model=quad_model,
            quad_policy=args.quad_policy,
        ),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
    )
    val_loader = DataLoader(
        PaperDataset(
            val_rows,
            config,
            build_transform(False, input_size=args.input_size),
            train=False,
            quad_model=quad_model,
            quad_policy=args.quad_policy,
        ),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )
    counts = np.bincount([CLASSES.index(row["label"]) for row in train_rows], minlength=2)
    class_weights = (
        (counts.sum() / (2.0 * np.maximum(counts, 1))).tolist()
        if args.class_weight_mode == "balanced"
        else None
    )
    classifier = CnnClassifier(
        backbone=str(config["classify"]["backbone"]),
        pretrained=True,
        input_size=args.input_size,
        random_state=args.seed,
    )
    history = classifier.fit(
        train_loader,
        val_loader,
        epochs=args.epochs,
        freeze_epochs=args.freeze_epochs,
        lr_head=float(config["classify"]["lr_stage1"]),
        lr_finetune=float(config["classify"]["lr_stage2"]),
        class_weights=class_weights,
        patience=args.patience,
        on_epoch=logger.log_epoch,
    )
    classifier.model.eval()
    predictions = []
    labels = []
    probabilities = []
    with torch.no_grad():
        for images, targets in val_loader:
            logits = classifier.model(images)
            probabilities.extend(torch.softmax(logits, dim=1).cpu().numpy().tolist())
            predictions.extend(logits.argmax(dim=1).tolist())
            labels.extend(targets.tolist())
    true_labels = [CLASSES[index] for index in labels]
    pred_labels = [CLASSES[index] for index in predictions]
    metrics = {
        "accuracy": float(accuracy_score(true_labels, pred_labels)),
        "macro_f1": float(f1_score(true_labels, pred_labels, average="macro")),
        "confusion_matrix": confusion_matrix(
            true_labels, pred_labels, labels=list(CLASSES)
        ).tolist(),
    }
    classifier.save(out_dir / "paper_cnn.pt")
    result = {
        "exp_id": out_dir.name,
        "manifest": str(args.manifest),
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "input_size": args.input_size,
        "epochs": len(history["train_loss"]),
        "metrics": metrics,
        "history": history,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "predictions_val.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["sample_id", "true_label", "pred_label", "prob_text", "prob_formula"],
        )
        writer.writeheader()
        for row, true_label, pred_label, prob in zip(
            val_rows, true_labels, pred_labels, probabilities
        ):
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "true_label": true_label,
                    "pred_label": pred_label,
                    "prob_text": f"{prob[0]:.8f}",
                    "prob_formula": f"{prob[1]:.8f}",
                }
            )
    print(f"paper acc={metrics['accuracy']:.4f} f1={metrics['macro_f1']:.4f} conf={metrics['confusion_matrix']}")
    logger.finish(
        metrics=metrics,
        extra={
            **result,
            "loss": "CrossEntropyLoss(weight=class_weights)",
            "optimizer": "AdamW",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
