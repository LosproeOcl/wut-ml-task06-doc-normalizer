#!/usr/bin/env python
"""核对清单记录与实际图像文件是否一致。

在 PR #1「实现数据层」的数据集核对思路基础上，按当前清单与排除表重写；
只读检查，不修改清单、划分或图像。

用法：
    python scripts/check_dataset.py
    python scripts/check_dataset.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import find_missing_files, load_manifest  # noqa: E402

ARCHIVE_DIRS = (
    "00_inbox",
    "01_ppt_text",
    "02_ppt_formula",
    "03_paper_text",
    "04_paper_formula",
    "99_unlabeled",
)


def check_dataset(
    manifest_path: Path,
    *,
    root: Path,
    exclusions_path: Path | None = None,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        all_samples = load_manifest(manifest_path)
        samples = load_manifest(manifest_path, exclusions_path=exclusions_path)
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "manifest": str(manifest_path),
            "n_qualified": 0,
            "missing_files": [],
            "empty_files": [],
            "untracked_files": [],
            "errors": [f"清单无法加载: {exc}"],
            "warnings": warnings,
        }

    missing = find_missing_files(samples, root)
    empty: list[str] = []
    for sample in samples:
        path = root / sample.file
        if path.is_file() and path.stat().st_size == 0:
            empty.append(sample.file)
    if missing:
        errors.append(f"清单记录但文件缺失: {len(missing)} 个")
    if empty:
        errors.append(f"空文件: {len(empty)} 个")

    listed = {sample.file for sample in all_samples}
    untracked: list[str] = []
    for name in ARCHIVE_DIRS:
        directory = root / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            relative = path.relative_to(root).as_posix()
            if relative not in listed:
                untracked.append(relative)
    if untracked:
        warnings.append(f"磁盘存在但未登记的图像: {len(untracked)} 个")

    return {
        "ok": not errors,
        "manifest": str(manifest_path),
        "n_qualified": len(samples),
        "missing_files": missing[:50],
        "empty_files": empty[:50],
        "untracked_files": untracked[:50],
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="核对清单与磁盘图像一致性")
    parser.add_argument("manifest", nargs="?", default=str(ROOT / "data/manifests/sample_manifest.csv"))
    parser.add_argument("--root", default=str(ROOT / "data/raw_samples"))
    parser.add_argument(
        "--exclusions", default=str(ROOT / "data/manifests/exclusions.csv")
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    exclusions = Path(args.exclusions) if args.exclusions else None
    report = check_dataset(Path(args.manifest), root=Path(args.root), exclusions_path=exclusions)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"清单：{report['manifest']}")
        print(f"纳入样本：{report['n_qualified']} 条")
        for error in report["errors"]:
            print(f"[错误] {error}")
        for warning in report["warnings"]:
            print(f"[警告] {warning}")
        for path in report["missing_files"][:20]:
            print(f"  [缺失] {path}")
        for path in report["untracked_files"][:20]:
            print(f"  [未登记] {path}")
        print("结论：一致" if report["ok"] else "结论：存在阻断性不一致")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
