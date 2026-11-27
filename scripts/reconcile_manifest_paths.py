"""根据磁盘实际位置修正清单中的 file 与归档 label。

用于样本在 01_ppt_text / 02_ppt_formula / 03_paper_text / 04_paper_formula
之间移动后标签已人工修正的场景。默认只预演，--apply 才写回。

用法：
    PYTHONPATH=src python3 scripts/reconcile_manifest_paths.py
    PYTHONPATH=src python3 scripts/reconcile_manifest_paths.py --apply
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import FIELDS  # noqa: E402

DIR_LABEL = {
    "01_ppt_text": "ppt_text",
    "02_ppt_formula": "ppt_formula",
    "03_paper_text": "paper_text",
    "04_paper_formula": "paper_formula",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/manifests/sample_manifest.csv")
    parser.add_argument("--root", type=Path, default=ROOT / "data/raw_samples")
    parser.add_argument("--apply", action="store_true", help="写回清单；默认只预演")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    rows = list(csv.DictReader(manifest.open(encoding="utf-8-sig", newline="")))
    changes = []
    for row in rows:
        path = args.root / row["file"]
        if path.is_file():
            continue
        matches = sorted(args.root.rglob(Path(row["file"]).name))
        if not matches:
            print(f"[缺失] {row['sample_id']}: {row['file']}")
            continue
        if len(matches) > 1:
            print(f"[歧义] {row['sample_id']}: {[str(p.relative_to(args.root)) for p in matches]}")
            continue
        actual = matches[0]
        label = DIR_LABEL.get(actual.parent.name)
        if label is None:
            print(f"[跳过] {row['sample_id']}: 实际目录不在四格归档内 {actual}")
            continue
        new_file = actual.relative_to(args.root).as_posix()
        changes.append((row, new_file, label))

    for row, new_file, label in changes:
        print(
            f"{row['sample_id']}: {row['file']} [{row['label']}] -> "
            f"{new_file} [{label}]"
        )
    if not changes:
        print("没有需要修正的路径")
        return 0
    if not args.apply:
        print(f"预演 {len(changes)} 条；加 --apply 写回")
        return 0

    for row, new_file, label in changes:
        row["file"] = new_file
        row["label"] = label
    with manifest.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FIELDS), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"已写回 {manifest}，修改 {len(changes)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
