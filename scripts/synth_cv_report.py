#!/usr/bin/env python3
"""汇总合成 PPT 训练试点的 5 折 × 3 种子结果。

读取 runs/<prefix>-f{fold}-s{seed}/metrics.json 与 predictions_val.csv，
输出逐折均值、总均值/标准差与 OOF 指标。只读取真实验证折，不读取测试集。
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="exp-cnn-ppt-synth-v2")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seeds", default="42,43,44")
    parser.add_argument("--out", type=Path, default=ROOT / "reports/synth_ppt_cv.json")
    args = parser.parse_args()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]

    per_fold: dict[int, list[dict]] = defaultdict(list)
    probs: dict[str, dict] = {}
    for fold in range(1, args.folds + 1):
        for seed in seeds:
            run = ROOT / "runs" / f"{args.prefix}-f{fold}-s{seed}"
            metrics_path = run / "metrics.json"
            if not metrics_path.is_file():
                continue
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            metrics = payload["metrics"]
            per_fold[fold].append(
                {
                    "seed": seed,
                    "accuracy": metrics["accuracy"],
                    "macro_f1": metrics["macro_f1"],
                    "confusion": metrics["confusion_matrix"],
                    "n_train": payload.get("n_train"),
                    "n_val": payload.get("n_val"),
                    "seconds": payload.get("train_seconds"),
                }
            )
            pred_path = run / "predictions_val.csv"
            if pred_path.is_file():
                for row in csv.DictReader(pred_path.open(encoding="utf-8")):
                    entry = probs.setdefault(
                        row["sample_id"],
                        {"true": row["true_label"], "p_formula": []},
                    )
                    entry["p_formula"].append(float(row["prob_formula"]))

    if not per_fold:
        raise SystemExit(f"没有找到 {args.prefix} 的运行结果")
    fold_summary = {}
    all_acc = []
    all_f1 = []
    for fold, rows in sorted(per_fold.items()):
        acc = [r["accuracy"] for r in rows]
        f1 = [r["macro_f1"] for r in rows]
        fold_summary[fold] = {
            "n_runs": len(rows),
            "accuracy_mean": statistics.mean(acc),
            "accuracy_std": statistics.pstdev(acc) if len(acc) > 1 else 0.0,
            "macro_f1_mean": statistics.mean(f1),
            "macro_f1_std": statistics.pstdev(f1) if len(f1) > 1 else 0.0,
            "runs": rows,
        }
        all_acc.extend(acc)
        all_f1.extend(f1)

    threshold = 0.5
    correct = 0
    tp = fp = fn = tn = 0
    oof_rows = []
    for sid, entry in sorted(probs.items()):
        p = statistics.mean(entry["p_formula"])
        pred = "formula" if p >= threshold else "text"
        true = entry["true"]
        ok = pred == true
        correct += int(ok)
        if pred == "formula" and true == "formula":
            tp += 1
        elif pred == "formula" and true == "text":
            fp += 1
        elif pred == "text" and true == "formula":
            fn += 1
        else:
            tn += 1
        oof_rows.append({"sample_id": sid, "true": true, "pred": pred, "p_formula": p})
    n = len(oof_rows)
    oof = {
        "n": n,
        "accuracy": correct / n if n else 0.0,
        "formula_precision": tp / (tp + fp) if tp + fp else 0.0,
        "formula_recall": tp / (tp + fn) if tp + fn else 0.0,
        "confusion": [[tn, fp], [fn, tp]],
    }

    result = {
        "prefix": args.prefix,
        "seeds": seeds,
        "folds": fold_summary,
        "overall": {
            "n_runs": len(all_acc),
            "accuracy_mean": statistics.mean(all_acc),
            "accuracy_std": statistics.pstdev(all_acc),
            "macro_f1_mean": statistics.mean(all_f1),
            "macro_f1_std": statistics.pstdev(all_f1),
        },
        "oof": oof,
        "oof_rows": oof_rows,
    }
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{args.folds} 折 × {len(seeds)} 种子，共 {len(all_acc)} 次")
    for fold, rows in sorted(fold_summary.items()):
        print(f"fold{fold}: {rows['accuracy_mean']:.4f} ± {rows['accuracy_std']:.4f} (n={rows['n_runs']})")
    print(f"总体: {result['overall']['accuracy_mean']:.4f} ± {result['overall']['accuracy_std']:.4f}")
    print(f"OOF: {oof['accuracy']:.4f}, formula P/R={oof['formula_precision']:.3f}/{oof['formula_recall']:.3f}")
    print(f"写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
