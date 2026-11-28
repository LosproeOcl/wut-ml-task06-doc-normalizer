"""构建“投影幕布 vs A4 纸质稿”场景门控清单。

正类 screen：SCB screen 图 + 自采 train ppt_*。
负类 paper：SmartDoc/Tobacco/IAM/IM2LATEX 图 + 自采 train paper_*。
自采 val 不参与训练，只用于最终场景/内容评估。
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCB = ROOT / "data/raw_samples/external-assets/scb-teacher"
ASSETS = ROOT / "data/raw_samples/external-assets"
OUT = ROOT / "data/manifests/carrier_gate.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "data/manifests/sample_manifest_v5.csv",
    )
    parser.add_argument(
        "--split",
        type=Path,
        default=ROOT / "data/splits/split_v5.json",
    )
    parser.add_argument("--screen-train", type=int, default=1000)
    parser.add_argument("--paper-train", type=int, default=1000)
    parser.add_argument("--val", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    screen_rows = list(csv.DictReader((ROOT / "data/manifests/scb_screen.csv").open(encoding="utf-8")))
    screen_train = [row["path"] for row in screen_rows if row["split"] == "train"]
    screen_val = [row["path"] for row in screen_rows if row["split"] == "val"]

    smartdoc = sorted((ASSETS / "smartdoc2015-ch1").glob("background*/*/frame_*.jpeg"))
    tobacco = sorted((ASSETS / "tobacco3482/images").glob("*/*.jpg"))
    iam = sorted((ASSETS / "iam-handwriting-finevision/images").glob("*.png"))
    im2latex = sorted((ASSETS / "im2latex-100k/images").glob("*.png"))
    pools = [
        (smartdoc, "smartdoc2015-ch1", 0.4),
        (tobacco, "tobacco3482", 0.4),
        (iam, "iam-handwriting-finevision", 0.1),
        (im2latex, "im2latex-100k", 0.1),
    ]

    rows = []
    for path in rng.sample(screen_train, min(args.screen_train, len(screen_train))):
        rows.append({"path": path, "label": "screen", "source": "SCB-screen", "split": "train"})
    for path in rng.sample(screen_val, min(args.val, len(screen_val))):
        rows.append({"path": path, "label": "screen", "source": "SCB-screen", "split": "val"})
    for split, count in (("train", args.paper_train), ("val", args.val)):
        for files, source, ratio in pools:
            if not files:
                continue
            take = int(round(count * ratio))
            for path in rng.sample(files, min(take, len(files))):
                rows.append({"path": relative(path), "label": "other", "source": source, "split": split})

    # 自采 train：ppt -> screen，paper -> other；val 留给评估
    # 使用项目 split 文件
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from docnorm.data.manifest import load_manifest
    from docnorm.data.split import assign_samples, load_split

    loaded = load_manifest(
        args.manifest,
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = assign_samples(load_split(args.split), loaded)
    for sample in loaded:
        if split.get(sample.sample_id) != "train":
            continue
        carrier = (sample.label or "").split("_")[0]
        if carrier not in {"ppt", "paper"}:
            continue
        rows.append(
            {
                "path": relative(ROOT / "data/raw_samples" / sample.file),
                "label": "screen" if carrier == "ppt" else "other",
                "source": f"self-{carrier}",
                "split": "train",
            }
        )

    rng.shuffle(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "label", "source", "split"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"写入 {args.out}，共 {len(rows)} 张")
    print("来源:", Counter(row["source"] for row in rows))
    print("标签:", Counter(row["label"] for row in rows))
    print("划分:", Counter(row["split"] for row in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
