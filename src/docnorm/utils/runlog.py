"""训练运行日志：参数、环境、逐轮指标与产物。

每个实验在 `runs/<exp_id>/` 下生成：

- `run.json`：完整参数、环境、数据文件哈希、指标与产物清单；
- `train.log`：训练过程的标准输出与错误输出；
- `epochs.csv`：逐轮训练/验证指标（CNN）。

用法：
    logger = RunLogger(exp_id, out_dir, "scripts/train_cnn.py", args, config, root=ROOT)
    logger.log_epoch(epoch=1, train_loss=..., val_loss=..., val_accuracy=...)
    logger.finish(metrics=result["metrics"], extra={"epochs": ...})
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Tee:
    """同时写入控制台和日志文件。"""

    def __init__(self, *streams):
        self.streams = [stream for stream in streams if stream is not None]

    def write(self, data):
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        for stream in self.streams:
            try:
                stream.write(data)
                stream.flush()
            except Exception:
                pass
        return len(data)

    def flush(self):
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    @property
    def encoding(self):
        return getattr(self.streams[0], "encoding", "utf-8") if self.streams else "utf-8"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_info(root: Path) -> dict:
    info = {"commit": None, "branch": None, "dirty_files": None}
    try:
        info["commit"] = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        info["branch"] = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        info["dirty_files"] = len([line for line in status.splitlines() if line.strip()])
    except (OSError, subprocess.SubprocessError):
        pass
    return info


def _package_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def _environment() -> dict:
    env = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "cwd": os.getcwd(),
        "packages": {
            "torch": _package_version("torch"),
            "torchvision": _package_version("torchvision"),
            "scikit-learn": _package_version("scikit-learn"),
            "numpy": _package_version("numpy"),
            "opencv-python": _package_version("opencv-python"),
            "Pillow": _package_version("Pillow"),
            "matplotlib": _package_version("matplotlib"),
        },
    }
    try:
        import torch

        env["cuda_available"] = bool(torch.cuda.is_available())
        env["torch_threads"] = torch.get_num_threads()
    except Exception:
        env["cuda_available"] = None
    return env


TRACKED_FILES = (
    "configs/default.yaml",
    "data/manifests/sample_manifest.csv",
    "data/manifests/exclusions.csv",
    "data/splits/split_v3.json",
    "data/annotations/manual_corners.csv",
    "data/annotations/manual_labels.csv",
    "data/annotations/assignees.csv",
    "data/manifests/external_aux.csv",
)


class RunLogger:
    """一次训练运行的完整日志。"""

    def __init__(
        self,
        exp_id: str,
        out_dir: Path,
        script: str,
        args: Any,
        config: dict | None = None,
        *,
        root: Path,
        notes: str = "",
    ) -> None:
        self.exp_id = exp_id
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.script = script
        self.root = Path(root)
        self.notes = notes
        self.started_at = datetime.now(timezone.utc)
        self._started = time.perf_counter()
        self.log_path = self.out_dir / "train.log"
        self.run_path = self.out_dir / "run.json"
        self.epoch_path = self.out_dir / "epochs.csv"
        self._log_handle = self.log_path.open("a", encoding="utf-8")
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = Tee(sys.__stdout__, self._log_handle)
        sys.stderr = Tee(sys.__stderr__, self._log_handle)
        self._finished = False
        self.meta = self._build_meta(args, config)
        self._write()
        atexit.register(self._finalize_if_running)

    def _build_meta(self, args: Any, config: dict | None) -> dict:
        files = {}
        for name in TRACKED_FILES:
            path = self.root / name
            if path.is_file():
                files[name] = {
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
        return {
            "schema_version": 1,
            "exp_id": self.exp_id,
            "script": self.script,
            "status": "running",
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": None,
            "duration_seconds": None,
            "argv": [str(item) for item in sys.argv],
            "args": _jsonable(vars(args)) if hasattr(args, "__dict__") else _jsonable(args),
            "config": _jsonable(config or {}),
            "environment": _environment(),
            "git": _git_info(self.root),
            "files": files,
            "metrics": None,
            "artifacts": [],
            "notes": self.notes,
        }

    def _write(self) -> None:
        self.run_path.write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{stamp}] {message}")

    def log_epoch(
        self,
        epoch: int,
        *,
        train_loss: float | None = None,
        val_loss: float | None = None,
        val_accuracy: float | None = None,
    ) -> None:
        new_file = not self.epoch_path.is_file()
        with self.epoch_path.open("a", encoding="utf-8", newline="") as stream:
            import csv

            writer = csv.writer(stream)
            if new_file:
                writer.writerow(
                    [
                        "epoch",
                        "timestamp",
                        "elapsed_seconds",
                        "train_loss",
                        "val_loss",
                        "val_accuracy",
                    ]
                )
            writer.writerow(
                [
                    epoch,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    round(time.perf_counter() - self._started, 2),
                    "" if train_loss is None else round(float(train_loss), 6),
                    "" if val_loss is None else round(float(val_loss), 6),
                    "" if val_accuracy is None else round(float(val_accuracy), 6),
                ]
            )

    def finish(
        self,
        *,
        metrics: dict | None = None,
        extra: dict | None = None,
        status: str = "completed",
    ) -> None:
        self.meta["status"] = status
        self.meta["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.meta["duration_seconds"] = round(time.perf_counter() - self._started, 2)
        self.meta["metrics"] = _jsonable(metrics or {})
        self.meta["extra"] = _jsonable(extra or {})
        artifacts = []
        for path in sorted(self.out_dir.rglob("*")):
            if path.is_file():
                artifacts.append(
                    {
                        "path": str(path.relative_to(self.out_dir)),
                        "bytes": path.stat().st_size,
                    }
                )
        self.meta["artifacts"] = artifacts
        self._write()
        self._finished = True
        self._restore()

    def _finalize_if_running(self) -> None:
        if self._finished:
            return
        try:
            self.meta["status"] = "interrupted"
            self.meta["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.meta["duration_seconds"] = round(time.perf_counter() - self._started, 2)
            self._write()
            self._restore()
        except Exception:
            pass

    def fail(self, error: BaseException) -> None:
        self.log(f"运行失败: {error}")
        traceback.print_exc()
        self.meta["status"] = "failed"
        self.meta["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.meta["duration_seconds"] = round(time.perf_counter() - self._started, 2)
        self.meta["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        self._write()
        self._finished = True
        self._restore()

    def _restore(self) -> None:
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr
        try:
            self._log_handle.close()
        except Exception:
            pass
