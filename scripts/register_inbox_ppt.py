"""把 00_inbox 中的 PPT 幕布样本归档到 ppt_text / ppt_formula 并登记。

人工判定基于 2026-11-27 的 93 张课堂幕布照片：含显式数学公式/推导的页面
归为 ppt_formula，其余归为 ppt_text。所有新增样本只进入训练集，不进入
val/test；生成 split_v4 并将配置切换到 v4。

用法：
    PYTHONPATH=src python3 scripts/register_inbox_ppt.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import FIELDS  # noqa: E402

INBOX = ROOT / "data/raw_samples/00_inbox"
MANIFEST = ROOT / "data/manifests/sample_manifest.csv"
MAPPING = ROOT / "data/manifests/inbox_ppt_20261127.csv"
SPLIT_V3 = ROOT / "data/splits/split_v3.json"
SPLIT_V4 = ROOT / "data/splits/split_v4.json"

# 人工判定：含显式数学公式的 PPT 页
FORMULA_INDICES = {
    22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34,
    38, 39, 41,
    52, 53, 54, 55, 56,
    63, 69, 71, 72,
    77, 78, 79, 80, 81, 83, 84, 86, 87, 88, 89,
}
# 文件名可能随排序变化；以当前 00_inbox 的稳定排序为准，脚本一次性执行。


def parse_date(name: str) -> str:
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", name)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else "2026-11-27"


def exif_device(image: Image.Image) -> str:
    exif = image.getexif()
    make = str(exif.get(271, "") or "").strip()
    model = str(exif.get(272, "") or "").strip()
    return " ".join(part for part in (make, model) if part) or "unknown"


def main() -> int:
    files = sorted(
        p
        for p in INBOX.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic"}
    )
    if not files:
        raise SystemExit("00_inbox 没有可归档图片")
    rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8-sig", newline="")))
    existing = {row["sample_id"] for row in rows}
    mapping = []
    new_rows = []
    for index, path in enumerate(files):
        label = "ppt_formula" if index in FORMULA_INDICES else "ppt_text"
        target_dir = ROOT / "data/raw_samples" / ("02_ppt_formula" if label == "ppt_formula" else "01_ppt_text")
        target_dir.mkdir(parents=True, exist_ok=True)
        sample_id = path.stem
        if sample_id in existing:
            sample_id = f"{sample_id}_inbox"
        suffix = 1
        sample_id_base = sample_id
        while sample_id in existing:
            suffix += 1
            sample_id = f"{sample_id_base}_{suffix}"
        target = target_dir / path.name
        if target.exists():
            target = target_dir / f"{path.stem}_{suffix}{path.suffix}"
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            device = exif_device(image)
        page_id = f"PT-INBOX-{index + 1:03d}"
        row = {
            "sample_id": sample_id,
            "file": target.relative_to(ROOT / "data/raw_samples").as_posix(),
            "label": label,
            "doc_page_id": page_id,
            "shooter": "yqy",
            "device": device,
            "scene": "classroom",
            "angle_deg": "10",
            "lighting": "ceiling",
            "resolution": f"{width}x{height}",
            "shot_at": parse_date(path.name),
            "notes": "2026-11-27 inbox PPT 幕布样本；公式/文字人工判定；角度未逐张测量",
            "privacy_masked": "false",
            "privacy_regions": "0",
            "release_file": "",
        }
        shutil.move(str(path), str(target))
        existing.add(sample_id)
        new_rows.append(row)
        mapping.append({"original_name": path.name, "sample_id": sample_id, "label": label, "doc_page_id": page_id, "file": row["file"]})
    rows.extend(new_rows)
    with MANIFEST.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FIELDS), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    with MAPPING.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(mapping[0].keys()))
        writer.writeheader()
        writer.writerows(mapping)

    split = json.loads(SPLIT_V3.read_text(encoding="utf-8"))
    groups = {name: list(values) for name, values in split["groups"].items()}
    groups["train"].extend(row["doc_page_id"] for row in new_rows)
    page_to_split = {page: name for name, pages in groups.items() for page in pages}
    excluded = {
        row["sample_id"]
        for row in csv.DictReader((ROOT / "data/manifests/exclusions.csv").open(encoding="utf-8-sig"))
    }
    counts = Counter()
    for row in rows:
        page = row["doc_page_id"]
        if row["sample_id"] in excluded or not row["label"] or page not in page_to_split:
            continue
        counts[page_to_split[page]] += 1
    doc = {
        "version": "v4",
        "seed": split["seed"],
        "group_key": split["group_key"],
        "ratio": split["ratio"],
        "groups": groups,
        "counts": {name: int(counts.get(name, 0)) for name in ("train", "val", "test")},
        "frozen_at": "2026-11-27",
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "note": "2026-11-27 新增 93 张 PPT 幕布样本，只加入 train；val/test 与 split_v3 一致",
    }
    SPLIT_V4.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"归档 {len(new_rows)} 张；{Counter(row['label'] for row in new_rows)}")
    print(f"split_v4 counts={doc['counts']} manifest={doc['manifest_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
