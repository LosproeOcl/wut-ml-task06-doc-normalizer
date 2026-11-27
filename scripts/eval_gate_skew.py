"""载体门控在合成空间偏度下的阈值与 TTA 评估。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.classify.gate import ScreenGate  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from scripts.eval_spatial_skew import resolve_sample_path, rotate, synthetic_skew  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", type=Path, default=ROOT / "runs/carrier-gate-01/screen_gate.pt")
    parser.add_argument("--angles", default="0,10,20,30,40")
    parser.add_argument("--out", type=Path, default=ROOT / "reports/gate_skew.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    angles = [float(value) for value in args.angles.split(",") if value.strip()]
    gate = ScreenGate.from_checkpoint(args.gate)
    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    assignment = assign_samples(load_split(ROOT / "data/splits/split_v4.json"), samples)
    items = [
        sample
        for sample in samples
        if assignment.get(sample.sample_id) == "val"
        and (sample.label or "").startswith(("ppt_", "paper_"))
    ]
    print(f"验证集 {len(items)} 张，angles {angles}")
    results = {}
    for angle in angles:
        labels = []
        raw_probs = []
        tta_probs = []
        for index, sample in enumerate(items):
            loaded = load_image(resolve_sample_path(sample), max_long_edge=1280)
            original = loaded.image
            warped = synthetic_skew(original, angle, "top" if index % 2 == 0 else "side")
            labels.append(1 if sample.label.startswith("ppt_") else 0)
            raw_probs.append(float(gate.predict(warped)))
            tta_probs.append(
                float(np.mean([gate.predict(rotate(warped, delta)) for delta in (-12, 0, 12)]))
            )
        labels_array = np.asarray(labels)
        raw = np.asarray(raw_probs)
        tta = np.asarray(tta_probs)
        row = {"n": len(labels), "ppt": int(labels_array.sum()), "paper": int((1 - labels_array).sum())}
        for name, probs in (("raw", raw), ("tta", tta)):
            row[f"{name}_auc"] = float(roc_auc_score(labels_array, probs))
            row[f"{name}_thresholds"] = {}
            for threshold in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
                pred = (probs >= threshold).astype(int)
                ppt_recall = float((pred[labels_array == 1] == 1).mean())
                paper_recall = float((pred[labels_array == 0] == 0).mean())
                row[f"{name}_thresholds"][f"{threshold:.1f}"] = {
                    "accuracy": float((pred == labels_array).mean()),
                    "ppt_recall": ppt_recall,
                    "paper_recall": paper_recall,
                    "balanced": (ppt_recall + paper_recall) / 2,
                }
        results[str(int(angle))] = row
        best = max(
            (item for item in row["raw_thresholds"].items()),
            key=lambda pair: pair[1]["balanced"],
        )
        print(
            f"{angle:>4.0f}° auc={row['raw_auc']:.3f}/{row['tta_auc']:.3f} "
            f"raw@{best[0]} bal={best[1]['balanced']:.3f} "
            f"ppt={best[1]['ppt_recall']:.3f} paper={best[1]['paper_recall']:.3f}"
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
