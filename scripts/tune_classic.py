"""Traditional baseline tuning on the frozen split.

The script builds the same features as ``scripts/train_classic.py``, runs a
grouped cross-validation search on the **training split only**, selects the best
SVM/RF configuration, evaluates it once on the validation split, and writes the
tuning table, model, predictions, and feature-importance summary.

The test split is never loaded. This follows the evaluation plan: test metrics
are reserved for the final report and must not be used for tuning.

Example:
    PYTHONPATH=src python scripts/tune_classic.py --model both
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from docnorm.classify.classic import ClassicClassifier  # noqa: E402
from docnorm.data.annotations import ManualCornerStore, ManualLabelStore  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, check_manifest_hash, load_split  # noqa: E402
from docnorm.features.classic import (  # noqa: E402
    FEATURE_DIM,
    GRID_SIZE,
    ORIENTATION_BINS,
)
from docnorm.utils.runlog import RunLogger  # noqa: E402
from scripts.train_classic import LABELS, build_features, evaluate  # noqa: E402

LAYOUT_DIM = GRID_SIZE * GRID_SIZE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.yaml")
    parser.add_argument(
        "--tuning-config",
        type=Path,
        default=ROOT / "configs/classic_tuning.yaml",
    )
    parser.add_argument("--split", type=Path, default=None)
    parser.add_argument("--exp-id", default=None)
    parser.add_argument("--model", choices=("svm", "rf", "both"), default="both")
    parser.add_argument("--no-rectify", action="store_true")
    parser.add_argument("--no-enhance", action="store_true")
    parser.add_argument(
        "--corners-policy",
        choices=("always", "fallback", "none"),
        default="fallback",
    )
    parser.add_argument("--cv-folds", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def generate_candidates(space: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Expand a one-level search space into a deterministic candidate list."""
    if not space:
        return [{}]
    keys = list(space)
    values = [list(space[key]) for key in keys]
    return [
        dict(zip(keys, combination, strict=True))
        for combination in itertools.product(*values)
    ]


def select_best(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Select by mean macro-F1, breaking ties by lower fold standard deviation."""
    if not results:
        raise ValueError("no candidate results")
    return max(results, key=lambda row: (row["mean_macro_f1"], -row["std_macro_f1"]))


def group_importance(
    importances: np.ndarray,
    *,
    layout_dim: int = LAYOUT_DIM,
    orientation_dim: int = ORIENTATION_BINS,
    top_k: int = 20,
) -> dict[str, Any]:
    """Aggregate feature importances by feature group and keep the top features."""
    values = np.asarray(importances, dtype=np.float64)
    if values.shape != (FEATURE_DIM,):
        raise ValueError(f"expected {FEATURE_DIM} importances, got {values.shape}")
    top = np.argsort(values)[::-1][:top_k]
    return {
        "layout": float(values[:layout_dim].sum()),
        "orientation": float(values[layout_dim : layout_dim + orientation_dim].sum()),
        "hog": float(values[layout_dim + orientation_dim :].sum()),
        "top_features": [
            {"index": int(index), "importance": float(values[index])} for index in top
        ],
    }


def cross_validate_candidate(
    model_name: str,
    params: dict[str, Any],
    features: np.ndarray,
    labels: np.ndarray,
    groups: list[str],
    cv_folds: int,
    seed: int,
) -> dict[str, Any] | None:
    """Evaluate one candidate with grouped cross-validation on the training split."""
    group_values = np.asarray(groups)
    unique_groups = len(set(group_values.tolist()))
    folds = max(2, min(cv_folds, unique_groups))
    if folds < 2:
        return None

    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    scores: list[float] = []
    durations: list[float] = []
    skipped = 0
    for train_index, val_index in splitter.split(features, labels, group_values):
        if np.unique(labels[train_index]).size < 2 or np.unique(labels[val_index]).size < 2:
            skipped += 1
            continue
        candidate_params = dict(params)
        if model_name == "rf":
            candidate_params.setdefault("n_jobs", 1)
        started = time.perf_counter()
        model = ClassicClassifier(
            model=model_name,
            random_state=seed,
            **candidate_params,
        ).fit(features[train_index], labels[train_index])
        predicted = model.predict(features[val_index])
        scores.append(
            float(
                f1_score(
                    labels[val_index],
                    predicted,
                    labels=LABELS,
                    average="macro",
                    zero_division=0,
                )
            )
        )
        durations.append(time.perf_counter() - started)

    if not scores:
        return None
    return {
        "mean_macro_f1": float(np.mean(scores)),
        "std_macro_f1": float(np.std(scores)),
        "n_folds": len(scores),
        "skipped_folds": skipped,
        "seconds": round(float(sum(durations)), 3),
        "scores": [round(score, 6) for score in scores],
    }


def search_model(
    model_name: str,
    space: dict[str, list[Any]],
    x_train: np.ndarray,
    y_train: np.ndarray,
    groups: list[str],
    cv_folds: int,
    seed: int,
) -> tuple[ClassicClassifier, dict[str, Any], list[dict[str, Any]]]:
    candidates = generate_candidates(space)
    results: list[dict[str, Any]] = []
    for index, params in enumerate(candidates, start=1):
        metrics = cross_validate_candidate(
            model_name, params, x_train, y_train, groups, cv_folds, seed
        )
        if metrics is None:
            continue
        results.append({"params": params, **metrics})
        print(
            f"[{model_name}] {index}/{len(candidates)} "
            f"cv={metrics['mean_macro_f1']:.4f}±{metrics['std_macro_f1']:.4f} "
            f"{params}"
        )
    if not results:
        raise SystemExit(f"{model_name}: no valid tuning candidate")

    best = select_best(results)
    results.sort(
        key=lambda row: (row["mean_macro_f1"], -row["std_macro_f1"]),
        reverse=True,
    )
    model = ClassicClassifier(
        model=model_name,
        random_state=seed,
        **best["params"],
    ).fit(x_train, y_train)
    return model, best, results


def write_tuning_table(path: Path, results: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["rank", "mean_macro_f1", "std_macro_f1", "n_folds", "seconds", "params"]
        )
        for rank, row in enumerate(results, start=1):
            writer.writerow(
                [
                    rank,
                    round(row["mean_macro_f1"], 6),
                    round(row["std_macro_f1"], 6),
                    row["n_folds"],
                    row["seconds"],
                    json.dumps(row["params"], ensure_ascii=False, sort_keys=True),
                ]
            )


def write_predictions(
    path: Path,
    sample_ids: list[str],
    y_true: np.ndarray,
    model: ClassicClassifier,
    metrics: dict[str, Any],
) -> None:
    classes = list(model.classes_)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "true_label", "pred_label", "prob_text", "prob_formula"])
        for sample_id, true_label, predicted, probability in zip(
            sample_ids,
            y_true,
            metrics["predictions"],
            metrics["probabilities"],
            strict=True,
        ):
            writer.writerow(
                [
                    sample_id,
                    true_label,
                    predicted,
                    float(probability[classes.index("text")]),
                    float(probability[classes.index("formula")]),
                ]
            )


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(_resolve(args.config).read_text(encoding="utf-8"))
    tuning = yaml.safe_load(_resolve(args.tuning_config).read_text(encoding="utf-8"))
    split_path = _resolve(args.split or config["data"]["split"])
    seed = int(args.seed if args.seed is not None else config["runtime"]["seed"])
    cv_folds = int(args.cv_folds or tuning.get("cv_folds", 3))

    samples = load_manifest(
        ROOT / config["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(split_path)
    check_manifest_hash(split, ROOT / config["data"]["manifest"])
    assignment = assign_samples(split, samples)

    overrides = {
        sample_id: label
        for sample_id, label in ManualLabelStore(
            ROOT / "data/annotations/manual_labels.csv"
        ).load().items()
        if assignment.get(sample_id) == "train"
    }
    corners = (
        {
            sample_id: points
            for sample_id, points in ManualCornerStore(
                ROOT / "data/annotations/manual_corners.csv"
            ).load().items()
            if assignment.get(sample_id) == "train"
        }
        if args.corners_policy != "none"
        else {}
    )

    exp_id = args.exp_id or f"exp-{datetime.now():%Y%m%d-%H%M}-tune"
    out_dir = ROOT / "runs" / exp_id
    logger = RunLogger(
        exp_id,
        out_dir,
        "scripts/tune_classic.py",
        args,
        config,
        root=ROOT,
        notes="传统基线调优；分组交叉验证仅使用训练集，验证集只评估一次",
    )
    logger.log(f"调优实验 {exp_id} 开始")

    features, labels, ids, failures = build_features(
        samples,
        config,
        use_rectify=not args.no_rectify,
        use_enhance=not args.no_enhance,
        label_overrides=overrides,
        corner_overrides=corners,
        corner_policy=args.corners_policy,
    )
    id_to_group = {sample.sample_id: sample.doc_page_id for sample in samples}
    train_index = [i for i, sample_id in enumerate(ids) if assignment.get(sample_id) == "train"]
    val_index = [i for i, sample_id in enumerate(ids) if assignment.get(sample_id) == "val"]
    if not train_index or not val_index:
        raise SystemExit("训练集或验证集为空，停止")

    x_train = features[train_index]
    y_train = labels[train_index]
    x_val = features[val_index]
    y_val = labels[val_index]
    val_ids = [ids[i] for i in val_index]
    groups = [id_to_group[ids[i]] for i in train_index]

    model_names = ["svm", "rf"] if args.model == "both" else [args.model]
    summary: dict[str, Any] = {
        "exp_id": exp_id,
        "split": split_path.name,
        "n_train": len(train_index),
        "n_val": len(val_index),
        "detection_failed": failures,
        "seed": seed,
        "cv_folds": cv_folds,
        "models": {},
    }

    for model_name in model_names:
        space = tuning.get(model_name) or {}
        model, best, results = search_model(
            model_name, space, x_train, y_train, groups, cv_folds, seed
        )
        val_metrics = evaluate(model, x_val, y_val)
        val_summary = {
            key: value
            for key, value in val_metrics.items()
            if key not in {"predictions", "probabilities"}
        }

        model.save(out_dir / f"best_{model_name}.joblib")
        write_tuning_table(out_dir / f"tuning_{model_name}.csv", results)
        write_predictions(
            out_dir / f"predictions_val_{model_name}.csv",
            val_ids,
            y_val,
            model,
            val_metrics,
        )

        model_summary = {
            "best_params": best["params"],
            "cv": {key: value for key, value in best.items() if key != "params"},
            "val": val_summary,
        }
        if model_name == "rf":
            estimator = model._pipeline.named_steps["model"]
            importances = getattr(estimator, "feature_importances_", None)
            if importances is not None:
                importance = group_importance(np.asarray(importances))
                (out_dir / "feature_importance.json").write_text(
                    json.dumps(importance, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                model_summary["feature_importance"] = {
                    key: importance[key] for key in ("layout", "orientation", "hog")
                }
        summary["models"][model_name] = model_summary
        print(
            f"[{model_name}] best cv={best['mean_macro_f1']:.4f} "
            f"val_accuracy={val_metrics['accuracy']:.4f} "
            f"val_macro_f1={val_metrics['macro_f1']:.4f}"
        )

    (out_dir / "tuning.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "config.snapshot.yaml").write_text(
        yaml.safe_dump(
            {"default": config, "tuning": tuning},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    logger.finish(
        metrics=summary["models"],
        extra={"n_train": summary["n_train"], "n_val": summary["n_val"]},
    )
    print(f"调优结果写入 {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
