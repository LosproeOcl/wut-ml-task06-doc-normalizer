"""遗传算法做特征组选择，再在验证集上评估。

传统特征共 1836 维，按来源分为 30 组：
- 版面密度 64 维 -> 1 组；
- 边缘方向 8 维 -> 1 组；
- HOG 1764 维 -> 28 组，每组 63 维。

适应度为训练集 5 折交叉验证准确率，验证集只在最后评估一次。

用法：
    PYTHONPATH=src python scripts/ga_feature_selection.py
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
import yaml
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.annotations import ManualLabelStore  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from docnorm.utils.runlog import RunLogger  # noqa: E402

LABELS = ["text", "formula"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=ROOT / "runs/fusion-exp-01/features.npz")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/ga-feature-01")
    parser.add_argument("--population", type=int, default=14)
    parser.add_argument("--generations", type=int, default=12)
    parser.add_argument("--mutation", type=float, default=0.15)
    parser.add_argument("--crossover", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def build_groups(feature_dim: int) -> list[tuple[str, list[int]]]:
    if feature_dim != 1836:
        raise SystemExit(f"预期 1836 维传统特征，实际 {feature_dim}")
    groups = [("density", list(range(0, 64))), ("edge", list(range(64, 72)))]
    hog = list(range(72, 1836))
    for index in range(28):
        groups.append((f"hog_{index:02d}", hog[index * 63:(index + 1) * 63]))
    return groups


def mask_indices(mask: list[int], groups) -> list[int]:
    indices: list[int] = []
    for selected, (_, group) in zip(mask, groups):
        if selected:
            indices.extend(group)
    return indices


def fitness(mask, groups, x_train, y_train, cache):
    key = tuple(mask)
    if key in cache:
        return cache[key]
    indices = mask_indices(mask, groups)
    if not indices:
        cache[key] = 0.0
        return 0.0
    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "model",
                SVC(
                    C=1.0,
                    gamma=0.001,
                    kernel="rbf",
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )
    scores = cross_val_score(
        pipeline,
        x_train[:, indices],
        y_train,
        cv=StratifiedKFold(5, shuffle=True, random_state=42),
        scoring="accuracy",
        n_jobs=1,
    )
    value = float(np.mean(scores))
    cache[key] = value
    return value


def tournament(scored, rng):
    picks = rng.sample(scored, 3)
    return max(picks, key=lambda item: item[0])[1]


def mutate(mask: list[int], rate: float, rng) -> list[int]:
    result = list(mask)
    for index in range(len(result)):
        if rng.random() < rate:
            result[index] = 1 - result[index]
    if not any(result):
        result[rng.randrange(len(result))] = 1
    return result


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    np.random.seed(args.seed)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data = np.load(args.features)
    x = data["classic"].astype(np.float32)
    y = data["labels"]
    splits = data["splits"]
    train_mask = splits == "train"
    val_mask = splits == "val"
    x_train, y_train = x[train_mask], y[train_mask]
    x_val, y_val = x[val_mask], y[val_mask]
    groups = build_groups(x.shape[1])
    samples = load_manifest(
        ROOT / config["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(ROOT / config["data"]["split"])
    assignment = assign_samples(split, samples)
    label_overrides = ManualLabelStore(ROOT / "data/annotations/manual_labels.csv").load()
    sample_ids = []
    for sample in samples:
        name = assignment.get(sample.sample_id)
        if name not in {"train", "val"}:
            continue
        label = label_overrides.get(sample.sample_id, sample.content_label) if name == "train" else sample.content_label
        if label is None:
            continue
        sample_ids.append(sample.sample_id)
    if len(sample_ids) != len(y):
        raise SystemExit(f"样本顺序不一致: ids={len(sample_ids)} labels={len(y)}")

    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(
        out_dir.name,
        out_dir,
        "scripts/ga_feature_selection.py",
        args,
        config,
        root=ROOT,
        notes="遗传算法选择传统特征组；适应度为训练集 5 折 CV",
    )
    logger.log(f"实验 {out_dir.name} 开始，特征组 {len(groups)}")

    population = []
    for _ in range(args.population - 2):
        population.append([1 if rng.random() < 0.5 else 0 for _ in groups])
    population.append([1] * len(groups))
    population.append([1 if name in {"density", "edge", "hog_00", "hog_01"} else 0 for name, _ in groups])

    cache: dict[tuple[int, ...], float] = {}
    history = []
    best_overall = None
    for generation in range(1, args.generations + 1):
        scored = [(fitness(mask, groups, x_train, y_train, cache), mask) for mask in population]
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_mask = scored[0]
        if best_overall is None or best_score > best_overall[0]:
            best_overall = (best_score, list(best_mask))
        selected = sum(best_mask)
        history.append(
            {
                "generation": generation,
                "best_cv": round(best_score, 4),
                "mean_cv": round(float(np.mean([item[0] for item in scored])), 4),
                "selected_groups": selected,
                "best_mask": list(best_mask),
            }
        )
        logger.log(
            f"第 {generation} 代 best_cv={best_score:.4f} "
            f"mean_cv={history[-1]['mean_cv']:.4f} groups={selected}"
        )

        next_population = [list(mask) for _, mask in scored[:2]]
        while len(next_population) < args.population:
            parent_a = tournament(scored, rng)
            parent_b = tournament(scored, rng)
            if rng.random() < args.crossover:
                point = rng.randrange(1, len(groups))
                child = parent_a[:point] + parent_b[point:]
            else:
                child = list(parent_a)
            next_population.append(mutate(child, args.mutation, rng))
        population = next_population

    with (out_dir / "ga_history.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["generation", "best_cv", "mean_cv", "selected_groups", "best_mask"])
        for row in history:
            writer.writerow(
                [
                    row["generation"],
                    row["best_cv"],
                    row["mean_cv"],
                    row["selected_groups"],
                    "".join(str(bit) for bit in row["best_mask"]),
                ]
            )

    best_score, best_mask = best_overall
    indices = mask_indices(best_mask, groups)
    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "model",
                SVC(
                    C=1.0,
                    gamma=0.001,
                    kernel="rbf",
                    probability=True,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )
    pipeline.fit(x_train[:, indices], y_train)
    probabilities = pipeline.predict_proba(x_val[:, indices])
    classes = list(pipeline.classes_)
    predictions = [classes[index] for index in probabilities.argmax(axis=1)]
    metrics = {
        "accuracy": float(accuracy_score(y_val, predictions)),
        "macro_f1": float(f1_score(y_val, predictions, average="macro")),
        "confusion_matrix": confusion_matrix(
            y_val, predictions, labels=LABELS
        ).tolist(),
    }
    selected_names = [name for selected, (name, _) in zip(best_mask, groups) if selected]
    result = {
        "exp_id": out_dir.name,
        "feature_dim": int(x.shape[1]),
        "selected_feature_dim": len(indices),
        "selected_groups": selected_names,
        "best_cv_accuracy": round(best_score, 4),
        "generations": len(history),
        "population": args.population,
        "metrics": metrics,
        "history": history,
    }
    (out_dir / "selected_groups.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "predictions_val.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "true_label", "pred_label"])
        val_ids = np.asarray(sample_ids)[val_mask]
        for sample_id, true_label, pred_label in zip(val_ids, y_val, predictions):
            writer.writerow([sample_id, true_label, pred_label])
    print(
        f"GA best_cv={best_score:.4f} selected={len(indices)} "
        f"val_acc={metrics['accuracy']:.4f} val_f1={metrics['macro_f1']:.4f}"
    )
    logger.finish(metrics=metrics, extra=result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
