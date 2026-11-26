"""复合模型实验：传统特征 + CNN 嵌入的早期融合。

在训练集上提取 1836 维传统特征与 MobileNetV3 池化嵌入，拼接后训练
SVM / 逻辑回归，并与单路特征对比。验证集只用于本实验评估，测试集不参与。

用法：
    PYTHONPATH=src python scripts/fusion_eval.py --cnn-run runs/exp-cnn-05
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.annotations import (  # noqa: E402
    ManualCornerStore,
    ManualLabelStore,
    scale_points,
)
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, check_manifest_hash, load_split  # noqa: E402
from docnorm.enhance.clahe import enhance_document  # noqa: E402
from docnorm.features.classic import extract_features  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402
from docnorm.rectify.geometry import DocumentQuad, RectifyError  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402
from docnorm.utils.runlog import RunLogger  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cnn-run", type=Path, default=ROOT / "runs/exp-cnn-05")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--split", type=Path, default=None)
    parser.add_argument("--no-rectify", action="store_true")
    parser.add_argument("--enhance", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def load_items(config: dict, split_path: Path):
    samples = load_manifest(
        ROOT / config["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(split_path)
    check_manifest_hash(split, ROOT / config["data"]["manifest"])
    assignment = assign_samples(split, samples)
    labels = ManualLabelStore(ROOT / "data/annotations/manual_labels.csv").load()
    corners = ManualCornerStore(ROOT / "data/annotations/manual_corners.csv").load()
    items = []
    for sample in samples:
        name = assignment.get(sample.sample_id)
        if name not in {"train", "val"}:
            continue
        label = labels.get(sample.sample_id, sample.content_label) if name == "train" else sample.content_label
        if label is None:
            continue
        items.append(
            {
                "sample_id": sample.sample_id,
                "file": sample.file,
                "label": label,
                "split": name,
                "corners": corners.get(sample.sample_id) if name == "train" else None,
            }
        )
    return items


def rectify_image(image, config, corners, original_size, *, rectify: bool, enhance: bool):
    if rectify:
        quad = detect_document(
            image,
            canny_low=int(config["rectify"]["canny_low"]),
            canny_high=int(config["rectify"]["canny_high"]),
            min_area_ratio=float(config["rectify"]["min_area_ratio"]),
            max_area_ratio=float(config["rectify"]["max_area_ratio"]),
        )
        if quad is None and corners is not None:
            try:
                points = scale_points(corners, original_size, image.shape)
                quad = DocumentQuad(np.asarray(points, dtype=np.float32))
            except (RectifyError, ValueError):
                quad = None
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


def cnn_embedding(classifier: CnnClassifier, image: np.ndarray) -> np.ndarray:
    tensor = classifier._prepare(image).unsqueeze(0)
    with torch.no_grad():
        features = classifier.model.features(tensor)
        pooled = classifier.model.avgpool(features)
        vector = torch.flatten(pooled, 1)
    return vector.cpu().numpy()[0]


def metrics_from_proba(y_true, proba, classes):
    pred = proba.argmax(axis=1)
    labels = [classes[i] for i in pred]
    return {
        "accuracy": float(accuracy_score(y_true, labels)),
        "macro_f1": float(f1_score(y_true, labels, average="macro")),
        "confusion_matrix": confusion_matrix(
            y_true, labels, labels=list(CLASSES)
        ).tolist(),
    }


def evaluate(name, x_train, y_train, x_val, y_val, estimator):
    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("model", estimator),
        ]
    )
    pipeline.fit(x_train, y_train)
    proba = pipeline.predict_proba(x_val)
    classes = list(pipeline.classes_)
    metrics = metrics_from_proba(y_val, proba, classes)
    print(
        f"{name:22s} acc={metrics['accuracy']:.4f} "
        f"f1={metrics['macro_f1']:.4f} cm={metrics['confusion_matrix']}"
    )
    return metrics


def main() -> int:
    args = parse_args()
    torch.set_num_threads(2)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    split_path = args.split or ROOT / config["data"]["split"]
    run_dir = args.cnn_run if args.cnn_run.is_absolute() else ROOT / args.cnn_run
    out_dir = args.out or (ROOT / "runs" / "fusion-exp-01")
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(
        out_dir.name,
        out_dir,
        "scripts/fusion_eval.py",
        args,
        config,
        root=ROOT,
        notes="传统特征 + CNN 嵌入的早期融合实验",
    )
    logger.log(f"融合实验 {out_dir.name} 开始")

    classifier = CnnClassifier.load(run_dir / "cnn.pt", device="cpu")
    classifier.model.eval()
    items = load_items(config, split_path)
    classic = []
    embeddings = []
    for index, item in enumerate(items, start=1):
        loaded = load_image(
            ROOT / config["data"]["raw_dir"] / item["file"],
            max_long_edge=int(config["data"]["image_size"]),
        )
        image = rectify_image(
            loaded.image,
            config,
            item["corners"],
            loaded.original_size,
            rectify=not args.no_rectify,
            enhance=args.enhance,
        )
        classic.append(extract_features(image))
        embeddings.append(cnn_embedding(classifier, image))
        if index % 50 == 0:
            print(f"特征 {index}/{len(items)}")
    classic = np.stack(classic)
    embeddings = np.stack(embeddings)
    labels = np.array([item["label"] for item in items])
    splits = np.array([item["split"] for item in items])
    train_mask = splits == "train"
    val_mask = splits == "val"
    fusion = np.concatenate([classic, embeddings], axis=1)

    np.savez_compressed(
        out_dir / "features.npz",
        classic=classic,
        cnn=embeddings,
        labels=labels,
        splits=splits,
    )

    y_train, y_val = labels[train_mask], labels[val_mask]
    results = {
        "cnn_run": run_dir.name,
        "split": split_path.name,
        "feature_dim": {
            "classic": int(classic.shape[1]),
            "cnn": int(embeddings.shape[1]),
            "fusion": int(fusion.shape[1]),
        },
        "models": {},
    }
    estimators = {
        "logreg": LogisticRegression(max_iter=3000, class_weight="balanced", random_state=args.seed),
        "svm": SVC(C=1.0, gamma="scale", probability=True, class_weight="balanced", random_state=args.seed),
        "rf": RandomForestClassifier(
            n_estimators=400,
            min_samples_leaf=2,
            max_features="sqrt",
            class_weight="balanced_subsample",
            random_state=args.seed,
            n_jobs=-1,
        ),
    }
    for feature_name, matrix in (("classic", classic), ("cnn", embeddings), ("fusion", fusion)):
        for estimator_name, estimator in estimators.items():
            results["models"][f"{feature_name}_{estimator_name}"] = evaluate(
                f"{feature_name}/{estimator_name}",
                matrix[train_mask],
                y_train,
                matrix[val_mask],
                y_val,
                estimator,
            )
    results["models"]["fusion_pca_svm"] = evaluate(
        "fusion/pca128+svm",
        fusion[train_mask],
        y_train,
        fusion[val_mask],
        y_val,
        Pipeline(
            [
                ("pca", PCA(n_components=128, random_state=args.seed)),
                ("model", SVC(C=1.0, gamma="scale", probability=True, class_weight="balanced", random_state=args.seed)),
            ]
        ),
    )

    (out_dir / "metrics.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"结果写入 {out_dir}")
    logger.finish(
        metrics=results["models"],
        extra={
            "feature_dim": results["feature_dim"],
            "cnn_run": results["cnn_run"],
            "split": results["split"],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
