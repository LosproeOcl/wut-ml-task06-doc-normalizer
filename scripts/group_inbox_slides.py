"""按同一张幻灯片聚合 2026-11-27 inbox PPT 样本，并更新清单/划分。"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from docnorm.data.manifest import FIELDS  # noqa: E402

MAPPING = ROOT / "data/manifests/inbox_ppt_20261127.csv"
GROUPS = ROOT / "data/manifests/inbox_slide_groups.csv"
MANIFEST = ROOT / "data/manifests/sample_manifest.csv"
SPLIT = ROOT / "data/splits/split_v4.json"

# 基于幻灯片标题/内容的人工聚合；索引对应 2026-11-27 的排序
GROUPS_BY_INDEX = {
    "G01": [0], "G02": [1], "G03": [2], "G04": [3, 43, 59, 76],
    "G05": [4], "G06": [5], "G07": [6], "G08": [7], "G09": [8],
    "G10": [9], "G11": [10], "G12": [11], "G13": [12], "G14": [13],
    "G15": [14], "G16": [15], "G17": [16], "G18": [17], "G19": [18],
    "G20": [19], "G21": [20], "G22": [21, 51], "G23": [22, 81],
    "G24": [23, 80], "G25": [24],
    "G26": [25, 26, 27, 28, 52, 77, 78, 79, 83, 84, 88, 89],
    "G27": [29, 30, 31, 34, 53, 86],
    "G28": [32, 33, 54, 55, 87],
    "G29": [35, 91], "G30": [36, 37, 58, 92],
    "G31": [38], "G32": [39], "G33": [40, 42], "G34": [41],
    "G35": [44, 45, 74],
    "G36": [46, 47, 48, 49, 50, 66, 67],
    "G37": [56], "G38": [57], "G39": [60, 61, 73],
    "G40": [62, 70], "G41": [63, 69], "G42": [64], "G43": [65],
    "G44": [68], "G45": [71], "G46": [72], "G47": [75],
    "G48": [82, 85, 90],
}


def index_of(name: str, order: dict[str, int]) -> int:
    return order[name]


def main() -> int:
    rows = list(csv.DictReader(MAPPING.open(encoding="utf-8", newline="")))
    order = {row["original_name"].rsplit(".", 1)[0]: index for index, row in enumerate(rows)}
    # 有些扩展名大小写不同，使用 sample_id 的稳定顺序
    order = {row["sample_id"]: index for index, row in enumerate(rows)}
    groups = {}
    for group, indices in GROUPS_BY_INDEX.items():
        for index in indices:
            if index >= len(rows):
                raise SystemExit(f"分组索引超出范围: {group} {index}")
            groups[rows[index]["sample_id"]] = f"PT-INBOX-{group}"
    # 未列出的样本各自独立，避免误合并
    for index, row in enumerate(rows):
        groups.setdefault(row["sample_id"], f"PT-INBOX-X{index + 1:03d}")

    # 选择每组最清晰的一张作为训练代表
    sharpness: dict[str, float] = {}
    for row in rows:
        image = cv2.imread(str(ROOT / "data/raw_samples" / row["file"]), cv2.IMREAD_GRAYSCALE)
        sharpness[row["sample_id"]] = float(cv2.Laplacian(image, cv2.CV_64F).var()) if image is not None else 0.0
    reps = {}
    for group in set(groups.values()):
        members = [sid for sid, value in groups.items() if value == group]
        reps[group] = max(members, key=lambda sid: sharpness.get(sid, 0.0))

    with GROUPS.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "original_name", "slide_group", "representative", "sharpness"])
        for row in rows:
            sid = row["sample_id"]
            writer.writerow([sid, row["original_name"], groups[sid], int(reps[groups[sid]] == sid), f"{sharpness[sid]:.2f}"])

    # 更新 sample_manifest 的 doc_page_id
    manifest_rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8-sig", newline="")))
    by_id = {row["sample_id"]: row for row in manifest_rows}
    for sid, group in groups.items():
        if sid in by_id:
            by_id[sid]["doc_page_id"] = group
    with MANIFEST.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FIELDS), lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(manifest_rows)

    # 更新 split_v4：移除旧的 93 个单图分组，加入 48 个幻灯片分组
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    groups_split = {name: [g for g in pages if not re.match(r"PT-INBOX-(?!G)", g)] for name, pages in split["groups"].items()}
    groups_split["train"].extend(sorted(set(groups.values())))
    page_to_split = {page: name for name, pages in groups_split.items() for page in pages}
    excluded = {row["sample_id"] for row in csv.DictReader((ROOT / "data/manifests/exclusions.csv").open(encoding="utf-8-sig"))}
    counts = Counter()
    for row in manifest_rows:
        if row["sample_id"] in excluded or not row["label"]:
            continue
        split_name = page_to_split.get(row["doc_page_id"])
        if split_name:
            counts[split_name] += 1
    split["groups"] = groups_split
    split["counts"] = {name: int(counts.get(name, 0)) for name in ("train", "val", "test")}
    split["manifest_sha256"] = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    split["note"] = "2026-11-27 新增 93 张 PPT 样本，按 48 张幻灯片聚合后只加入 train；val/test 与 v3 一致"
    SPLIT.write_text(json.dumps(split, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"组数 {len(set(groups.values()))}，代表 {len(reps)}；counts={split['counts']}")
    print(f"代表样本列表写入 {GROUPS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
