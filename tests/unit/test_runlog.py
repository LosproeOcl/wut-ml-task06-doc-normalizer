"""运行日志的契约测试。"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from pathlib import Path

from docnorm.utils.runlog import RunLogger

ROOT = Path(__file__).resolve().parents[2]


def test_runlogger_writes_metadata_epochs_and_restores_stdout(tmp_path):
    out_dir = tmp_path / "exp-test"
    old_stdout = sys.stdout
    args = SimpleNamespace(epochs=2, input_size=224, note="test")
    logger = RunLogger(
        "exp-test",
        out_dir,
        "scripts/test.py",
        args,
        {"data": {"split": "data/splits/split_v3.json"}},
        root=ROOT,
        notes="单元测试",
    )
    logger.log("开始")
    logger.log_epoch(1, train_loss=0.5, val_loss=0.6, val_accuracy=0.7)
    logger.finish(metrics={"accuracy": 0.7})

    payload = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["args"]["epochs"] == 2
    assert payload["args"]["note"] == "test"
    assert payload["metrics"]["accuracy"] == 0.7
    assert (out_dir / "train.log").is_file()
    assert (out_dir / "epochs.csv").is_file()
    assert "1" in (out_dir / "epochs.csv").read_text(encoding="utf-8")
    assert any(item["path"] == "run.json" for item in payload["artifacts"])
    assert sys.stdout is old_stdout
