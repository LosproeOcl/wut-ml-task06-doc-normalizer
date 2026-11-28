#!/usr/bin/env python3
"""构建合成投影 PPT 的背景清单。

背景只用自采 train 的 PPT 页面（人工四角）与少量 SCB 教室图；
val/test 样本不进入背景池。每个 doc_page_id 只保留一张，避免同一页
的多张近景重复。

用法：
    PYTHONPATH=src python scripts/build_synth_backgrounds.py \
      --out data/manifests/synth_backgrounds_v1.csv --per-class 24
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402

DEFAULT_OUT = ROOT / "data/manifests/synth_backgrounds_v1.csv"
SCB_MANIFEST = ROOT / "data/manifests/scb_screen.csv"
MANIFEST = ROOT / "data/manifests/sample_manifest.csv"
EXCLUSIONS = ROOT / "data/manifests/exclusions.csv"
SPLIT = ROOT / "data/splits/split_v4.json"
CORNERS = ROOT / "data/annotations/manual_corners.csv"

SCB_WANTED = [
    "111_000056.jpg",
    "111_000060.jpg",
    "111_000061.jpg",
    "111_000952.jpg",
    "111_000953.jpg",
    "111_000954.jpg",
    "111_001266.jpg",
    "116_001726.jpg",
    "132_001287.jpg",
    "133_000892.jpg",
]


def order_quad(points: list[list[float]]) -> list[tuple[float, float]]:
    """按 TL / TR / BR / BL 排序，兼容人工标注的点序。"""
    pts = sorted(((float(x), float(y)) for x, y in points), key=lambda p: p[1])
    top = sorted(pts[:2], key=lambda p: p[0])
    bottom = sorted(pts[2:], key=lambda p: p[0])
    return [top[0], top[1], bottom[1], bottom[0]]


def quad_stats(image: Image.Image, quad: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """返回 (area_ratio, skin_ratio, dark_ratio, bright_ratio)。"""
    small = image.resize((480, 360))
    arr = np.asarray(small, dtype=np.float32)
    w, h = small.size
    pts = [(x * w, y * h) for x, y in quad]
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    selected = arr[np.asarray(mask) > 0]
    if selected.size == 0:
        return 0.0, 0.0, 0.0, 0.0
    value = selected.max(axis=1)
    red, green, blue = selected[:, 0], selected[:, 1], selected[:, 2]
    skin = (
        (red > 95)
        & (green > 40)
        & (blue > 20)
        & (red > green + 15)
        & (red > blue + 15)
        & (np.abs(red - green) > 15)
    ).mean()
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    area = (max(xs) - min(xs)) * (max(ys) - min(ys)) / (w * h)
    return float(area), float(skin), float((value < 70).mean()), float((value > 190).mean())


def build(per_class: int) -> list[dict]:
    samples = load_manifest(MANIFEST, exclusions_path=EXCLUSIONS)
    split = assign_samples(load_split(SPLIT), samples)
    corners = {
        row["sample_id"]: json.loads(row["points"])
        for row in csv.DictReader(CORNERS.open(encoding="utf-8"))
    }
    candidates: list[dict] = []
    for sample in samples:
        if not (sample.label or "").startswith("ppt_"):
            continue
        if split.get(sample.sample_id) != "train" or sample.sample_id not in corners:
            continue
        path = ROOT / "data/raw_samples" / sample.file
        with Image.open(path) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
            width, height = image.size
            pts = order_quad(corners[sample.sample_id])
            quad = [(x / width, y / height) for x, y in pts]
            area, skin, dark, bright = quad_stats(image, quad)
        if not (0.30 <= area <= 0.65) or skin > 0.02 or dark > 0.08:
            continue
        candidates.append(
            {
                "background_id": f"self-{sample.sample_id}",
                "path": str(path.relative_to(ROOT)),
                "quad": quad,
                "area": area,
                "skin": skin,
                "dark": dark,
                "bright": bright,
                "label": sample.content_label,
                "doc_page_id": sample.doc_page_id,
                "width": width,
                "height": height,
                "source": "self-train-ppt",
                "orig_label": sample.label,
            }
        )

    # 每个 doc_page_id 只留一张，优先面积大、皮肤/暗部少
    best: dict[tuple[str, str], dict] = {}
    for row in candidates:
        key = (row["label"] or "", row["doc_page_id"])
        score = row["area"] - 2.5 * row["skin"] - 0.4 * row["dark"]
        if key not in best or score > best[key]["_score"]:
            row["_score"] = score
            best[key] = row
    by_label: dict[str, list[dict]] = {"text": [], "formula": []}
    for row in best.values():
        if row["label"] in by_label:
            by_label[row["label"]].append(row)
    for label in by_label:
        by_label[label].sort(key=lambda r: r["_score"], reverse=True)

    selected: list[dict] = []
    for label in ("text", "formula"):
        selected.extend(by_label[label][:per_class])
    return selected


def load_scb() -> list[dict]:
    rows = []
    with SCB_MANIFEST.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if Path(row["path"]).name not in SCB_WANTED:
                continue
            path = ROOT / row["path"]
            if not path.is_file():
                continue
            x1, y1, x2, y2 = (float(row[k]) for k in ("x1", "y1", "x2", "y2"))
            quad = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            with Image.open(path) as im:
                width, height = im.size
            rows.append(
                {
                    "background_id": f"scb-{Path(row['path']).stem}",
                    "path": str(path.relative_to(ROOT)),
                    "quad": quad,
                    "area": (x2 - x1) * (y2 - y1),
                    "skin": 0.0,
                    "dark": 0.0,
                    "bright": 0.0,
                    "label": None,
                    "doc_page_id": None,
                    "width": width,
                    "height": height,
                    "source": "SCB-Dataset-teacher",
                    "orig_label": "screen",
                }
            )
    rows.sort(key=lambda r: r["background_id"])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--per-class", type=int, default=24, help="自采文本/公式背景各保留多少")
    parser.add_argument("--include-scb", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    rows = build(args.per_class)
    if not args.include_scb:
        rows = [r for r in rows if r["source"] != "SCB-Dataset-teacher"]
    else:
        rows.extend(load_scb())

    fieldnames = [
        "background_id", "path", "x1", "y1", "x2", "y2", "quad",
        "width", "height", "source", "orig_label", "doc_page_id",
        "area", "skin", "dark",
    ]
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            xs = [p[0] for p in row["quad"]]
            ys = [p[1] for p in row["quad"]]
            writer.writerow(
                {
                    "background_id": row["background_id"],
                    "path": row["path"],
                    "x1": f"{min(xs):.6f}",
                    "y1": f"{min(ys):.6f}",
                    "x2": f"{max(xs):.6f}",
                    "y2": f"{max(ys):.6f}",
                    "quad": json.dumps(row["quad"]),
                    "width": row["width"],
                    "height": row["height"],
                    "source": row["source"],
                    "orig_label": row["orig_label"],
                    "doc_page_id": row["doc_page_id"] or "",
                    "area": f"{row['area']:.4f}",
                    "skin": f"{row['skin']:.4f}",
                    "dark": f"{row['dark']:.4f}",
                }
            )
    counts = {source: sum(r["source"] == source for r in rows) for source in set(r["source"] for r in rows)}
    print(f"写入 {len(rows)} 个背景: {counts}; {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
