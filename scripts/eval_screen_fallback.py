"""评估屏幕检测兜底对自采验证集分类的影响。

基线：自动四角检测，失败时保留原图。
兜底：自动四角失败时，用 SCB 训练的屏幕检测器裁出幕布，再在裁剪图上做四角检测/拉正，最后分类。

只看自采 split_v3 验证集；外部 SCB 数据只参与屏幕检测器训练。
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
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.classify.cnn import CnnClassifier  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402
from docnorm.utils.runlog import RunLogger  # noqa: E402

CLASSES = ("text", "formula")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cnn-run", type=Path, default=ROOT / "runs/exp-cnn-05")
    parser.add_argument("--screen-run", type=Path, default=ROOT / "runs/screen-detector-01")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/screen-fallback-01")
    parser.add_argument("--margin", type=float, default=0.06)
    return parser.parse_args()


def load_val_items(config: dict):
    samples = load_manifest(
        ROOT / config["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(ROOT / config["data"]["split"])
    assignment = assign_samples(split, samples)
    return [
        {
            "sample_id": sample.sample_id,
            "file": sample.file,
            "label": sample.content_label,
        }
        for sample in samples
        if assignment.get(sample.sample_id) == "val" and sample.content_label is not None
    ]


class ScreenDetector:
    def __init__(self, path: Path):
        payload = torch.load(path, map_location="cpu")
        from scripts.train_screen_detector import ScreenRegressor

        self.model = ScreenRegressor(pretrained=False)
        self.model.load_state_dict(payload["state_dict"])
        self.model.eval()
        self.input_size = int(payload.get("input_size", 224))

    @torch.no_grad()
    def predict(self, image: np.ndarray) -> tuple[float, float, float, float]:
        resized = cv2.resize(
            image, (self.input_size, self.input_size), interpolation=cv2.INTER_AREA
        )
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        mean = torch.tensor((0.485, 0.456, 0.406)).view(3, 1, 1)
        std = torch.tensor((0.229, 0.224, 0.225)).view(3, 1, 1)
        tensor = ((tensor - mean) / std).unsqueeze(0)
        box = self.model(tensor)[0].cpu().numpy().tolist()
        return tuple(float(value) for value in box)


def crop_box(image: np.ndarray, box, margin: float):
    height, width = image.shape[:2]
    x1, y1, x2, y2 = box
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    aspect = (x2 - x1) / max(y2 - y1, 1e-6)
    if area < 0.04 or area > 0.92 or not 0.5 <= aspect <= 2.5:
        return None
    pad_x = (x2 - x1) * margin
    pad_y = (y2 - y1) * margin
    left = max(0, int(round((x1 - pad_x) * width)))
    top = max(0, int(round((y1 - pad_y) * height)))
    right = min(width, int(round((x2 + pad_x) * width)))
    bottom = min(height, int(round((y2 + pad_y) * height)))
    if right - left < 32 or bottom - top < 32:
        return None
    return image[top:bottom, left:right]


def classify(classifier: CnnClassifier, image: np.ndarray) -> str:
    probabilities = classifier.predict_proba([image])[0]
    return CLASSES[int(probabilities.argmax())]


def rectify_crop(image: np.ndarray, config: dict) -> np.ndarray:
    height, width = image.shape[:2]
    if height < 32 or width < 32:
        return image
    quad = detect_document(
        image,
        canny_low=int(config["rectify"]["canny_low"]),
        canny_high=int(config["rectify"]["canny_high"]),
        min_area_ratio=0.15,
        max_area_ratio=0.98,
    )
    if quad is not None:
        return warp_document(
            image, quad, output_long_edge=int(config["rectify"]["output_long_edge"])
        )
    return image


def metrics(y_true, y_pred):
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=list(CLASSES)).tolist(),
    }


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    items = load_val_items(config)
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(
        out_dir.name,
        out_dir,
        "scripts/eval_screen_fallback.py",
        args,
        config,
        root=ROOT,
        notes="屏幕检测兜底评估；自采验证集，外部 SCB 只训练屏幕检测器",
    )
    classifier = CnnClassifier.load(args.cnn_run / "cnn.pt", device="cpu")
    detector = ScreenDetector(args.screen_run / "screen_detector.pt")
    true_labels = []
    baseline_predictions = []
    fallback_predictions = []
    changed = []
    for item in items:
        loaded = load_image(
            ROOT / config["data"]["raw_dir"] / item["file"], max_long_edge=1280
        )
        image = loaded.image
        quad = detect_document(
            image,
            canny_low=int(config["rectify"]["canny_low"]),
            canny_high=int(config["rectify"]["canny_high"]),
            min_area_ratio=float(config["rectify"]["min_area_ratio"]),
            max_area_ratio=float(config["rectify"]["max_area_ratio"]),
        )
        baseline_image = (
            warp_document(
                image, quad, output_long_edge=int(config["rectify"]["output_long_edge"])
            )
            if quad is not None
            else image
        )
        baseline_pred = classify(classifier, baseline_image)
        fallback_pred = baseline_pred
        if quad is None:
            box = detector.predict(image)
            crop = crop_box(image, box, args.margin)
            if crop is not None:
                fallback_pred = classify(classifier, rectify_crop(crop, config))
        true_labels.append(item["label"])
        baseline_predictions.append(baseline_pred)
        fallback_predictions.append(fallback_pred)
        if baseline_pred != fallback_pred:
            changed.append(
                {
                    "sample_id": item["sample_id"],
                    "true": item["label"],
                    "baseline": baseline_pred,
                    "fallback": fallback_pred,
                }
            )
    baseline_metrics = metrics(true_labels, baseline_predictions)
    fallback_metrics = metrics(true_labels, fallback_predictions)
    result = {
        "exp_id": out_dir.name,
        "cnn_run": args.cnn_run.name,
        "screen_run": args.screen_run.name,
        "n_val": len(items),
        "baseline": baseline_metrics,
        "fallback": fallback_metrics,
        "changed": changed,
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "predictions_val.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "true_label", "baseline", "fallback"])
        for item, baseline, fallback in zip(items, baseline_predictions, fallback_predictions):
            writer.writerow([item["sample_id"], item["label"], baseline, fallback])
    print(
        f"baseline acc={baseline_metrics['accuracy']:.4f} "
        f"fallback acc={fallback_metrics['accuracy']:.4f} "
        f"changed={len(changed)}"
    )
    logger.finish(metrics={"baseline": baseline_metrics, "fallback": fallback_metrics}, extra=result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
