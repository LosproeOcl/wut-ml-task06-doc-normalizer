#!/usr/bin/env python3
"""把合成 PPT 产物转成 train_cnn 可读的额外训练清单。

输出列：sample_id,path,label,group,rectify
- path 相对仓库根目录；
- group 为背景来源的 doc_page_id，训练时若该组在当前 CV 验证折内会被跳过；
- 合成图已经裁好，训练时不再做四角拉正（rectify=0）。
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/synthetic/ppt_projection_v2/manifest.csv"
DEFAULT_OUT = ROOT / "data/manifests/synth_ppt_v2_train.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--per-cell",
        type=int,
        default=0,
        help="每个模板×类别最多取多少条；0 表示全部",
    )
    args = parser.parse_args()

    manifest = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    if not manifest.is_file():
        raise SystemExit(f"合成清单不存在: {manifest}")
    rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
    if args.per_cell:
        kept = []
        used = Counter()
        for row in rows:
            key = (row["template"], row["label"])
            if used[key] >= args.per_cell:
                continue
            used[key] += 1
            kept.append(row)
        rows = kept
    if not rows:
        raise SystemExit("没有可写入的合成样本")

    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["sample_id", "path", "label", "group", "rectify"]
        )
        writer.writeheader()
        for row in rows:
            # 合成清单里的 path 是相对其输出目录的；这里按实际清单目录解析。
            image = manifest.parent / row["path"]
            if not image.is_file():
                raise SystemExit(f"合成图缺失: {image}")
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "path": str(image.relative_to(ROOT)),
                    "label": row["label"],
                    "group": row.get("background_group", ""),
                    "rectify": 0,
                }
            )

    print(f"写入 {len(rows)} 条 -> {out}")
    print("模板×类别:", dict(Counter((r["template"], r["label"]) for r in rows)))
    print("标签:", dict(Counter(r["label"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
