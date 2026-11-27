"""构建“是否为投影幕布”门控分类器清单。

正类：SCB screen 图 + 自采 train 中 ppt_* 图。
负类：SCB 无 screen 框的教师子集图 + 自采 train 中 paper_* 图。
自采 val 只用于最终评估，不进入门控训练。

用法：
    PYTHONPATH=src python scripts/build_screen_gate_manifest.py
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402

ASSETS = ROOT / "data/raw_samples/external-assets/scb-teacher"
OUT = ROOT / "data/manifests/screen_gate.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scb-root", type=Path, default=ASSETS)
    parser.add_argument("--screen-manifest", type=Path, default=ROOT / "data/manifests/scb_screen.csv")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--pos", type=int, default=1000)
    parser.add_argument("--neg", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def find_images_dir(root: Path) -> Path:
    for path in root.rglob("images"):
        if path.is_dir() and (path / "train").is_dir() and (path / "val").is_dir():
            return path
    raise SystemExit(f"找不到 images 目录: {root}")


def screen_class_index(images_dir: Path) -> int:
    for yaml_path in images_dir.parent.glob("*.yaml"):
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        names = data.get("names")
        if isinstance(names, list):
            for index, name in enumerate(names):
                if str(name).lower() == "screen":
                    return index
        if isinstance(names, dict):
            for key, name in names.items():
                if str(name).lower() == "screen":
                    return int(key)
    return 6


def has_screen(label_path: Path, class_index: int) -> bool:
    if not label_path.is_file():
        return False
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 5 and int(float(parts[0])) == class_index:
            return True
    return False


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    args.scb_root = args.scb_root.resolve()
    images_dir = find_images_dir(args.scb_root)
    class_index = screen_class_index(images_dir)
    screen_rows = list(csv.DictReader(args.screen_manifest.open(encoding="utf-8")))
    positives = {
        split: [row["path"] for row in screen_rows if row["split"] == split]
        for split in ("train", "val")
    }

    negatives = {"train": [], "val": []}
    for split in ("train", "val"):
        label_dir = images_dir.parent / "labels" / split
        for image_path in sorted((images_dir / split).iterdir()):
            if not image_path.is_file():
                continue
            if not has_screen(label_dir / f"{image_path.stem}.txt", class_index):
                negatives[split].append(str(image_path.resolve().relative_to(ROOT)))

    rows = []
    for split, count in (("train", args.pos), ("val", max(100, args.pos // 2))):
        for path in rng.sample(positives[split], min(count, len(positives[split]))):
            rows.append({"path": path, "label": "screen", "source": "SCB-screen", "split": split})
    for split, count in (("train", args.neg), ("val", max(100, args.neg // 2))):
        for path in rng.sample(negatives[split], min(count, len(negatives[split]))):
            rows.append({"path": path, "label": "other", "source": "SCB-other", "split": split})

    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = assign_samples(load_split(ROOT / "data/splits/split_v4.json"), samples)
    for sample in samples:
        if split.get(sample.sample_id) != "train":
            continue
        carrier = (sample.label or "").split("_")[0]
        if carrier not in {"ppt", "paper"}:
            continue
        rows.append(
            {
                "path": str((ROOT / "data/raw_samples" / sample.file).resolve().relative_to(ROOT)),
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
