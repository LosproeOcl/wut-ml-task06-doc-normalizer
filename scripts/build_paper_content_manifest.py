"""构建纸质稿内容分类训练清单：自采 paper + 外部 A4 纸质数据。

外部数据只用于纸质稿专用分类器；自采 val 只评估，不参与训练。
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data/raw_samples/external-assets"
OUT = ROOT / "data/manifests/paper_content.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    sys.path.insert(0, str(ROOT / "src"))
    from docnorm.data.manifest import load_manifest
    from docnorm.data.split import assign_samples, load_split

    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = assign_samples(load_split(ROOT / "data/splits/split_v3.json"), samples)
    rows = []
    for sample in samples:
        if not (sample.label or "").startswith("paper_"):
            continue
        name = split.get(sample.sample_id)
        if name not in {"train", "val"}:
            continue
        rows.append(
            {
                "path": relative(ROOT / "data/raw_samples" / sample.file),
                "label": sample.content_label,
                "source": "self-paper",
                "split": name,
                "sample_id": sample.sample_id,
            }
        )

    pools = [
        (sorted((ASSETS / "smartdoc2015-ch1").glob("background*/*/frame_*.jpeg")), "smartdoc2015-ch1", "text", 250),
        (sorted((ASSETS / "tobacco3482/images").glob("*/*.jpg")), "tobacco3482", "text", 200),
        (sorted((ASSETS / "iam-handwriting-finevision/images").glob("*.png")), "iam-handwriting-finevision", "text", 50),
        (sorted((ASSETS / "im2latex-100k/images").glob("*.png")), "im2latex-100k", "formula", 400),
    ]
    for files, source, label, count in pools:
        if not files:
            continue
        for path in rng.sample(files, min(count, len(files))):
            rows.append(
                {
                    "path": relative(path),
                    "label": label,
                    "source": source,
                    "split": "train",
                    "sample_id": "",
                }
            )

    rng.shuffle(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "label", "source", "split", "sample_id"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"写入 {args.out}，共 {len(rows)} 张")
    print("来源:", Counter(row["source"] for row in rows))
    print("标签:", Counter(row["label"] for row in rows))
    print("划分:", Counter(row["split"] for row in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
