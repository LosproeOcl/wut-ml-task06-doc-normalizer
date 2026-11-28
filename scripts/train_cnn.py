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
from docnorm.rectify.quad import QuadRegressor  # noqa: E402
from docnorm.enhance.clahe import enhance_document  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402
from docnorm.utils.runlog import RunLogger  # noqa: E402

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
        corner_policy: str = "always",
        load_size: int | None = None,
        quad_model=None,
        quad_policy: str = "off",
    ):
        self.items = items
        self.config = config
        self.transform = transform
        self.rectify = rectify
        self.enhance = enhance
        self.corner_overrides = corner_overrides or {}
        self.corner_policy = corner_policy
        self.load_size = load_size or int(config["data"]["image_size"])
        self.quad_model = quad_model
        self.quad_policy = quad_policy

    def __len__(self) -> int:
        return len(self.items)

    def _manual_quad(self, item, loaded, image):
        points = self.corner_overrides.get(item["sample_id"])
        if points is None:
            return None
        try:
            points = scale_points(points, loaded.original_size, image.shape)
            return DocumentQuad(np.asarray(points, dtype=np.float32))
        except (RectifyError, ValueError):
            return None

    def __getitem__(self, index: int):
        item = self.items[index]
        if item.get("path"):
            image_path = Path(item["path"])
            if not image_path.is_absolute():
                image_path = ROOT / image_path
        else:
            image_path = ROOT / self.config["data"]["raw_dir"] / item["file"]
        loaded = load_image(image_path, max_long_edge=self.load_size)
        image = loaded.image
        if self.rectify and item.get("rectify", True):
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
            if quad is None and self.corner_policy == "always":
                quad = self._manual_quad(item, loaded, image)
            if quad is None and self.corner_policy == "fallback":
                quad = self._manual_quad(item, loaded, image)
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


def build_transform(
    train: bool, *, input_size: int = 224, augment: str = "default"
):
    if not train:
        return transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.Resize(int(round(input_size * 256 / 224))),
                transforms.CenterCrop(input_size),
                transforms.ToTensor(),
                transforms.Normalize(MEAN, STD),
            ]
        )
    if augment == "none":
        return build_transform(False, input_size=input_size)
    if augment == "mild":
        return transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.RandomResizedCrop(
                    input_size, scale=(0.85, 1.0), ratio=(0.95, 1.05)
                ),
                transforms.RandomRotation(3),
                transforms.ColorJitter(brightness=0.15, contrast=0.15),
                transforms.ToTensor(),
                transforms.Normalize(MEAN, STD),
            ]
        )
    if augment == "skew":
        return transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.RandomResizedCrop(
                    input_size, scale=(0.6, 1.0), ratio=(0.8, 1.25)
                ),
                transforms.RandomRotation(10),
                transforms.RandomPerspective(distortion_scale=0.3, p=0.5),
                transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
                transforms.ToTensor(),
                transforms.Normalize(MEAN, STD),
            ]
        )
    if augment != "default":
        raise ValueError(f"未知增强策略: {augment}")
    return transforms.Compose(
        [
            transforms.ToPILImage(),
            transforms.RandomResizedCrop(input_size, scale=(0.7, 1.0)),
            transforms.RandomRotation(5),
            transforms.RandomPerspective(distortion_scale=0.15, p=0.3),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument(
        "--split",
        type=Path,
        default=None,
        help="覆盖配置中的划分文件（用于交叉验证折）",
    )
    parser.add_argument("--exp-id", default=None)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--freeze-epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--no-rectify", action="store_true")
    parser.add_argument("--no-enhance", action="store_true")
    parser.add_argument("--no-pretrained", action="store_true")
    parser.add_argument(
        "--corners-policy",
        choices=("always", "fallback", "none"),
        default="fallback",
        help="fallback 仅自动失败时用人工四角（默认）；always 优先人工；none 不使用",
    )
    parser.add_argument("--input-size", type=int, default=224)
    parser.add_argument(
        "--carrier",
        choices=("all", "ppt", "paper"),
        default="all",
        help="只用某一载体的样本训练/验证，默认全部",
    )
    parser.add_argument(
        "--dedupe-inbox",
        action="store_true",
        help="同一幻灯片的 2026-11-27 inbox 样本只保留清晰度最高的一张",
    )
    parser.add_argument(
        "--augment",
        choices=("default", "mild", "skew", "none"),
        default="default",
        help="增强强度；skew 增加随机透视/旋转，公式页建议 mild 或 none",
    )
    parser.add_argument(
        "--backbone",
        choices=(
            "mobilenet_v3_small",
            "mobilenet_v3_large",
            "efficientnet_b0",
        ),
        default=None,
        help="覆盖配置中的骨干网络",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--lr-head", type=float, default=None)
    parser.add_argument("--lr-finetune", type=float, default=None)
    parser.add_argument("--label-smoothing", type=float, default=0.0)
    parser.add_argument(
        "--formula-weight",
        type=float,
        default=1.0,
        help="在自动类别权重上再乘公式类权重，缓解公式召回偏低",
    )
    parser.add_argument(
        "--extra-train-manifest",
        type=Path,
        default=None,
        help="额外训练清单（sample_id,path,label[,rectify]），只追加到 train，不参与验证",
    )
    parser.add_argument(
        "--load-size",
        type=int,
        default=None,
        help="原图长边；默认取 1280 与 input_size×5 的较大值",
    )
    parser.add_argument(
        "--init-checkpoint",
        type=Path,
        default=None,
        help="外部预训练或上一阶段权重，加载后继续微调",
    )
    parser.add_argument(
        "--quad-model",
        type=Path,
        default=None,
        help="按载体训练的四角回归权重；提供后按 --quad-policy 参与拉正",
    )
    parser.add_argument(
        "--quad-policy",
        choices=("off", "primary", "fallback"),
        default="off",
        help="primary 学习四角优先；fallback 仅 OpenCV 失败时用学习四角",
    )
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True, warn_only=True)

    quad_model = None
    if args.quad_model is not None:
        if not args.quad_model.is_file():
            raise SystemExit(f"四角模型不存在: {args.quad_model}")
        quad_model = QuadRegressor.from_checkpoint(args.quad_model)
    if args.quad_policy != "off" and quad_model is None:
        raise SystemExit("--quad-policy 需要同时提供 --quad-model")

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    # 训练时的 OpenCV 回退参数与网页按载体选参保持一致。
    if args.carrier == "ppt":
        config["rectify"]["canny_low"] = int(
            config["rectify"].get("ppt_canny_low", config["rectify"]["canny_low"])
        )
        config["rectify"]["canny_high"] = int(
            config["rectify"].get("ppt_canny_high", config["rectify"]["canny_high"])
        )
    elif args.carrier == "paper":
        config["rectify"]["canny_low"] = int(
            config["rectify"].get("paper_canny_low", config["rectify"]["canny_low"])
        )
        config["rectify"]["canny_high"] = int(
            config["rectify"].get("paper_canny_high", config["rectify"]["canny_high"])
        )
    if args.backbone:
        config["classify"]["backbone"] = args.backbone
    load_size = args.load_size or max(1280, args.input_size * 5)
    exp_id = args.exp_id or f"exp-cnn-{datetime.now():%Y%m%d-%H%M}"
    out_dir = ROOT / "runs" / exp_id
    logger = RunLogger(
        exp_id,
        out_dir,
        "scripts/train_cnn.py",
        args,
        config,
        root=ROOT,
        notes="CNN 训练；数据、参数与环境见 run.json",
    )
    logger.log(f"实验 {exp_id} 开始")
    samples = load_manifest(
        ROOT / config["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(args.split or ROOT / config["data"]["split"])
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
    } if args.corners_policy != "none" else {}
    if overrides:
        print(f"应用训练集人工标签 {len(overrides)} 条")
    print(
        f"人工四角策略 {args.corners_policy}，训练集可用 {len(corners)} 条"
    )

    items = {"train": [], "val": []}
    inbox_representatives = set()
    if args.dedupe_inbox:
        groups_path = ROOT / "data/manifests/inbox_slide_groups.csv"
        if groups_path.is_file():
            inbox_representatives = {
                row["sample_id"]
                for row in csv.DictReader(groups_path.open(encoding="utf-8"))
                if row.get("representative") == "1"
            }
    for sample in samples:
        label = overrides.get(sample.sample_id, sample.content_label)
        if label is None:
            continue
        if args.carrier != "all" and not (sample.label or "").startswith(args.carrier + "_"):
            continue
        name = assignment[sample.sample_id]
        if (
            args.dedupe_inbox
            and name == "train"
            and sample.sample_id not in inbox_representatives
            and sample.sample_id in {
                row["sample_id"]
                for row in csv.DictReader((ROOT / "data/manifests/inbox_slide_groups.csv").open(encoding="utf-8"))
            }
        ):
            continue
        if name in items:
            items[name].append(
                {
                    "sample_id": sample.sample_id,
                    "file": sample.file,
                    "label": label,
                }
            )

    n_extra = 0
    if args.extra_train_manifest:
        extra_path = args.extra_train_manifest
        if not extra_path.is_absolute():
            extra_path = ROOT / extra_path
        if not extra_path.is_file():
            raise SystemExit(f"额外训练清单不存在: {extra_path}")
        seen_ids = {item["sample_id"] for group in items.values() for item in group}
        val_groups = set(split.groups.get("val", []))
        skipped_group = 0
        with extra_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                sample_id = (row.get("sample_id") or "").strip()
                label = (row.get("label") or "").strip()
                extra = (row.get("path") or row.get("file") or "").strip()
                if not sample_id or not label or not extra:
                    raise SystemExit(f"额外训练清单字段缺失: {row}")
                if sample_id in seen_ids:
                    raise SystemExit(f"额外训练清单 sample_id 重复: {sample_id}")
                if label not in CLASSES:
                    raise SystemExit(f"额外训练清单标签非法: {label}")
                extra_group = (row.get("group") or "").strip()
                if extra_group and extra_group in val_groups:
                    skipped_group += 1
                    continue
                items["train"].append(
                    {
                        "sample_id": sample_id,
                        "path": extra,
                        "label": label,
                        "rectify": (row.get("rectify") or "0").lower() not in {"0", "false"},
                    }
                )
                seen_ids.add(sample_id)
                n_extra += 1
        print(
            f"追加额外训练样本 {n_extra} 条: {extra_path}"
            + (f"，跳过 {skipped_group} 条来自当前验证组的背景" if skipped_group else "")
        )

    rectify = not args.no_rectify
    enhance = not args.no_enhance
    train_dataset = DocumentDataset(
        items["train"],
        config,
        build_transform(
            True, input_size=args.input_size, augment=args.augment
        ),
        rectify=rectify,
        enhance=enhance,
        corner_overrides=corners,
        corner_policy=args.corners_policy,
        load_size=load_size,
        quad_model=quad_model,
        quad_policy=args.quad_policy,
    )
    val_dataset = DocumentDataset(
        items["val"],
        config,
        build_transform(False, input_size=args.input_size),
        rectify=rectify,
        enhance=enhance,
        corner_overrides=corners,
        corner_policy=args.corners_policy,
        load_size=load_size,
        quad_model=quad_model,
        quad_policy=args.quad_policy,
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
    class_weights[CLASSES.index("formula")] *= args.formula_weight
    print(
        f"train={len(train_dataset)} val={len(val_dataset)} "
        f"class_weights={class_weights} rectify={rectify} enhance={enhance} "
        f"input={args.input_size} augment={args.augment} "
        f"backbone={config['classify']['backbone']} seed={args.seed}"
    )

    classifier = CnnClassifier(
        backbone=str(config["classify"]["backbone"]),
        pretrained=not args.no_pretrained,
        input_size=args.input_size,
        random_state=args.seed,
    )
    if args.init_checkpoint:
        checkpoint_path = (
            args.init_checkpoint
            if args.init_checkpoint.is_absolute()
            else ROOT / args.init_checkpoint
        )
        payload = torch.load(checkpoint_path, map_location="cpu")
        state = payload.get("state_dict", payload) if isinstance(payload, dict) else payload
        missing, unexpected = classifier.model.load_state_dict(state, strict=False)
        print(
            f"加载初始化权重 {checkpoint_path}，"
            f"missing={len(missing)} unexpected={len(unexpected)}"
        )
    started = time.perf_counter()
    history = classifier.fit(
        train_loader,
        val_loader,
        epochs=args.epochs,
        freeze_epochs=args.freeze_epochs,
        lr_head=float(args.lr_head or config["classify"]["lr_stage1"]),
        lr_finetune=float(args.lr_finetune or config["classify"]["lr_stage2"]),
        class_weights=class_weights,
        patience=args.patience,
        label_smoothing=args.label_smoothing,
        on_epoch=logger.log_epoch,
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
        "corner_policy": args.corners_policy,
        "n_manual_corners": len(corners),
        "backbone": str(config["classify"]["backbone"]),
        "input_size": args.input_size,
        "init_checkpoint": str(args.init_checkpoint) if args.init_checkpoint else None,
        "augment": args.augment,
        "load_size": load_size,
        "seed": args.seed,
        "patience": args.patience,
        "lr_head": float(args.lr_head or config["classify"]["lr_stage1"]),
        "lr_finetune": float(args.lr_finetune or config["classify"]["lr_stage2"]),
        "label_smoothing": args.label_smoothing,
        "formula_weight": args.formula_weight,
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
    logger.finish(
        metrics=result["metrics"],
        extra={
            "n_train": len(train_dataset),
            "n_val": len(val_dataset),
            "epochs": len(history["train_loss"]),
            "train_seconds": round(train_seconds, 2),
            "best_val_accuracy": max(history["val_accuracy"]),
            "class_weights": class_weights,
            "history": history,
            "loss": "CrossEntropyLoss(weight=class_weights,label_smoothing=args.label_smoothing)",
            "optimizer": "AdamW",
            "lr_head": float(args.lr_head or config["classify"]["lr_stage1"]),
            "lr_finetune": float(args.lr_finetune or config["classify"]["lr_stage2"]),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
