"""在同一组验证样本上对比学习四角与 OpenCV 检测。

训练脚本按 doc_page_id 分组切分；本脚本复现同一随机种子与切分，
读取指定四角模型，与 detect_document 的四角误差对照。

用法：
    PYTHONPATH=src python3 scripts/eval_ppt_quad.py
    PYTHONPATH=src python3 scripts/eval_ppt_quad.py --carrier paper \
      --model runs/quad-paper-01/quad_ppt.pt --out runs/quad-paper-01/eval_vs_detector.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
from torchvision import models

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.annotations import ManualCornerStore, scale_points  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class QuadNet(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        base = models.mobilenet_v3_small(weights=None)
        self.features = base.features
        self.avgpool = base.avgpool
        self.head = torch.nn.Sequential(
            torch.nn.Linear(576, 256),
            torch.nn.Hardswish(),
            torch.nn.Dropout(0.2),
            torch.nn.Linear(256, 8),
            torch.nn.Sigmoid(),
        )

    def forward(self, images):
        return self.head(torch.flatten(self.avgpool(self.features(images)), 1))


def load_model(path: Path) -> tuple[torch.nn.Module, int]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    input_size = int(checkpoint.get("input_size", 224))
    net = QuadNet()
    net.load_state_dict(checkpoint["state_dict"])
    net.eval()
    return net, input_size


def prepare_tensor(image: np.ndarray, input_size: int) -> torch.Tensor:
    resized = cv2.resize(image, (input_size, input_size), interpolation=cv2.INTER_AREA)
    resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(resized).permute(2, 0, 1).float() / 255.0
    mean = torch.tensor(MEAN).view(3, 1, 1)
    std = torch.tensor(STD).view(3, 1, 1)
    return ((tensor - mean) / std).unsqueeze(0)


def val_items(seed: int, carrier: str = "ppt") -> list[dict]:
    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    assignment = assign_samples(load_split(ROOT / "data/splits/split_v4.json"), samples)
    corners = ManualCornerStore(ROOT / "data/annotations/manual_corners.csv").load()
    by_group: dict[str, list] = defaultdict(list)
    for sample in samples:
        if carrier != "all" and not (sample.label or "").startswith(carrier + "_"):
            continue
        if assignment.get(sample.sample_id) != "train":
            continue
        if sample.sample_id not in corners:
            continue
        by_group[sample.doc_page_id].append(sample)
    groups = sorted(by_group)
    rng = random.Random(seed)
    rng.shuffle(groups)
    val_groups = set(groups[: max(1, round(len(groups) * 0.2))])
    items: list[dict] = []
    for group in sorted(val_groups):
        for sample in by_group[group]:
            items.append(
                {
                    "sample_id": sample.sample_id,
                    "file": sample.file,
                    "points": corners[sample.sample_id],
                }
            )
    return items


def quad_error(pred_norm: np.ndarray, target_norm: np.ndarray) -> float:
    return float(np.linalg.norm(pred_norm.reshape(-1) - target_norm.reshape(-1)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "runs/quad-ppt-01/quad_ppt.pt")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--carrier", choices=("ppt", "paper", "all"), default="ppt")
    parser.add_argument("--canny-low", type=int, default=90)
    parser.add_argument("--canny-high", type=int, default=250)
    parser.add_argument("--min-area", type=float, default=0.15)
    parser.add_argument("--max-area", type=float, default=0.98)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "runs/quad-ppt-01/eval_vs_detector.json"
    )
    args = parser.parse_args()
    net, input_size = load_model(args.model)
    items = val_items(args.seed, args.carrier)
    learned_errors: list[float] = []
    detector_errors: list[float] = []
    detector_failed = 0
    rows = []
    for item in items:
        loaded = load_image(
            ROOT / "data/raw_samples" / item["file"], max_long_edge=1280
        )
        image = loaded.image
        points = np.asarray(
            scale_points(item["points"], loaded.original_size, image.shape),
            dtype=np.float32,
        )
        height, width = image.shape[:2]
        target = points / np.array([width, height], dtype=np.float32)
        with torch.no_grad():
            prediction = net(prepare_tensor(image, input_size)).numpy()[0]
        learned = quad_error(prediction, target.reshape(-1))
        learned_errors.append(learned)
        quad = detect_document(
            image,
            canny_low=args.canny_low,
            canny_high=args.canny_high,
            min_area_ratio=args.min_area,
            max_area_ratio=args.max_area,
        )
        if quad is None:
            detector_failed += 1
            detector = None
            detector_error = None
        else:
            detected = np.asarray(quad.points, dtype=np.float32)
            detected = detected / np.array([width, height], dtype=np.float32)
            detector = detected.tolist()
            detector_error = quad_error(detected, target.reshape(-1))
            detector_errors.append(detector_error)
        rows.append(
            {
                "sample_id": item["sample_id"],
                "learned_quad": prediction.tolist(),
                "detector_quad": detector,
                "detector_method": quad.method if quad else None,
                "target_quad": target.tolist(),
                "learned_l2": learned,
                "detector_l2": detector_error,
            }
        )
    summary = {
        "n_val": len(items),
        "learned_mean_l2": float(np.mean(learned_errors)),
        "learned_median_l2": float(np.median(learned_errors)),
        "detector_success": len(detector_errors),
        "detector_failed": detector_failed,
        "detector_mean_l2_on_success": float(np.mean(detector_errors))
        if detector_errors
        else None,
        "detector_median_l2_on_success": float(np.median(detector_errors))
        if detector_errors
        else None,
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"n={summary['n_val']} learned_l2={summary['learned_mean_l2']:.4f} "
        f"detector_success={summary['detector_success']}/{summary['n_val']} "
        f"detector_l2={summary['detector_mean_l2_on_success']}"
    )
    print(f"保存 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
