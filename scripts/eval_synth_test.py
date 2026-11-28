#!/usr/bin/env python3
"""在 split_v4 测试集上复验合成 PPT 模型（仅推理，不调参）。

评估 v2 / v3 / v2+v3 三个固定集成；测试集不参与训练、阈值选择或早停。
论文/纸质分支沿用已冻结的 final_test 预测，只替换 PPT 分支，便于看整体影响。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from web import services  # noqa: E402


def bootstrap_ci(values: list[int], rounds: int = 1000, seed: int = 42):
    rng = np.random.default_rng(seed)
    array = np.asarray(values, dtype=np.float32)
    samples = [float(rng.choice(array, size=len(array), replace=True).mean()) for _ in range(rounds)]
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def mcnemar_exact(a: list[int], b: list[int]) -> dict:
    only_a = sum(1 for x, y in zip(a, b) if x and not y)
    only_b = sum(1 for x, y in zip(a, b) if not x and y)
    n = only_a + only_b
    if n == 0:
        p = 1.0
    else:
        tail = sum(math.comb(n, k) for k in range(0, min(only_a, only_b) + 1)) / (2**n)
        p = min(1.0, 2 * tail)
    return {"only_a": only_a, "only_b": only_b, "p_value": p}


def metrics(y: list[str], p: list[str]) -> dict:
    return {
        "accuracy": float(accuracy_score(y, p)),
        "macro_f1": float(f1_score(y, p, average="macro")),
        "confusion_matrix": confusion_matrix(y, p, labels=list(CLASSES)).tolist(),
        "per_class_recall": {
            label: float(sum(1 for t, q in zip(y, p) if t == label and q == label) / max(1, sum(1 for t in y if t == label)))
            for label in CLASSES
        },
    }


def run_models(models: list[CnnClassifier], image: np.ndarray) -> tuple[float, float]:
    probs = []
    with torch.no_grad():
        for model in models:
            tensor = model._prepare(image).unsqueeze(0)
            logits = model.model(tensor)
            probs.append(torch.softmax(logits, dim=1)[0].cpu().numpy())
    mean = np.mean(np.stack(probs), axis=0)
    return float(mean[0]), float(mean[1])


def load_models(prefix: str) -> list[CnnClassifier]:
    paths = sorted((ROOT / "runs").glob(f"{prefix}-f*-s*/cnn.pt"))
    if not paths:
        raise SystemExit(f"找不到模型: {prefix}")
    return [CnnClassifier.load(path, device="cpu") for path in paths]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "reports/synth_test_eval.json")
    parser.add_argument("--predictions", type=Path, default=ROOT / "reports/synth_test_eval.csv")
    args = parser.parse_args()

    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    assignment = assign_samples(load_split(ROOT / "data/splits/split_v4.json"), samples)
    test = [s for s in samples if assignment.get(s.sample_id) == "test" and s.content_label is not None]
    frozen = {row["sample_id"]: row for row in json.loads((ROOT / "reports/final_test.json").read_text())["rows"]}

    v2 = load_models("exp-cnn-ppt-synth-v2")
    v3 = load_models("exp-cnn-ppt-synth-v3")
    print(f"v2 models={len(v2)} v3 models={len(v3)} test={len(test)}")

    rows = []
    for sample in test:
        loaded = load_image(ROOT / "data/raw_samples" / sample.file, max_long_edge=1280)
        original = loaded.image
        carrier = (sample.label or "").split("_")[0]
        if carrier == "ppt":
            rectified, _quad, status = services._apply_rectify(original, "ppt")
            image = rectified if status == "ok" else original
            p2t, p2f = run_models(v2, image)
            p3t, p3f = run_models(v3, image)
            pcf = (p2f + p3f) / 2
            rows.append(
                {
                    "sample_id": sample.sample_id,
                    "true_label": sample.content_label,
                    "carrier": carrier,
                    "rectify_status": status,
                    "v2_pred": "formula" if p2f >= 0.5 else "text",
                    "v2_prob_formula": p2f,
                    "v3_pred": "formula" if p3f >= 0.5 else "text",
                    "v3_prob_formula": p3f,
                    "combined_pred": "formula" if pcf >= 0.5 else "text",
                    "combined_prob_formula": pcf,
                    "frozen_pred": frozen[sample.sample_id]["final_pred"],
                }
            )
        else:
            fp = frozen[sample.sample_id]["final_pred"]
            rows.append(
                {
                    "sample_id": sample.sample_id,
                    "true_label": sample.content_label,
                    "carrier": carrier,
                    "rectify_status": "not_run",
                    "v2_pred": fp,
                    "v2_prob_formula": None,
                    "v3_pred": fp,
                    "v3_prob_formula": None,
                    "combined_pred": fp,
                    "combined_prob_formula": None,
                    "frozen_pred": fp,
                }
            )

    y_ppt = [r["true_label"] for r in rows if r["carrier"] == "ppt"]
    result = {"n_test": len(rows), "n_ppt": len(y_ppt), "ppt": {}, "full": {}}
    for key in ("frozen_pred", "v2_pred", "v3_pred", "combined_pred"):
        p_ppt = [r[key] for r in rows if r["carrier"] == "ppt"]
        result["ppt"][key] = metrics(y_ppt, p_ppt)
        p_full = [r[key] for r in rows]
        y_full = [r["true_label"] for r in rows]
        result["full"][key] = metrics(y_full, p_full)
        result["ppt"][key]["ci95"] = bootstrap_ci([int(a == b) for a, b in zip(y_ppt, p_ppt)])
        result["full"][key]["ci95"] = bootstrap_ci([int(a == b) for a, b in zip(y_full, p_full)])

    base = [int(r["frozen_pred"] == r["true_label"]) for r in rows if r["carrier"] == "ppt"]
    for key in ("v2_pred", "v3_pred", "combined_pred"):
        other = [int(r[key] == r["true_label"]) for r in rows if r["carrier"] == "ppt"]
        result["ppt"][f"mcnemar_{key}_vs_frozen"] = mcnemar_exact(other, base)

    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with args.predictions.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    for key, label in (("frozen_pred", "冻结链路"), ("v2_pred", "v2"), ("v3_pred", "v3"), ("combined_pred", "v2+v3")):
        p = result["ppt"][key]
        f = result["full"][key]
        print(
            f"{label:8s} PPT acc={p['accuracy']:.4f} f1={p['macro_f1']:.4f} "
            f"| 全测试 acc={f['accuracy']:.4f} f1={f['macro_f1']:.4f} "
            f"conf={f['confusion_matrix']}"
        )
    print(f"保存 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
