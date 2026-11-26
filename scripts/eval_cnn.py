"""在验证集上评估已训练的 CNN，可选测试时增强（TTA）。

用法：
    PYTHONPATH=src python scripts/eval_cnn.py --run runs/exp-cnn-05 --tta all
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
from PIL import Image
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, check_manifest_hash, load_split  # noqa: E402
from docnorm.enhance.clahe import enhance_document  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="runs/exp-* 目录")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--split", type=Path, default=None)
    parser.add_argument("--no-rectify", action="store_true")
    parser.add_argument("--enhance", action="store_true")
    parser.add_argument(
        "--tta",
        choices=("none", "scales", "crops", "all"),
        default="none",
        help="none 仅中心裁剪；scales 多尺度；crops 五裁剪；all 合并",
    )
    parser.add_argument("--input-size", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


def val_items(config: dict, split_path: Path):
    samples = load_manifest(
        ROOT / config["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(split_path)
    check_manifest_hash(split, ROOT / config["data"]["manifest"])
    assignment = assign_samples(split, samples)
    items = []
    for sample in samples:
        if assignment.get(sample.sample_id) != "val":
            continue
        if sample.content_label is None:
            continue
        items.append(
            {
                "sample_id": sample.sample_id,
                "file": sample.file,
                "label": sample.content_label,
                "resolution": sample.resolution,
            }
        )
    return items


def rectify_image(image: np.ndarray, config: dict, *, rectify: bool, enhance: bool):
    if rectify:
        quad = detect_document(
            image,
            canny_low=int(config["rectify"]["canny_low"]),
            canny_high=int(config["rectify"]["canny_high"]),
            min_area_ratio=float(config["rectify"]["min_area_ratio"]),
            max_area_ratio=float(config["rectify"]["max_area_ratio"]),
        )
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


def center_transform(scale: float, size: int):
    return transforms.Compose(
        [
            transforms.Resize(int(round(size * scale))),
            transforms.CenterCrop(size),
            transforms.ToTensor(),
            transforms.Normalize(MEAN, STD),
        ]
    )


def variants(image: np.ndarray, size: int, tta: str) -> torch.Tensor:
    if tta == "none":
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return torch.stack([transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.Resize(int(round(size * 256 / 224))),
                transforms.CenterCrop(size),
                transforms.ToTensor(),
                transforms.Normalize(MEAN, STD),
            ]
        )(rgb)])

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    tensors = []
    if tta in {"scales", "all"}:
        for scale in (1.0, 256 / 224, 288 / 224):
            tensors.append(center_transform(scale, size)(pil))
    if tta in {"crops", "all"}:
        base = transforms.Resize(int(round(size * 256 / 224)))(pil)
        crop_tf = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize(MEAN, STD),
            ]
        )
        tensors.extend(crop_tf(crop) for crop in transforms.FiveCrop(size)(base))
    return torch.stack(tensors)


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    split_path = args.split or ROOT / config["data"]["split"]
    run_dir = args.run if args.run.is_absolute() else ROOT / args.run
    model_path = run_dir / "cnn.pt"
    if not model_path.is_file():
        raise SystemExit(f"找不到模型: {model_path}")

    classifier = CnnClassifier.load(model_path, device="cpu")
    size = args.input_size or classifier.input_size
    load_size = max(1280, size * 5)
    items = val_items(config, split_path)
    if not items:
        raise SystemExit("验证集为空")

    all_variants = []
    labels = []
    for index, item in enumerate(items, start=1):
        loaded = load_image(
            ROOT / config["data"]["raw_dir"] / item["file"],
            max_long_edge=load_size,
        )
        image = rectify_image(
            loaded.image,
            config,
            rectify=not args.no_rectify,
            enhance=args.enhance,
        )
        all_variants.append(variants(image, size, args.tta))
        labels.append(CLASSES.index(item["label"]))
        if index % 10 == 0:
            print(f"预处理 {index}/{len(items)}")

    widths = {tensor.shape[0] for tensor in all_variants}
    if len(widths) != 1:
        raise SystemExit(f"TTA 变体数量不一致: {widths}")
    batch = torch.stack(all_variants)  # (N, V, 3, H, W)
    n, v = batch.shape[:2]
    batch = batch.reshape(n * v, *batch.shape[2:])

    classifier.model.eval()
    probabilities = []
    with torch.no_grad():
        for start in range(0, batch.shape[0], args.batch_size):
            logits = classifier.model(batch[start:start + args.batch_size])
            probabilities.append(torch.softmax(logits, dim=1).cpu().numpy())
    probabilities = np.vstack(probabilities).reshape(n, v, len(CLASSES)).mean(axis=1)

    predictions = probabilities.argmax(axis=1)
    true_labels = [CLASSES[index] for index in labels]
    predicted_labels = [CLASSES[index] for index in predictions]
    metrics = {
        "run": run_dir.name,
        "tta": args.tta,
        "input_size": size,
        "accuracy": float(accuracy_score(true_labels, predicted_labels)),
        "macro_f1": float(f1_score(true_labels, predicted_labels, average="macro")),
        "confusion_matrix": confusion_matrix(
            true_labels, predicted_labels, labels=list(CLASSES)
        ).tolist(),
    }

    out_path = run_dir / f"metrics_tta_{args.tta}.json"
    out_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    with (run_dir / f"predictions_val_tta_{args.tta}.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["sample_id", "true_label", "pred_label", "prob_text", "prob_formula"]
        )
        for index, item in enumerate(items):
            writer.writerow(
                [
                    item["sample_id"],
                    true_labels[index],
                    predicted_labels[index],
                    float(probabilities[index, 0]),
                    float(probabilities[index, 1]),
                ]
            )

    print(
        f"tta={args.tta} accuracy={metrics['accuracy']:.4f} "
        f"macro_f1={metrics['macro_f1']:.4f} "
        f"confusion={metrics['confusion_matrix']}"
    )
    print(f"结果写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
