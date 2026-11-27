"""把外部预训练权重直接用在自采真实数据上，测零样本迁移准确率。

不加载任何自采训练权重，只做自采验证/测试/全量评估，用于判断外部公式
与文本数据本身能否直接支撑内容二分类。

用法：
    PYTHONPATH=src python scripts/eval_pretrained_on_self.py \
      --checkpoint runs/pretrain-external-01/backbone.pt \
      --checkpoint runs/pretrain-external-small/backbone.pt
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch
import yaml
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.annotations import ManualCornerStore, scale_points  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from docnorm.enhance.clahe import enhance_document  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402
from docnorm.rectify.geometry import DocumentQuad, RectifyError  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", action="append", required=True, type=Path)
    parser.add_argument(
        "--split", choices=("all", "train", "val", "test"), default="all"
    )
    parser.add_argument("--no-rectify", action="store_true")
    parser.add_argument("--enhance", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json-out", type=Path, default=None)
    return parser.parse_args()


def metrics_block(labels, predictions, carriers) -> dict:
    labels = np.asarray(labels)
    predictions = np.asarray(predictions)
    carriers = np.asarray(carriers)
    result = {
        "n": int(len(labels)),
        "accuracy": float(accuracy_score(labels, predictions)),
        "macro_f1": float(f1_score(labels, predictions, average="macro")),
        "confusion_matrix": confusion_matrix(
            labels, predictions, labels=list(CLASSES)
        ).tolist(),
        "per_class_recall": {},
        "per_carrier_accuracy": {},
    }
    for name in CLASSES:
        mask = labels == name
        result["per_class_recall"][name] = (
            float((predictions[mask] == name).mean()) if mask.any() else None
        )
    for carrier in ("ppt", "paper"):
        mask = carriers == carrier
        result["per_carrier_accuracy"][carrier] = (
            float((predictions[mask] == labels[mask]).mean()) if mask.any() else None
        )
    return result


def main() -> int:
    args = parse_args()
    torch.set_num_threads(4)
    config = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    assignment = assign_samples(load_split(ROOT / "data/splits/split_v4.json"), samples)
    corners = ManualCornerStore(ROOT / "data/annotations/manual_corners.csv").load()
    items = []
    for sample in samples:
        if sample.content_label is None:
            continue
        split = assignment.get(sample.sample_id)
        if split is None:
            continue
        if args.split != "all" and split != args.split:
            continue
        items.append(sample)
    if args.limit:
        items = items[: args.limit]
    print(f"评估样本 {len(items)} 张，split={args.split}")

    rows = []
    for checkpoint in args.checkpoint:
        path = checkpoint if checkpoint.is_absolute() else ROOT / checkpoint
        payload = torch.load(path, map_location="cpu")
        input_size = int(payload.get("input_size", 224))
        classifier = CnnClassifier(
            backbone=str(payload.get("backbone", "mobilenet_v3_small")),
            pretrained=False,
            input_size=input_size,
        )
        classifier.model.load_state_dict(payload["state_dict"])
        classifier.model.eval()
        labels = []
        predictions = []
        carriers = []
        probabilities = []
        valid = 0
        with torch.no_grad():
            for sample in items:
                loaded = load_image(
                    ROOT / "data/raw_samples" / sample.file, max_long_edge=1280
                )
                image = loaded.image
                if not args.no_rectify:
                    quad = detect_document(
                        image,
                        canny_low=int(config["rectify"]["canny_low"]),
                        canny_high=int(config["rectify"]["canny_high"]),
                        min_area_ratio=float(config["rectify"]["min_area_ratio"]),
                        max_area_ratio=float(config["rectify"]["max_area_ratio"]),
                    )
                    if quad is None and sample.sample_id in corners:
                        try:
                            points = scale_points(
                                corners[sample.sample_id],
                                loaded.original_size,
                                image.shape,
                            )
                            quad = DocumentQuad(np.asarray(points, dtype=np.float32))
                        except (RectifyError, ValueError):
                            quad = None
                    if quad is not None:
                        image = warp_document(
                            image,
                            quad,
                            output_long_edge=int(
                                config["rectify"]["output_long_edge"]
                            ),
                        )
                if args.enhance:
                    image = enhance_document(
                        image,
                        clip_limit=float(config["enhance"]["clahe_clip"]),
                        tile_grid_size=int(config["enhance"]["clahe_grid"]),
                        correct_shadows=bool(config["enhance"]["correct_shadows"]),
                        shadow_kernel=int(config["enhance"]["shadow_kernel"]),
                        shadow_strength=float(config["enhance"]["shadow_strength"]),
                        denoise=bool(config["enhance"]["denoise"]),
                    )
                tensor = classifier._prepare(image).unsqueeze(0)
                probs = torch.softmax(classifier.model(tensor), dim=1)[0].numpy()
                index = int(probs.argmax())
                labels.append(sample.content_label)
                predictions.append(CLASSES[index])
                carriers.append((sample.label or "").split("_")[0])
                probabilities.append(float(probs[CLASSES.index("formula")]))
                valid += 1
                if valid % 25 == 0:
                    print(f"  {path.name}: {valid}/{len(items)}", flush=True)

        metrics = metrics_block(labels, predictions, carriers)
        row = {
            "checkpoint": str(path.relative_to(ROOT)),
            "split": args.split,
            "rectify": not args.no_rectify,
            "enhance": args.enhance,
            **{key: metrics[key] for key in ("n", "accuracy", "macro_f1")},
            "text_recall": metrics["per_class_recall"]["text"],
            "formula_recall": metrics["per_class_recall"]["formula"],
            "ppt_accuracy": metrics["per_carrier_accuracy"]["ppt"],
            "paper_accuracy": metrics["per_carrier_accuracy"]["paper"],
            "confusion_matrix": json.dumps(metrics["confusion_matrix"]),
        }
        rows.append(row)
        # 保存逐样本预测，便于后续 McNemar / 错误分析。
        detail_path = path.parent / f"predictions_self_{args.split}.csv"
        with detail_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["sample_id", "label", "carrier", "pred", "prob_formula"])
            for sample, label, carrier, pred, prob in zip(
                items, labels, carriers, predictions, probabilities
            ):
                writer.writerow([sample.sample_id, label, carrier, pred, f"{prob:.6f}"])
        print(
            f"{path} n={metrics['n']} acc={metrics['accuracy']:.4f} "
            f"f1={metrics['macro_f1']:.4f} "
            f"text_recall={metrics['per_class_recall']['text']:.4f} "
            f"formula_recall={metrics['per_class_recall']['formula']:.4f} "
            f"conf={metrics['confusion_matrix']}",
            flush=True,
        )

    if args.json_out:
        out = args.json_out if args.json_out.is_absolute() else ROOT / args.json_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
