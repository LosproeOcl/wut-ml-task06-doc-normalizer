"""汇总 5 折 × 3 种子 OOF 预测，做温度校准、阈值选择与 CNN/SVM 集成评估。

只使用训练集折内 OOF 预测；原验证集仅做最终检查，测试集不读取。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import load_split, assign_samples  # noqa: E402


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def read_predictions(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            rows[row["sample_id"]] = {
                "true": row["true_label"],
                "p_formula": float(row["prob_formula"]),
            }
    return rows


def metrics(probs, truths, threshold=0.5):
    preds = ["formula" if p >= threshold else "text" for p in probs]
    correct = [int(p == t) for p, t in zip(preds, truths)]
    tp = sum(1 for p, t in zip(preds, truths) if p == "formula" and t == "formula")
    fp = sum(1 for p, t in zip(preds, truths) if p == "formula" and t == "text")
    fn = sum(1 for p, t in zip(preds, truths) if p == "text" and t == "formula")
    tn = sum(1 for p, t in zip(preds, truths) if p == "text" and t == "text")
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "n": len(truths),
        "accuracy": float(np.mean(correct)),
        "formula_precision": precision,
        "formula_recall": recall,
        "confusion": [[tn, fp], [fn, tp]],
    }


def fit_temperature(probs, truths):
    probs = np.clip(np.asarray(probs, dtype=np.float64), 1e-6, 1 - 1e-6)
    logits = np.log(probs / (1 - probs))
    y = np.asarray([1 if t == "formula" else 0 for t in truths])

    def nll(temperature):
        p = np.clip(sigmoid(logits / temperature), 1e-6, 1 - 1e-6)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

    result = minimize_scalar(nll, bounds=(0.1, 10.0), method="bounded")
    return float(result.x), float(result.fun)


def best_threshold(probs, truths):
    best = (0.5, -1.0)
    for threshold in np.linspace(0.25, 0.75, 101):
        value = metrics(probs, truths, threshold)["accuracy"]
        if value > best[1]:
            best = (float(threshold), float(value))
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "reports/cv_oof.json")
    parser.add_argument(
        "--predictions", type=Path, default=ROOT / "reports/cv_oof_predictions.csv"
    )
    args = parser.parse_args()

    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(ROOT / "data/splits/split_v4.json")
    assignment = assign_samples(split, samples)
    by_id = {s.sample_id: s for s in samples}

    oof = {}
    fold_of = {}
    for fold in range(1, 6):
        fold_path = ROOT / f"data/splits/cv/fold_{fold}.json"
        fold_doc = json.loads(fold_path.read_text(encoding="utf-8"))
        val_groups = set(fold_doc["groups"]["val"])
        for sample in samples:
            if sample.doc_page_id in val_groups and assignment.get(sample.sample_id) == "train":
                fold_of[sample.sample_id] = fold
        ppt = read_predictions(ROOT / f"runs/cv-ppt-f{fold}-s42/predictions_val.csv")
        paper = read_predictions(ROOT / f"runs/cv-paper-f{fold}-s42/predictions_val.csv")
        for pid, row in ppt.items():
            if pid not in oof:
                oof[pid] = {"carrier": "ppt", "true": row["true"], "fold": fold}
            oof[pid]["ppt_probs"] = [row["p_formula"]]
        for pid, row in paper.items():
            if pid not in oof:
                oof[pid] = {"carrier": "paper", "true": row["true"], "fold": fold}
            oof[pid]["paper_probs"] = [row["p_formula"]]
        for seed in (43, 44):
            p2 = read_predictions(
                ROOT / f"runs/cv-ppt-f{fold}-s{seed}/predictions_val.csv"
            )
            for pid, row in p2.items():
                if pid in oof and "ppt_probs" in oof[pid]:
                    oof[pid]["ppt_probs"].append(row["p_formula"])
            p2 = read_predictions(
                ROOT / f"runs/cv-paper-f{fold}-s{seed}/predictions_val.csv"
            )
            for pid, row in p2.items():
                if pid in oof and "paper_probs" in oof[pid]:
                    oof[pid]["paper_probs"].append(row["p_formula"])

    # 合并每折 SVM OOF
    svm = {}
    for fold in range(1, 6):
        path = ROOT / f"runs/cv-svm-f{fold}/predictions_val_svm.csv"
        if path.is_file():
            svm.update(read_predictions(path))
    # 只保留训练集 OOF，且两个分支都应有预测
    rows = []
    for pid, item in oof.items():
        if assignment.get(pid) != "train":
            continue
        probs = item.get("ppt_probs") or item.get("paper_probs")
        if not probs:
            continue
        item["cnn_prob"] = float(np.mean(probs))
        item["svm_prob"] = svm.get(pid, {}).get("p_formula")
        rows.append({"sample_id": pid, **item})

    results = {}
    for carrier in ("ppt", "paper"):
        subset = [r for r in rows if r["carrier"] == carrier]
        if not subset:
            continue
        probs = [r["cnn_prob"] for r in subset]
        truths = [r["true"] for r in subset]
        base = metrics(probs, truths)
        temperature, nll = fit_temperature(probs, truths)
        calibrated = [float(sigmoid(np.log(max(1e-6, min(1 - 1e-6, p)) / (1 - max(1e-6, min(1 - 1e-6, p)))) / temperature)) for p in probs]
        threshold, threshold_acc = best_threshold(calibrated, truths)
        results[carrier] = {
            "n": len(subset),
            "raw": base,
            "temperature": temperature,
            "nll_after": nll,
            "calibrated": metrics(calibrated, truths, 0.5),
            "best_threshold": threshold,
            "best_threshold_accuracy": threshold_acc,
            "seed_std_accuracy": float(
                np.std(
                    [
                        metrics(
                            [r["ppt_probs"][i] if carrier == "ppt" else r["paper_probs"][i] for r in subset],
                            truths,
                        )["accuracy"]
                        for i in range(3)
                    ]
                )
            ),
        }
        # CNN + SVM 概率融合，权重只在 OOF 上选
        paired = [(r["cnn_prob"], r["svm_prob"]) for r in subset if r["svm_prob"] is not None]
        if len(paired) == len(subset):
            best = (0.0, -1.0)
            for weight in np.linspace(0.0, 1.0, 21):
                blended = [weight * c + (1 - weight) * s for c, s in paired]
                acc = metrics(blended, truths, threshold)["accuracy"]
                if acc > best[1]:
                    best = (float(weight), float(acc))
            results[carrier]["cnn_svm_weight"] = best[0]
            results[carrier]["cnn_svm_accuracy"] = best[1]

    # 原验证集最终检查：用 OOF 选择的温度/阈值检查，不重新选参
    val_rows = []
    val_path = ROOT / "reports/eval_paper/routed_val.csv"
    if val_path.is_file():
        with val_path.open(encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                carrier = row["carrier"]
                if carrier not in results or not row["prob_formula"]:
                    continue
                p = float(row["prob_formula"])
                t = results[carrier]["temperature"]
                p = float(sigmoid(np.log(max(1e-6, min(1 - 1e-6, p)) / (1 - max(1e-6, min(1 - 1e-6, p)))) / t))
                val_rows.append(
                    {
                        "sample_id": row["sample_id"],
                        "true": row["label"],
                        "carrier": carrier,
                        "p": p,
                        "pred": "formula" if p >= results[carrier]["best_threshold"] else "text",
                    }
                )
    if val_rows:
        results["validation_check"] = {
            "n": len(val_rows),
            "accuracy": float(np.mean([r["pred"] == r["true"] for r in val_rows])),
        }

    payload = {"rows": rows, "results": results, "oof_samples": len(rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with args.predictions.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["sample_id", "carrier", "true", "fold", "cnn_prob", "svm_prob"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})
    print(json.dumps(payload["results"], ensure_ascii=False, indent=2))
    print(f"保存 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
