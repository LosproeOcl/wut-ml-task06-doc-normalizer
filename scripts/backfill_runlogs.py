"""为早期实验回填 run.json。

历史实验只有 metrics.json，没有 RunLogger 生成的参数/环境日志。
本脚本生成带 `backfilled: true` 的 run.json，缺失字段留空，不臆造环境信息。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
sys.path.insert(0, str(ROOT / "scripts"))

from index_runs import CLASSIC_FALLBACK, CNN_FALLBACK, family_of  # noqa: E402


def mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def main() -> int:
    count = 0
    for run_dir in sorted(RUNS.iterdir()):
        if not run_dir.is_dir():
            continue
        run_path = run_dir / "run.json"
        metrics_path = run_dir / "metrics.json"
        if run_path.is_file() or not metrics_path.is_file():
            continue
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        family = family_of(run_dir.name)
        args = {}
        if family == "cnn":
            args = {
                **CNN_FALLBACK.get(run_dir.name, {}),
                "input_size": metrics.get("input_size"),
                "augment": metrics.get("augment"),
                "corner_policy": metrics.get("corner_policy"),
            }
        elif family == "classic":
            args = CLASSIC_FALLBACK.get(run_dir.name, {})
        artifacts = [
            {"path": path.name, "bytes": path.stat().st_size}
            for path in sorted(run_dir.iterdir())
            if path.is_file()
        ]
        payload = {
            "schema_version": 1,
            "exp_id": run_dir.name,
            "script": (
                "scripts/train_cnn.py"
                if family == "cnn"
                else "scripts/train_classic.py"
                if family == "classic"
                else "unknown"
            ),
            "status": "completed",
            "backfilled": True,
            "backfill_note": "由 metrics.json 与报告回填；缺失参数留空，不臆造环境与逐轮日志",
            "started_at": mtime_iso(metrics_path),
            "finished_at": mtime_iso(metrics_path),
            "duration_seconds": None,
            "argv": [],
            "args": {key: value for key, value in args.items() if value is not None},
            "config": {},
            "environment": {},
            "git": {},
            "files": {},
            "metrics": metrics.get("metrics") or metrics.get("models") or {},
            "artifacts": artifacts,
            "notes": "历史实验回填；原始逐轮日志不可恢复",
        }
        run_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        count += 1
    print(f"回填 {count} 个 run.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
