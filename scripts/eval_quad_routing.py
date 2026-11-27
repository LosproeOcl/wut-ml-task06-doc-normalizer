"""评估学习四角在双分支链路中的三种接入策略。

策略：
- opencv：只用 OpenCV（按载体选参），失败时保留原图；
- fallback：OpenCV 成功时用它，失败时用该载体的学习四角；
- learned：优先用学习四角，学习结果不合法时回退 OpenCV。

用法：
    PYTHONPATH=src python3 scripts/eval_quad_routing.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from docnorm.rectify.geometry import DocumentQuad, RectifyError  # noqa: E402
from docnorm.rectify.warp import warp_document  # noqa: E402
from scripts.eval_ppt_quad import load_model, prepare_tensor  # noqa: E402
from web import services  # noqa: E402


def learned_quad(model, input_size: int, image: np.ndarray) -> DocumentQuad | None:
    tensor = prepare_tensor(image, input_size)
    import torch

    with torch.no_grad():
        prediction = model(tensor).numpy()[0]
    height, width = image.shape[:2]
    points = prediction.reshape(4, 2) * np.array([width, height], dtype=np.float32)
    try:
        quad = DocumentQuad(points)
    except (RectifyError, ValueError):
        return None
    if not 0.10 <= quad_area_ratio(quad.points, width, height) <= 0.99:
        return None
    return quad


def quad_area_ratio(points: np.ndarray, width: int, height: int) -> float:
    x = points[:, 0]
    y = points[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    return area / float(width * height)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ppt-model", type=Path, default=ROOT / "runs/quad-ppt-02/quad_ppt.pt")
    parser.add_argument("--paper-model", type=Path, default=ROOT / "runs/quad-paper-01/quad_ppt.pt")
    parser.add_argument("--out", type=Path, default=ROOT / "reports/quad_routing_eval.json")
    args = parser.parse_args()

    ppt_model, ppt_size = load_model(args.ppt_model)
    paper_model, paper_size = load_model(args.paper_model)
    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(ROOT / "data/splits/split_v4.json")
    assignment = assign_samples(split, samples)
    val = [
        sample
        for sample in samples
        if assignment.get(sample.sample_id) == "val" and sample.content_label is not None
    ]
    rows = []
    for sample in val:
        loaded = load_image(ROOT / "data/raw_samples" / sample.file, max_long_edge=1280)
        original = services._limit_long_edge(loaded.image, 2000)
        carrier, carrier_probs = services._carrier_info(original)
        cv_rectified, cv_quad, cv_status = services._apply_rectify(original, carrier)

        model, size = (ppt_model, ppt_size) if carrier == "ppt" else (paper_model, paper_size)
        q = learned_quad(model, size, original)
        learned_rectified = None
        if q is not None:
            learned_rectified = warp_document(
                original,
                q,
                output_long_edge=int(services.CONFIG["rectify"]["output_long_edge"]),
            )

        strategies = {
            "opencv": cv_rectified,
            "fallback": cv_rectified if cv_quad is not None else (learned_rectified if learned_rectified is not None else original),
            "learned": learned_rectified if learned_rectified is not None else cv_rectified,
        }
        row = {
            "sample_id": sample.sample_id,
            "label": sample.content_label,
            "carrier": (sample.label or "").split("_")[0],
            "carrier_pred": carrier,
            "opencv_status": cv_status,
            "learned_valid": q is not None,
        }
        probability_sets = {}
        for name, image in strategies.items():
            label, probabilities, routing = services._classify(
                original, image, (carrier, carrier_probs)
            )
            probability_sets[name] = probabilities
            row[f"{name}_pred"] = label
            row[f"{name}_correct"] = int(label == sample.content_label)
            row[f"{name}_prob_formula"] = (
                round(float(probabilities["formula"]), 6) if probabilities else None
            )
            row[f"{name}_branch"] = routing.get("branch")

        def add_average(name, keys):
            sets = [probability_sets[key] for key in keys if probability_sets.get(key)]
            if not sets:
                return
            averaged = {
                cls: sum(values[cls] for values in sets) / len(sets)
                for cls in sets[0]
            }
            label = max(averaged, key=averaged.get)
            row[f"{name}_pred"] = label
            row[f"{name}_correct"] = int(label == sample.content_label)
            row[f"{name}_prob_formula"] = round(float(averaged["formula"]), 6)
            row[f"{name}_branch"] = "dual-view"

        add_average("dual", ["opencv", "learned"])
        add_average("triple", ["opencv", "learned", "original"])
        rows.append(row)

    summary = {}
    for name in ("opencv", "fallback", "learned", "dual", "triple"):
        y = [r["label"] for r in rows]
        p = [r[f"{name}_pred"] or "" for r in rows]
        summary[name] = {
            "accuracy": float(accuracy_score(y, p)),
            "macro_f1": float(f1_score(y, p, average="macro")),
            "confusion_matrix": confusion_matrix(y, p).tolist(),
        }
    payload = {
        "n": len(rows),
        "summary": summary,
        "status": {f"{carrier}:{status}": count for (carrier, status), count in Counter((r["carrier_pred"], r["opencv_status"]) for r in rows).items()},
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, metrics in summary.items():
        print(
            f"{name}: acc={metrics['accuracy']:.4f} f1={metrics['macro_f1']:.4f} "
            f"conf={metrics['confusion_matrix']}"
        )
    print(f"保存 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
