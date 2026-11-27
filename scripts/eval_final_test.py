"""测试集最终评估（一次性）：当前双分支链路、单模型 CNN、传统 SVM。

只在模型与配置冻结后运行一次；输出准确率、宏 F1、混淆矩阵、
按载体分组、自助法 95% 置信区间与 McNemar 检验。

用法：
    DOCNORM_PPT_MODEL=... DOCNORM_PAPER_MODELS=... \
    PYTHONPATH=src python scripts/eval_final_test.py
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.classify.classic import ClassicClassifier  # noqa: E402
from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from scripts.train_classic import build_features  # noqa: E402
from web import services  # noqa: E402


def bootstrap_ci(values: list[int], rounds: int = 1000, seed: int = 42):
    rng = np.random.default_rng(seed)
    array = np.asarray(values, dtype=np.float32)
    samples = [
        float(rng.choice(array, size=len(array), replace=True).mean())
        for _ in range(rounds)
    ]
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def mcnemar_exact(final_correct: list[int], baseline_correct: list[int]) -> dict:
    b = sum(1 for f, c in zip(final_correct, baseline_correct) if f and not c)
    c = sum(1 for f, c in zip(final_correct, baseline_correct) if not f and c)
    n = b + c
    if n == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / (2**n)
        p_value = min(1.0, 2 * tail)
    return {"final_only_correct": b, "baseline_only_correct": c, "p_value": p_value}


def final_prediction(original):
    result = services.analyze_pipeline(original, rectify=True, enhance=False)
    return result


def single_cnn_prediction(model: CnnClassifier, original):
    rectified, _quad, status = services._apply_rectify(original, None)
    tensor = model._prepare(rectified).unsqueeze(0)
    with torch.no_grad():
        probs = torch.softmax(model.model(tensor), dim=1)[0].cpu().numpy()
    index = int(probs.argmax())
    return CLASSES[index], float(probs[1]), status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "reports/final_test.json")
    parser.add_argument(
        "--predictions", type=Path, default=ROOT / "reports/final_test_predictions.csv"
    )
    parser.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()

    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(ROOT / "data/splits/split_v4.json")
    assignment = assign_samples(split, samples)
    test = [
        sample
        for sample in samples
        if assignment.get(sample.sample_id) == "test"
        and sample.content_label is not None
    ]
    if not test:
        raise SystemExit("测试集为空")

    cnn = CnnClassifier.load(ROOT / "runs/exp-cnn-05/cnn.pt", device="cpu")
    classic = ClassicClassifier.load(ROOT / "runs/exp-20261126-08/svm.joblib")
    classic_features, classic_labels, classic_ids, _failures = build_features(
        test,
        services.CONFIG,
        use_rectify=True,
        use_enhance=False,
        label_overrides={},
        corner_overrides={},
        corner_policy="none",
    )
    classic_probs = classic.predict_proba(classic_features)
    classic_pred = {
        sample_id: classic.classes_[int(prob.argmax())]
        for sample_id, prob in zip(classic_ids, classic_probs)
    }

    rows = []
    for sample in test:
        loaded = load_image(
            ROOT / "data/raw_samples" / sample.file, max_long_edge=1280
        )
        original = services._limit_long_edge(loaded.image, 2000)
        result = final_prediction(original)
        final_label = result["label"]
        cnn_label, cnn_prob_formula, cnn_status = single_cnn_prediction(cnn, original)
        trad_label = classic_pred.get(sample.sample_id)
        true_label = sample.content_label
        carrier = (sample.label or "").split("_")[0]
        rows.append(
            {
                "sample_id": sample.sample_id,
                "true_label": true_label,
                "carrier": carrier,
                "carrier_pred": result["routing"].get("carrier", "unknown"),
                "carrier_override": bool(result["routing"].get("carrier_override")),
                "gate_uncertain": bool(result["routing"].get("uncertain")),
                "final_pred": final_label or "",
                "final_prob_formula": (
                    round(float(result["probabilities"]["formula"]), 6)
                    if result["probabilities"]
                    else None
                ),
                "final_status": result["status"],
                "classifier_status": result["classifier_status"],
                "display_quad": bool(result["display_quad"]),
                "cnn_pred": cnn_label,
                "cnn_prob_formula": round(cnn_prob_formula, 6),
                "cnn_status": cnn_status,
                "classic_pred": trad_label or "",
            }
        )

    def metrics(key: str) -> dict:
        y = [row["true_label"] for row in rows]
        p = [row[key] for row in rows]
        return {
            "accuracy": float(accuracy_score(y, p)),
            "macro_f1": float(f1_score(y, p, average="macro")),
            "confusion_matrix": confusion_matrix(y, p, labels=list(CLASSES)).tolist(),
            "per_class_recall": {
                label: float(
                    sum(1 for t, q in zip(y, p) if t == label and q == label)
                    / max(1, sum(1 for t in y if t == label))
                )
                for label in CLASSES
            },
        }

    final_correct = [int(row["final_pred"] == row["true_label"]) for row in rows]
    cnn_correct = [int(row["cnn_pred"] == row["true_label"]) for row in rows]
    classic_correct = [int(row["classic_pred"] == row["true_label"]) for row in rows]
    carrier_stats = defaultdict(lambda: {"n": 0, "correct": 0})
    for row in rows:
        key = row["carrier"]
        carrier_stats[key]["n"] += 1
        carrier_stats[key]["correct"] += int(row["final_pred"] == row["true_label"])

    payload = {
        "split": "test",
        "n": len(rows),
        "final": metrics("final_pred"),
        "single_cnn": metrics("cnn_pred"),
        "classic_svm": metrics("classic_pred"),
        "final_per_carrier": {
            name: {
                "n": value["n"],
                "accuracy": value["correct"] / value["n"],
            }
            for name, value in carrier_stats.items()
        },
        "final_accuracy_ci95": bootstrap_ci(final_correct, args.bootstrap),
        "mcnemar_final_vs_single_cnn": mcnemar_exact(final_correct, cnn_correct),
        "mcnemar_final_vs_classic_svm": mcnemar_exact(final_correct, classic_correct),
        "status_counts": {
            "final_ok": sum(1 for row in rows if row["final_status"] == "ok"),
            "classifier_ok": sum(
                1 for row in rows if row["classifier_status"] == "ok"
            ),
            "display_quad": sum(1 for row in rows if row["display_quad"]),
        },
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with args.predictions.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    for name in ("final", "single_cnn", "classic_svm"):
        m = payload[name]
        print(
            f"{name}: acc={m['accuracy']:.4f} f1={m['macro_f1']:.4f} "
            f"conf={m['confusion_matrix']}"
        )
    print(f"final CI95={payload['final_accuracy_ci95']}")
    print(f"mcnemar vs CNN={payload['mcnemar_final_vs_single_cnn']}")
    print(f"mcnemar vs SVM={payload['mcnemar_final_vs_classic_svm']}")
    print(f"保存 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
