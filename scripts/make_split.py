#!/usr/bin/env python
"""按分组键生成划分文件并计算清单哈希。

用法：
    python scripts/make_split.py data/manifests/sample_manifest.csv \
        --out data/splits/split_v1.json --seed 42
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docnorm.data.manifest import parse_manifest  # noqa: E402
from docnorm.data.split import (  # noqa: E402
    make_split,
    sha256_file,
    validate_split,
    write_split,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成数据划分文件")
    parser.add_argument("manifest", help="样本清单 CSV 路径")
    parser.add_argument("--out", default="data/splits/split_v1.json", help="输出 JSON 路径")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument(
        "--ratio",
        default="0.7,0.15,0.15",
        help="train,val,test 比例（逗号分隔）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    ratio_parts = [float(x) for x in args.ratio.split(",")]
    if len(ratio_parts) != 3 or abs(sum(ratio_parts) - 1.0) > 1e-6:
        print("--ratio 须为三个和为 1 的数，如 0.7,0.15,0.15", file=sys.stderr)
        return 2
    ratio = {"train": ratio_parts[0], "val": ratio_parts[1], "test": ratio_parts[2]}

    manifest = parse_manifest(args.manifest)
    split = make_split(manifest, seed=args.seed, ratio=ratio)
    split["manifest_sha256"] = sha256_file(args.manifest)

    problems = validate_split(split, manifest)
    if problems:
        for p in problems:
            print(f"[问题] {p}", file=sys.stderr)
        return 1

    write_split(split, args.out)

    if args.json:
        print(json.dumps(split, ensure_ascii=False, indent=2))
    else:
        print(f"已写入：{args.out}")
        print(f"样本数：train={split['counts']['train']}, "
              f"val={split['counts']['val']}, test={split['counts']['test']}")
        print(f"清单哈希：{split['manifest_sha256'][:16]}…")
        print(f"冻结日期：{split['frozen_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
