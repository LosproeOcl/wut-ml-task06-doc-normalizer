"""传统基线训练与验证。

只使用训练集拟合、验证集评估；测试集留待最终评估，不在本脚本中触碰。
用法：
    PYTHONPATH=src python scripts/train_classic.py --exp-id exp-20261126-01
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.classify.classic import ClassicClassifier  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, check_manifest_hash, load_split  # noqa: E402
from docnorm.data.annotations import ManualCornerStore, ManualLabelStore, scale_points  # noqa: E402
from docnorm.rectify.geometry import DocumentQuad, RectifyError  # noqa: E402
from docnorm.enhance.clahe import enhance_document  # noqa: E402
from docnorm.features.classic import FEATURE_DIM, extract_features  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402

LABELS = ["text", "formula"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--split", type=Path, default=None)
    parser.add_argument("--exp-id", default=None)
    parser.add_argument("--no-rectify", action="store_true")
    parser.add_argument("--no-enhance", action="store_true")
    parser.add_argument(
        "--corners-policy",
        choices=("always", "fallback", "none"),
        default="fallback",
        help="fallback 仅自动失败时用人工四角（默认）；always 优先人工；none 不使用",
    )
    return parser.parse_args()


def build_features(
    samples,
    config: dict,
    *,
    use_rectify: bool,
    use_enhance: bool,
    label_overrides: dict[str, str] | None = None,
    corner_overrides: dict[str, list[list[float]]] | None = None,
    corner_policy: str = "always",
) -> tuple[np.ndarray, np.ndarray, list[str], int]:
    overrides = label_overrides or {}
    corners = corner_overrides or {}

    def manual_quad(sample_id: str, loaded, image):
        points = corners.get(sample_id)
        if points is None:
            return None
        try:
            points = scale_points(points, loaded.original_size, image.shape)
            return DocumentQuad(np.asarray(points, dtype=np.float32))
        except (RectifyError, ValueError):
            return None

    vectors: list[np.ndarray] = []
    labels: list[str] = []
    ids: list[str] = []
    failures = 0
    image_size = int(config["data"]["image_size"])

    for sample in samples:
        label = overrides.get(sample.sample_id, sample.content_label)
        if label is None:
            continue
        loaded = load_image(
            ROOT / config["data"]["raw_dir"] / sample.file,
            max_long_edge=image_size,
        )
        image = loaded.image

        if use_rectify:
            quad = None
            if corner_policy == "always":
                quad = manual_quad(sample.sample_id, loaded, image)
            if quad is None:
                quad = detect_document(
                    image,
                    canny_low=int(config["rectify"]["canny_low"]),
                    canny_high=int(config["rectify"]["canny_high"]),
                    min_area_ratio=float(config["rectify"]["min_area_ratio"]),
                    max_area_ratio=float(config["rectify"]["max_area_ratio"]),
                )
            if quad is None and corner_policy == "fallback":
                quad = manual_quad(sample.sample_id, loaded, image)
            if quad is not None:
                image = warp_document(
                    image,
                    quad,
                    output_long_edge=int(config["rectify"]["output_long_edge"]),
                )
            else:
                failures += 1

        if use_enhance:
            image = enhance_document(
                image,
                clip_limit=float(config["enhance"]["clahe_clip"]),
                tile_grid_size=int(config["enhance"]["clahe_grid"]),
                correct_shadows=bool(config["enhance"]["correct_shadows"]),
                shadow_kernel=int(config["enhance"]["shadow_kernel"]),
                shadow_strength=float(config["enhance"]["shadow_strength"]),
                denoise=bool(config["enhance"]["denoise"]),
            )

        vectors.append(extract_features(image))
        labels.append(label)
        ids.append(sample.sample_id)
    return np.stack(vectors), np.asarray(labels), ids, failures


def evaluate(model: ClassicClassifier, features: np.ndarray, labels: np.ndarray) -> dict:
    predictions = model.predict(features)
    probabilities = model.predict_proba(features)
    return {
        "accuracy": float(accuracy_score(labels, predictions)),
        "macro_f1": float(f1_score(labels, predictions, average="macro")),
        "confusion_matrix": confusion_matrix(
            labels, predictions, labels=LABELS
        ).tolist(),
        "classification_report": classification_report(
            labels, predictions, labels=LABELS, output_dict=True, zero_division=0
        ),
        "predictions": predictions,
        "probabilities": probabilities,
    }


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    split_path = args.split or ROOT / config["data"]["split"]
    samples = load_manifest(
        ROOT / config["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(split_path)
    check_manifest_hash(split, ROOT / config["data"]["manifest"])
    assignment = assign_samples(split, samples)

    use_rectify = not args.no_rectify
    use_enhance = not args.no_enhance
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
    started = time.perf_counter()
    features, labels, ids, failures = build_features(
        samples,
        config,
        use_rectify=use_rectify,
        use_enhance=use_enhance,
        label_overrides=overrides,
        corner_overrides=corners,
        corner_policy=args.corners_policy,
    )
    feature_seconds = time.perf_counter() - started

    groups: dict[str, list[int]] = {"train": [], "val": []}
    for index, sample_id in enumerate(ids):
        name = assignment[sample_id]
        if name in groups:
            groups[name].append(index)
    if not groups["train"] or not groups["val"]:
        raise SystemExit("训练集或验证集为空，停止")

    train_index = np.asarray(groups["train"])
    val_index = np.asarray(groups["val"])
    x_train, y_train = features[train_index], labels[train_index]
    x_val, y_val = features[val_index], labels[val_index]

    exp_id = args.exp_id or f"exp-{datetime.now():%Y%m%d-%H%M}"
    out_dir = ROOT / "runs" / exp_id
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "exp_id": exp_id,
        "split": split_path.name,
        "feature_dim": FEATURE_DIM,
        "n_train": int(len(train_index)),
        "n_val": int(len(val_index)),
        "detection_failed": failures,
        "rectify": use_rectify,
        "enhance": use_enhance,
        "corner_policy": args.corners_policy,
        "n_manual_corners": len(corners),
        "feature_seconds": round(feature_seconds, 2),
        "models": {},
    }

    for name in ("svm", "rf"):
        train_started = time.perf_counter()
        model = ClassicClassifier(model=name).fit(x_train, y_train)
        metrics = evaluate(model, x_val, y_val)
        train_seconds = time.perf_counter() - train_started
        model.save(out_dir / f"{name}.joblib")

        predictions_path = out_dir / f"predictions_val_{name}.csv"
        with predictions_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ["sample_id", "true_label", "pred_label", "prob_text", "prob_formula"]
            )
            classes = list(model.classes_)
            for sample_id, true_label, pred_label, probability in zip(
                [ids[i] for i in val_index],
                y_val,
                metrics["predictions"],
                metrics["probabilities"],
            ):
                writer.writerow(
                    [
                        sample_id,
                        true_label,
                        pred_label,
                        float(probability[classes.index("text")]),
                        float(probability[classes.index("formula")]),
                    ]
                )

        results["models"][name] = {
            "accuracy": round(metrics["accuracy"], 4),
            "macro_f1": round(metrics["macro_f1"], 4),
            "confusion_matrix": metrics["confusion_matrix"],
            "classification_report": metrics["classification_report"],
            "train_seconds": round(train_seconds, 2),
        }
        print(
            f"{name}: accuracy={metrics['accuracy']:.4f} "
            f"macro_f1={metrics['macro_f1']:.4f} "
            f"confusion={metrics['confusion_matrix']}"
        )

    (out_dir / "metrics.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "config.snapshot.yaml").write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"结果写入 {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
