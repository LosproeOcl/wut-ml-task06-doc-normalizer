"""用人工四角标注调优 OpenCV 检测器参数。

OpenCV 检测器本身是规则算法，不能像 CNN 那样端到端训练；这里把人工
四角当作监督信号，对 Canny 阈值与面积门槛做网格搜索，并按文档页分组
切分训练/验证，避免同一页跨集合。

用法：
    PYTHONPATH=src python3 scripts/tune_rectify_detector.py --carrier all
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.annotations import ManualCornerStore, scale_points  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from docnorm.rectify.detector import detect_document  # noqa: E402

DEFAULT = {"canny_low": 50, "canny_high": 150, "min_area": 0.15, "max_area": 0.98}
CANNY_PAIRS = [
    (30, 90),
    (50, 120),
    (50, 150),
    (70, 150),
    (70, 200),
    (90, 250),
]
AREA_MINS = [0.05, 0.10, 0.15, 0.20]
AREA_MAXES = [0.98, 0.99]


def carrier_of(label: str | None) -> str:
    return "ppt" if (label or "").startswith("ppt_") else "paper"


def build_items(carrier: str, seed: int) -> tuple[list[dict], list[dict]]:
    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    assignment = assign_samples(load_split(ROOT / "data/splits/split_v4.json"), samples)
    corners = ManualCornerStore(ROOT / "data/annotations/manual_corners.csv").load()
    by_group: dict[str, list] = defaultdict(list)
    for sample in samples:
        if assignment.get(sample.sample_id) != "train":
            continue
        if sample.sample_id not in corners:
            continue
        if carrier != "all" and carrier_of(sample.label) != carrier:
            continue
        by_group[sample.doc_page_id].append(sample)
    groups = sorted(by_group)
    rng = random.Random(seed)
    rng.shuffle(groups)
    val_groups = set(groups[: max(1, round(len(groups) * 0.2))])
    train_items, val_items = [], []
    for group, members in by_group.items():
        target = val_items if group in val_groups else train_items
        for sample in members:
            target.append(
                {
                    "sample_id": sample.sample_id,
                    "file": sample.file,
                    "label": sample.label,
                    "group": sample.doc_page_id,
                    "points": corners[sample.sample_id],
                }
            )
    return train_items, val_items


def load_gray(item: dict) -> tuple[np.ndarray, np.ndarray]:
    loaded = load_image(ROOT / "data/raw_samples" / item["file"], max_long_edge=1280)
    image = loaded.image
    points = np.asarray(
        scale_points(item["points"], loaded.original_size, image.shape), dtype=np.float32
    )
    height, width = image.shape[:2]
    target = points / np.array([width, height], dtype=np.float32)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), target


def evaluate(
    items: list[dict],
    cache: dict[str, tuple[np.ndarray, np.ndarray]],
    params: dict,
) -> dict:
    errors = []
    failures = 0
    carrier_stats = defaultdict(lambda: {"n": 0, "ok": 0, "errors": []})
    for item in items:
        sample_id = item["sample_id"]
        if sample_id not in cache:
            cache[sample_id] = load_gray(item)
        gray, target = cache[sample_id]
        carrier = carrier_of(item["label"])
        carrier_stats[carrier]["n"] += 1
        quad = detect_document(
            gray,
            canny_low=int(params["canny_low"]),
            canny_high=int(params["canny_high"]),
            min_area_ratio=float(params["min_area"]),
            max_area_ratio=float(params["max_area"]),
        )
        if quad is None:
            failures += 1
            continue
        height, width = gray.shape[:2]
        detected = np.asarray(quad.points, dtype=np.float32) / np.array(
            [width, height], dtype=np.float32
        )
        error = float(np.linalg.norm(detected.reshape(-1) - target.reshape(-1)))
        errors.append(error)
        carrier_stats[carrier]["ok"] += 1
        carrier_stats[carrier]["errors"].append(error)
    total = len(items)
    success = (total - failures) / total if total else 0.0
    mean_error = float(np.mean(errors)) if errors else None
    per_carrier = {}
    for name, stat in carrier_stats.items():
        per_carrier[name] = {
            "n": stat["n"],
            "success": stat["ok"] / stat["n"] if stat["n"] else 0.0,
            "mean_l2": float(np.mean(stat["errors"])) if stat["errors"] else None,
        }
    return {
        "n": total,
        "success": success,
        "failures": failures,
        "mean_l2": mean_error,
        "median_l2": float(np.median(errors)) if errors else None,
        "per_carrier": per_carrier,
    }


def score(result: dict) -> tuple[float, float]:
    # 先保证检出，再比较成功样本的角点误差。
    return (result["success"], -(result["mean_l2"] or 1.0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carrier", choices=("all", "ppt", "paper"), default="all")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "runs/rectify-tune-01")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    train_items, val_items = build_items(args.carrier, args.seed)
    print(
        f"carrier={args.carrier} train={len(train_items)} val={len(val_items)} "
        f"train_groups={len({i['group'] for i in train_items})} "
        f"val_groups={len({i['group'] for i in val_items})}"
    )
    if args.dry_run:
        return 0
    cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    results = []

    def run(params: dict, stage: str) -> dict:
        train_metrics = evaluate(train_items, cache, params)
        row = {
            "stage": stage,
            "params": params,
            "train": train_metrics,
        }
        results.append(row)
        print(
            f"[{stage}] {params} train success={train_metrics['success']:.4f} "
            f"l2={train_metrics['mean_l2']}"
        )
        return row

    baseline = run(dict(DEFAULT), "baseline")
    best = baseline
    for low, high in CANNY_PAIRS:
        params = dict(DEFAULT, canny_low=low, canny_high=high)
        row = run(params, "canny")
        if score(row["train"]) > score(best["train"]):
            best = row
    best_canny = dict(best["params"])
    for min_area in AREA_MINS:
        for max_area in AREA_MAXES:
            params = dict(best_canny, min_area=min_area, max_area=max_area)
            row = run(params, "area")
            if score(row["train"]) > score(best["train"]):
                best = row
    final = dict(best["params"])
    val_metrics = evaluate(val_items, cache, final)
    val_default = evaluate(val_items, cache, dict(DEFAULT))
    print(
        f"best={final} val success={val_metrics['success']:.4f} "
        f"l2={val_metrics['mean_l2']} (default val success={val_default['success']:.4f} "
        f"l2={val_default['mean_l2']})"
    )
    payload = {
        "carrier": args.carrier,
        "n_train": len(train_items),
        "n_val": len(val_items),
        "default": DEFAULT,
        "best": final,
        "val_best": val_metrics,
        "val_default": val_default,
        "results": results,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "tune.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"保存 {args.out / 'tune.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
