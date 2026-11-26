"""汇总 runs/ 下的实验日志为一张索引表。

优先读取 `run.json`；历史实验没有 run.json 时从 `metrics.json` 回填，
缺失字段留空，并标记 status 为 `completed (metrics-only)`。

用法：
    PYTHONPATH=src python scripts/index_runs.py
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
OUT = ROOT / "reports/run_index.csv"

CNN_FALLBACK = {
    "exp-cnn-01": {"backbone": "mobilenet_v3_small", "input_size": 224, "augment": "default", "corner_policy": "unknown", "epochs": 12},
    "exp-cnn-02": {"backbone": "mobilenet_v3_small", "input_size": 224, "augment": "default", "corner_policy": "unknown", "epochs": 15},
    "exp-cnn-03": {"backbone": "mobilenet_v3_small", "input_size": 224, "augment": "default", "corner_policy": "always", "epochs": 9},
    "exp-cnn-04": {"backbone": "mobilenet_v3_small", "input_size": 224, "augment": "default", "corner_policy": "none", "epochs": 15},
    "exp-cnn-05": {"backbone": "mobilenet_v3_small", "input_size": 224, "augment": "default", "corner_policy": "fallback", "epochs": 13},
}
CLASSIC_FALLBACK = {
    "exp-20261126-03": {"corner_policy": "always (25 条)"},
    "exp-20261126-04": {"corner_policy": "none"},
    "exp-20261126-05": {"corner_policy": "always (236 条)"},
    "exp-20261126-06": {"corner_policy": "none"},
    "exp-20261126-07": {"corner_policy": "fallback"},
    "exp-20261126-08": {"corner_policy": "none"},
}

FIELDS = [
    "exp_id",
    "family",
    "script",
    "status",
    "started_at",
    "finished_at",
    "duration_seconds",
    "split",
    "n_train",
    "n_val",
    "model",
    "accuracy",
    "macro_f1",
    "backbone",
    "input_size",
    "augment",
    "corner_policy",
    "seed",
    "epochs",
    "run_dir",
    "log_status",
    "notes",
]


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def mtime_iso(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def family_of(exp_id: str) -> str:
    if exp_id.startswith("pretrain"):
        return "pretrain"
    if exp_id.startswith("ensemble"):
        return "ensemble"
    if exp_id.startswith("cv-lstm"):
        return "lstm_cv"
    if exp_id.startswith("exp-cnn-lstm") or exp_id.startswith("exp-lstm"):
        return "lstm"
    if exp_id.startswith("exp-cnn"):
        return "cnn"
    if exp_id.startswith("fusion"):
        return "fusion"
    if exp_id.startswith("ga-"):
        return "ga"
    return "classic"


def rows_for_run(run_dir: Path) -> list[dict]:
    exp_id = run_dir.name
    family = family_of(exp_id)
    run = read_json(run_dir / "run.json")
    metrics = read_json(run_dir / "metrics.json")
    args = run.get("args", {}) or {}
    extra = run.get("extra", {}) or {}
    base = {
        "exp_id": exp_id,
        "family": family,
        "script": run.get("script", ""),
        "status": run.get("status", "completed (metrics-only)" if metrics else "unknown"),
        "started_at": run.get("started_at", mtime_iso(run_dir / "metrics.json")),
        "finished_at": run.get("finished_at", mtime_iso(run_dir / "metrics.json")),
        "duration_seconds": run.get("duration_seconds", ""),
        "split": metrics.get("split", ""),
        "n_train": metrics.get("n_train", extra.get("n_train", "")),
        "n_val": metrics.get("n_val", extra.get("n_val", "")),
        "backbone": metrics.get("backbone", args.get("backbone", "")),
        "input_size": metrics.get("input_size", args.get("input_size", "")),
        "augment": metrics.get("augment", args.get("augment", "")),
        "corner_policy": metrics.get("corner_policy", args.get("corners_policy", "")),
        "seed": metrics.get("seed", args.get("seed", "")),
        "epochs": metrics.get("epochs", ""),
        "run_dir": str(run_dir.relative_to(ROOT)),
        "log_status": (
            "run.json (backfilled)"
            if run.get("backfilled")
            else "run.json+train.log"
            if run and (run_dir / "train.log").is_file()
            else "run.json"
            if run
            else "metrics only"
        ),
        "notes": run.get("notes", ""),
    }
    if not run:
        base["notes"] = "历史实验，参数按 metrics 或报告回填；时间为 metrics.json 修改时间"
        if family == "cnn":
            for key, value in CNN_FALLBACK.get(exp_id, {}).items():
                if not base.get(key):
                    base[key] = value
        if family == "classic":
            for key, value in CLASSIC_FALLBACK.get(exp_id, {}).items():
                if not base.get(key):
                    base[key] = value
    rows = []
    if family == "classic":
        for model in ("svm", "rf"):
            model_metrics = (metrics.get("models") or {}).get(model)
            if not model_metrics:
                continue
            row = dict(base)
            row.update(
                {
                    "model": model,
                    "accuracy": model_metrics.get("accuracy", ""),
                    "macro_f1": model_metrics.get("macro_f1", ""),
                }
            )
            rows.append(row)
        if not rows:
            row = dict(base)
            row.update({"model": "", "accuracy": "", "macro_f1": ""})
            rows.append(row)
        return rows
    if family == "fusion":
        models = metrics.get("models") or {}
        best_name, best = None, None
        for name, value in models.items():
            if value.get("accuracy", -1) > (best or {}).get("accuracy", -1):
                best_name, best = name, value
        if best:
            row = dict(base)
            row.update(
                {
                    "model": best_name,
                    "accuracy": best.get("accuracy", ""),
                    "macro_f1": best.get("macro_f1", ""),
                }
            )
            return [row]
        return []
    if family == "pretrain":
        row = dict(base)
        row.update(
            {
                "model": "pretrain",
                "accuracy": metrics.get("external_val_accuracy", ""),
                "macro_f1": "",
                "backbone": metrics.get("backbone", "mobilenet_v3_small"),
            }
        )
        return [row]
    if family == "ensemble":
        summary = metrics.get("summary") or {}
        best = summary.get("best_weight") or summary.get("best_route") or {}
        row = dict(base)
        row.update(
            {
                "model": "ensemble",
                "accuracy": best.get("accuracy", ""),
                "macro_f1": best.get("macro_f1", ""),
            }
        )
        return [row]
    top_metrics = metrics.get("metrics") or {}
    row = dict(base)
    row.update(
        {
            "model": family,
            "accuracy": top_metrics.get("accuracy", ""),
            "macro_f1": top_metrics.get("macro_f1", ""),
        }
    )
    return [row]


def main() -> int:
    rows = []
    for run_dir in sorted(RUNS.iterdir()):
        if not run_dir.is_dir():
            continue
        rows.extend(rows_for_run(run_dir))
    rows.sort(key=lambda row: (row.get("started_at", ""), row["exp_id"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"写入 {OUT}，共 {len(rows)} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
