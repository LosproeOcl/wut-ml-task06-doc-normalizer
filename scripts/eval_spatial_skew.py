"""空间偏度压力测试：对现有 PPT 验证页做合成透视，不新增样本。

评估两条路径：
1. 分类器：先按当前 webapp 拉正，再对拉正图施加合成透视；
2. 完整链路：对原始图施加合成透视，再走拉正 + 载体门控 + 分支分类。

用法：
    PYTHONPATH=src python scripts/eval_spatial_skew.py --out reports/spatial_skew.json
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
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.classify.gate import ScreenGate  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from web import services  # noqa: E402


def resolve_sample_path(sample) -> Path:
    path = ROOT / "data/raw_samples" / sample.file
    if path.is_file():
        return path
    matches = sorted((ROOT / "data/raw_samples").rglob(Path(sample.file).name))
    if not matches:
        raise FileNotFoundError(f"找不到样本文件: {sample.file}")
    return matches[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT / "runs/exp-cnn-05")
    parser.add_argument("--angles", default="0,10,20,30,40")
    parser.add_argument(
        "--tta",
        choices=("none", "rotations"),
        default="none",
        help="rotations：在 -15..15 度旋转上平均概率",
    )
    parser.add_argument(
        "--gate", type=Path, default=ROOT / "runs/carrier-gate-01/screen_gate.pt"
    )
    parser.add_argument(
        "--gate-threshold",
        type=float,
        default=None,
        help="覆盖门控阈值；配合 --gate-tta 评估偏度优化",
    )
    parser.add_argument(
        "--gate-tta",
        action="store_true",
        help="门控在 -12/0/12 度旋转上平均",
    )
    parser.add_argument(
        "--paper-checkpoint",
        action="append",
        type=Path,
        default=[
            ROOT / "runs/paper-cnn-extctl-01/paper_cnn.pt",
            ROOT / "runs/paper-cnn-extctl-43/paper_cnn.pt",
            ROOT / "runs/paper-cnn-extctl-44/paper_cnn.pt",
        ],
    )
    parser.add_argument("--out", type=Path, default=ROOT / "reports/spatial_skew.json")
    parser.add_argument(
        "--predictions",
        type=Path,
        default=ROOT / "reports/spatial_skew_predictions.csv",
    )
    return parser.parse_args()


def synthetic_skew(image: np.ndarray, angle_deg: float, direction: str) -> np.ndarray:
    """对图像施加梯形透视，模拟相机与幕布不垂直。"""
    if angle_deg <= 0:
        return image.copy()
    height, width = image.shape[:2]
    shift = min(width * 0.35, height * 0.55 * np.tan(np.radians(angle_deg)))
    src = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    if direction == "top":
        dst = np.float32([[shift, 0], [width - shift, 0], [width, height], [0, height]])
    else:
        dst = np.float32([[0, shift], [width, 0], [width, height - shift], [0, height]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(
        image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE
    )


def rotate(image: np.ndarray, angle: float) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE
    )


@torch.no_grad()
def predict(model: CnnClassifier, image: np.ndarray, tta: str) -> tuple[str, np.ndarray]:
    if tta == "none":
        probabilities = model.predict_proba([image])[0]
    else:
        angles = (-15, -10, -5, 0, 5, 10, 15)
        probabilities = np.mean(
            [model.predict_proba([rotate(image, angle)])[0] for angle in angles], axis=0
        )
    return CLASSES[int(probabilities.argmax())], probabilities


@torch.no_grad()
def predict_ensemble(models, image: np.ndarray) -> tuple[str, np.ndarray]:
    probabilities = np.mean([model.predict_proba([image])[0] for model in models], axis=0)
    return CLASSES[int(probabilities.argmax())], probabilities


def metrics(labels, predictions) -> dict:
    return {
        "n": len(labels),
        "accuracy": float(accuracy_score(labels, predictions)),
        "macro_f1": float(f1_score(labels, predictions, average="macro")),
        "confusion_matrix": confusion_matrix(
            labels, predictions, labels=list(CLASSES)
        ).tolist(),
    }


def main() -> int:
    args = parse_args()
    angles = [float(value) for value in args.angles.split(",") if value.strip()]
    run_dir = args.run if args.run.is_absolute() else ROOT / args.run
    model = CnnClassifier.load(run_dir / "cnn.pt", device="cpu")
    gate = None
    paper_models = []
    if args.gate_threshold is not None:
        gate = ScreenGate.from_checkpoint(
            args.gate if args.gate.is_absolute() else ROOT / args.gate
        )
        paper_models = [
            CnnClassifier.load(path if path.is_absolute() else ROOT / path, device="cpu")
            for path in args.paper_checkpoint
            if (path if path.is_absolute() else ROOT / path).is_file()
        ]
    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    assignment = assign_samples(load_split(ROOT / "data/splits/split_v3.json"), samples)
    items = [
        sample
        for sample in samples
        if assignment.get(sample.sample_id) == "val"
        and (sample.label or "").startswith("ppt_")
        and sample.content_label
    ]
    print(f"PPT 验证页 {len(items)} 张，角度 {angles}，TTA={args.tta}")

    rows = []
    classifier_results = {}
    pipeline_results = {}
    for angle in angles:
        labels = []
        classifier_predictions = []
        pipeline_predictions = []
        for index, sample in enumerate(items):
            loaded = load_image(resolve_sample_path(sample), max_long_edge=1280)
            original = services._limit_long_edge(loaded.image, 2000)
            rectified, _quad, _status = services._apply_rectify(original)
            direction = "top" if index % 2 == 0 else "side"
            warped_rectified = synthetic_skew(rectified, angle, direction)
            warped_original = synthetic_skew(original, angle, direction)
            classifier_pred, classifier_prob = predict(
                model, warped_rectified, args.tta
            )
            if gate is not None:
                if args.gate_tta:
                    gate_prob = float(
                        np.mean(
                            [gate.predict(rotate(warped_original, delta)) for delta in (-12, 0, 12)]
                        )
                    )
                else:
                    gate_prob = float(gate.predict(warped_original))
                pipeline_carrier = "ppt" if gate_prob >= args.gate_threshold else "paper"
                if pipeline_carrier == "ppt":
                    pipeline_pred, _pipeline_prob = predict(model, warped_rectified, args.tta)
                    pipeline_branch = "ppt-cnn-exp-cnn-05"
                elif paper_models:
                    pipeline_pred, _pipeline_prob = predict_ensemble(
                        paper_models, warped_rectified
                    )
                    pipeline_branch = f"paper-cnn-ensemble-{len(paper_models)}"
                else:
                    pipeline_pred = ""
                    pipeline_branch = "paper-missing"
                carrier_prob_paper = 1.0 - gate_prob
                carrier_prob_ppt = gate_prob
            else:
                _label, _prob, routing = services._classify(warped_original, warped_rectified)
                pipeline_pred = _label or ""
                pipeline_carrier = routing.get("carrier", "unknown")
                pipeline_branch = routing.get("branch", "unknown")
                carrier_prob_paper = None if not routing.get("carrier_probabilities") else routing["carrier_probabilities"]["paper"]
                carrier_prob_ppt = None if not routing.get("carrier_probabilities") else routing["carrier_probabilities"]["ppt"]
            labels.append(sample.content_label)
            classifier_predictions.append(classifier_pred)
            pipeline_predictions.append(pipeline_pred)
            rows.append(
                {
                    "sample_id": sample.sample_id,
                    "angle": angle,
                    "carrier": "ppt",
                    "label": sample.content_label,
                    "classifier_pred": classifier_pred,
                    "classifier_prob_formula": f"{float(classifier_prob[1]):.6f}",
                    "pipeline_pred": pipeline_pred,
                    "pipeline_carrier": pipeline_carrier,
                    "pipeline_branch": pipeline_branch,
                    "carrier_prob_paper": "" if carrier_prob_paper is None else f"{carrier_prob_paper:.6f}",
                    "carrier_prob_ppt": "" if carrier_prob_ppt is None else f"{carrier_prob_ppt:.6f}",
                }
            )
        classifier_results[str(int(angle))] = metrics(labels, classifier_predictions)
        pipeline_results[str(int(angle))] = metrics(labels, pipeline_predictions)
        print(
            f"{angle:>4.0f}° classifier={classifier_results[str(int(angle))]['accuracy']:.4f} "
            f"pipeline={pipeline_results[str(int(angle))]['accuracy']:.4f}"
        )

    result = {
        "run": str(run_dir.relative_to(ROOT)),
        "carrier": "ppt",
        "n": len(items),
        "tta": args.tta,
        "classifier": classifier_results,
        "pipeline": pipeline_results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    with args.predictions.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"写入 {args.out} 与 {args.predictions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
