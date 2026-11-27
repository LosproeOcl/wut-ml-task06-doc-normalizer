"""在自采验证集上评估网页双分支链路：载体门控 + 纸质稿集成 / PPT CNN。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.classify.cnn import CLASSES  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from web import services  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="val")
    parser.add_argument("--json-out", type=Path, default=ROOT / "reports/routed_pipeline.json")
    parser.add_argument(
        "--predictions",
        type=Path,
        default=ROOT / "reports/eval_paper/routed_val.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    assignment = assign_samples(load_split(ROOT / "data/splits/split_v4.json"), samples)
    rows = []
    labels = []
    predictions = []
    carriers = []
    branches = Counter()
    for sample in samples:
        if assignment.get(sample.sample_id) != args.split:
            continue
        if sample.content_label is None:
            continue
        loaded = load_image(ROOT / "data/raw_samples" / sample.file, max_long_edge=1280)
        original = services._limit_long_edge(loaded.image, 2000)
        result = services.analyze_pipeline(original, rectify=True, enhance=False)
        status = result["status"]
        label = result["label"]
        probabilities = result["probabilities"]
        routing = result["routing"]
        true_label = sample.content_label
        carrier = (sample.label or "").split("_")[0]
        labels.append(true_label)
        predictions.append(label or "")
        carriers.append(carrier)
        branches[routing.get("branch", "unknown")] += 1
        rows.append(
            {
                "sample_id": sample.sample_id,
                "label": true_label,
                "carrier": carrier,
                "pred": label or "",
                "correct": int((label or "") == true_label),
                "prob_text": "" if not probabilities else f"{probabilities['text']:.6f}",
                "prob_formula": "" if not probabilities else f"{probabilities['formula']:.6f}",
                "carrier_pred": routing.get("carrier", "unknown"),
                "branch": routing.get("branch", "unknown"),
                "status": status,
            }
        )
    y = np.asarray(labels)
    p = np.asarray(predictions)
    result = {
        "split": args.split,
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, p)),
        "macro_f1": float(f1_score(y, p, average="macro")),
        "confusion_matrix": confusion_matrix(y, p, labels=list(CLASSES)).tolist(),
        "per_carrier_accuracy": {},
        "per_class_recall": {},
        "branches": dict(branches),
    }
    for carrier in ("ppt", "paper"):
        mask = np.asarray(carriers) == carrier
        result["per_carrier_accuracy"][carrier] = (
            float((p[mask] == y[mask]).mean()) if mask.any() else None
        )
    for name in CLASSES:
        mask = y == name
        result["per_class_recall"][name] = (
            float((p[mask] == name).mean()) if mask.any() else None
        )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    with args.predictions.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"routed {args.split}: n={result['n']} acc={result['accuracy']:.4f} "
        f"f1={result['macro_f1']:.4f} conf={result['confusion_matrix']} "
        f"carrier={result['per_carrier_accuracy']} branches={result['branches']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
