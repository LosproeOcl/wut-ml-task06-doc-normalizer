#!/usr/bin/env python
"""核对清单记录与实际文件是否一致。

用法：
    python scripts/check_dataset.py data/manifests/sample_manifest.csv \
        --root data/raw_samples

清单中的 ``file`` 字段是相对于 ``data/raw_samples/`` 的路径；本脚本检查每条
记录对应的图像文件是否存在、是否非空，并报告清单中有但磁盘缺失（或反之）的情况。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docnorm.data.manifest import parse_manifest  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="核对清单与磁盘文件一致性")
    parser.add_argument("manifest", help="样本清单 CSV 路径")
    parser.add_argument("--root", default="data/raw_samples", help="图像根目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)

    root = Path(args.root)
    manifest = parse_manifest(args.manifest)

    missing: list[str] = []
    empty: list[str] = []
    for row in manifest.rows:
        if not row.file:
            continue
        p = root / row.file
        if not p.exists():
            missing.append(row.file)
        elif p.stat().st_size == 0:
            empty.append(row.file)

    # 磁盘上有、但清单未登记的文件（仅限四格归档目录与 inbox，排除发布副本）。
    tracked_dirs = {"00_inbox", "01_ppt_text", "02_ppt_formula",
                    "03_paper_text", "04_paper_formula", "99_unlabeled"}
    listed = {row.file for row in manifest.rows if row.file}
    untracked: list[str] = []
    for sub in sorted(tracked_dirs):
        d = root / sub
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                rel = p.relative_to(root).as_posix()
                if rel not in listed:
                    untracked.append(rel)

    ok = not missing and not empty
    result = {
        "ok": ok,
        "n_rows": len(manifest.rows),
        "missing_files": missing,
        "empty_files": empty,
        "untracked_files": untracked,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"清单记录：{len(manifest.rows)} 条")
        print(f"磁盘缺失：{len(missing)} 个")
        for f in missing[:20]:
            print(f"  [缺失] {f}")
        print(f"空文件：{len(empty)} 个")
        for f in empty[:20]:
            print(f"  [空] {f}")
        print(f"清单未登记：{len(untracked)} 个")
        for f in untracked[:20]:
            print(f"  [未登记] {f}")
        print(f"\n结论：{'一致' if ok else '存在不一致'}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
