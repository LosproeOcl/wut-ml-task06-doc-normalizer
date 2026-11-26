"""从 SCB-Dataset 教师子集生成屏幕检测清单。

只保留含 `screen` 类的图像，取面积最大的屏幕框，输出归一化 xyxy。

用法：
    PYTHONPATH=src python scripts/build_scb_screen_manifest.py \
      --root data/raw_samples/external-assets/scb-teacher
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data/manifests/scb_screen.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT / "data/raw_samples/external-assets/scb-teacher",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def find_images_dir(root: Path) -> Path:
    candidates = [path for path in root.rglob("images") if path.is_dir()]
    for path in candidates:
        if (path / "train").is_dir() and (path / "val").is_dir():
            return path
    if candidates:
        return candidates[0]
    raise SystemExit(f"找不到 images 目录: {root}")


def screen_index(images_dir: Path) -> int:
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


def parse_label(path: Path, class_index: int) -> tuple[float, float, float, float] | None:
    if not path.is_file():
        return None
    best = None
    best_area = -1.0
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            label = int(float(parts[0]))
            cx, cy, width, height = (float(value) for value in parts[1:5])
        except ValueError:
            continue
        if label != class_index:
            continue
        area = width * height
        if area > best_area:
            best_area = area
            best = (
                max(0.0, cx - width / 2),
                max(0.0, cy - height / 2),
                min(1.0, cx + width / 2),
                min(1.0, cy + height / 2),
            )
    return best


def main() -> int:
    args = parse_args()
    args.root = args.root.resolve()
    images_dir = find_images_dir(args.root)
    class_index = screen_index(images_dir)
    rows = []
    for split in ("train", "val"):
        image_dir = images_dir / split
        label_dir = images_dir.parent / "labels" / split
        for image_path in sorted(image_dir.iterdir()):
            if not image_path.is_file():
                continue
            box = parse_label(label_dir / f"{image_path.stem}.txt", class_index)
            if box is None:
                continue
            area = (box[2] - box[0]) * (box[3] - box[1])
            aspect = (box[2] - box[0]) / max(box[3] - box[1], 1e-6)
            if area < 0.02 or area > 0.95 or not 0.25 <= aspect <= 4.0:
                continue
            rows.append(
                {
                    "path": str(image_path.resolve().relative_to(ROOT)),
                    "x1": round(box[0], 6),
                    "y1": round(box[1], 6),
                    "x2": round(box[2], 6),
                    "y2": round(box[3], 6),
                    "split": split,
                    "source": "SCB-Dataset-teacher",
                }
            )
    if not rows:
        raise SystemExit(f"没有找到 screen 标注: {images_dir}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["path", "x1", "y1", "x2", "y2", "split", "source"],
        )
        writer.writeheader()
        writer.writerows(rows)
    train_count = sum(1 for row in rows if row["split"] == "train")
    print(f"写入 {args.out}，共 {len(rows)} 张（train {train_count} / val {len(rows)-train_count}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
