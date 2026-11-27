"""把 inbox 中新增的实拍样本登记进清单、幻灯片分组与 train 划分。

流程与 2026-11-27 首批 93 张一致：按映射表把文件移入类别目录，
补充 sample_manifest.csv 行，更新 inbox_slide_groups.csv，
把新分组加入 split_v4 的 train 并重算清单哈希。

用法：
    python scripts/ingest_inbox_batch.py \
      --mapping data/manifests/inbox_ppt_20261127b.csv --dry-run
    python scripts/ingest_inbox_batch.py \
      --mapping data/manifests/inbox_ppt_20261127b.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import FIELDS  # noqa: E402

MANIFEST = ROOT / "data/manifests/sample_manifest.csv"
GROUPS = ROOT / "data/manifests/inbox_slide_groups.csv"
SPLIT = ROOT / "data/splits/split_v4.json"
EXCLUSIONS = ROOT / "data/manifests/exclusions.csv"
INBOX = ROOT / "data/raw_samples/00_inbox"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def shot_date(path: Path) -> str:
    with Image.open(path) as image:
        exif = image.getexif()
        value = exif.get(36867) or exif.get(306)
    if not value:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    return str(value).split()[0].replace(":", "-")


def resolution(path: Path) -> str:
    with Image.open(path) as image:
        width, height = ImageOps.exif_transpose(image).size
    return f"{width}x{height}"


def sharpness(path: Path) -> float:
    """与现有分组脚本一致：全分辨率灰度图 3x3 Laplacian 方差。"""
    with Image.open(path) as image:
        grayscale = ImageOps.exif_transpose(image).convert("L")
        array = np.asarray(grayscale, dtype=np.float32)
    laplacian = (
        4 * array[1:-1, 1:-1]
        - array[:-2, 1:-1]
        - array[2:, 1:-1]
        - array[1:-1, :-2]
        - array[1:-1, 2:]
    )
    return float(laplacian.var())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--shooter", default="yqy")
    parser.add_argument("--device", default="iPhone Air")
    parser.add_argument("--scene", default="dorm")
    parser.add_argument("--lighting", default="ceiling")
    parser.add_argument("--note", default="2026-11-27 第二批 inbox 实拍幕布样本；人工判定为文字页；用于四角定位增训；角度未逐张测量")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    mapping = read_csv(args.mapping)
    if not mapping:
        raise SystemExit("映射表为空")

    manifest = read_csv(MANIFEST)
    known = {row["sample_id"] for row in manifest}
    groups_rows = read_csv(GROUPS)
    group_known = {row["sample_id"] for row in groups_rows}

    to_add = []
    sharp = {}
    for row in mapping:
        sample_id = row["sample_id"].strip()
        if not sample_id:
            raise SystemExit("映射表存在空 sample_id")
        if sample_id in known:
            print(f"跳过已登记样本 {sample_id}")
            continue
        source = INBOX / row["original_name"]
        target = ROOT / "data/raw_samples" / row["file"]
        if not source.is_file() and target.is_file():
            source = target
        if not source.is_file():
            raise SystemExit(f"找不到源文件: {source}")
        sharp[sample_id] = sharpness(source)
        to_add.append(
            {
                "sample_id": sample_id,
                "file": row["file"],
                "label": row["label"],
                "doc_page_id": row["doc_page_id"],
                "shooter": args.shooter,
                "device": args.device,
                "scene": args.scene,
                "angle_deg": "10",
                "lighting": args.lighting,
                "resolution": resolution(source),
                "shot_at": shot_date(source),
                "notes": args.note,
                "privacy_masked": "false",
                "privacy_regions": "0",
                "release_file": "",
                "_source": str(source),
                "_target": str(target),
            }
        )

    if not to_add:
        print("没有需要登记的新样本。")
        return 0

    new_groups = sorted({row["doc_page_id"] for row in to_add})
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    existing_group_set = {g: name for name, pages in split["groups"].items() for g in pages}
    for group in new_groups:
        if existing_group_set.get(group, "train") != "train":
            raise SystemExit(f"分组 {group} 已在 {existing_group_set[group]}，拒绝重复加入")

    print(f"新增 {len(to_add)} 张，分组 {new_groups}")
    for row in to_add:
        print(f"  {row['sample_id']} -> {row['file']} {row['resolution']} {row['shot_at']}")
    if args.dry_run:
        print("预演模式，未写入。")
        return 0

    # 1) 移动文件到类别目录
    for row in to_add:
        source = Path(row.pop("_source"))
        target = Path(row.pop("_target"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if source != target:
            source.replace(target)

    # 2) 追加清单行
    with MANIFEST.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FIELDS), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(manifest)
        writer.writerows(to_add)

    # 3) 更新幻灯片分组与代表帧
    representatives = {}
    for group in new_groups:
        members = [row for row in to_add if row["doc_page_id"] == group]
        representatives[group] = max(members, key=lambda row: sharp[row["sample_id"]])["sample_id"]
    with GROUPS.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(["sample_id", "original_name", "slide_group", "representative", "sharpness"])
        for row in groups_rows:
            writer.writerow([row["sample_id"], row["original_name"], row["slide_group"], row["representative"], row["sharpness"]])
        for row in to_add:
            writer.writerow(
                [
                    row["sample_id"],
                    Path(row["file"]).name,
                    row["doc_page_id"],
                    int(representatives[row["doc_page_id"]] == row["sample_id"]),
                    f"{sharp[row['sample_id']]:.2f}",
                ]
            )

    # 4) 新分组只加入 train，重算 counts 与清单哈希
    train_groups = list(dict.fromkeys(list(split["groups"]["train"]) + new_groups))
    split["groups"]["train"] = sorted(train_groups)
    page_to_split = {g: name for name, pages in split["groups"].items() for g in pages}
    excluded = {row["sample_id"] for row in read_csv(EXCLUSIONS)}
    all_rows = manifest + to_add
    counts = Counter()
    for row in all_rows:
        if row["sample_id"] in excluded or not row["label"]:
            continue
        name = page_to_split.get(row["doc_page_id"])
        if name:
            counts[name] += 1
    split["counts"] = {name: int(counts.get(name, 0)) for name in ("train", "val", "test")}
    split["manifest_sha256"] = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    split["note"] = "2026-11-27 首批 93 张 + 第二批 9 张 PPT 实拍样本只加入 train；val/test 与 v3 一致"
    SPLIT.write_text(json.dumps(split, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"清单 {len(all_rows)} 行，counts={split['counts']}，代表帧 {representatives}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
