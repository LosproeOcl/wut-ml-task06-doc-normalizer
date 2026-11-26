"""把训练集标注任务均衡分配给组员。

已有四角标注的样本锁定给其标注人（仅当标注人在成员名单内），
其余样本按文档页整体分配，优先选择当前总数最少的成员。
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402

MEMBERS = ("余青阳", "张毅卓", "任万东", "王康琦", "蒋翔恒", "张艺萧", "孔泽宇", "李念")


def load_locked(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    locked = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            annotator = (row.get("annotator") or "").strip()
            if annotator in MEMBERS:
                locked[row["sample_id"]] = annotator
    return locked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, default=ROOT / "data/splits/split_v3.json")
    parser.add_argument("--corners", type=Path, default=ROOT / "data/annotations/manual_corners.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "data/annotations/assignees.csv")
    args = parser.parse_args()

    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = assign_samples(load_split(args.split), samples)
    train = [sample for sample in samples if split[sample.sample_id] == "train"]
    locked = load_locked(args.corners)
    counts = Counter(locked.values())

    pages: dict[str, list] = defaultdict(list)
    for sample in train:
        pages[sample.doc_page_id].append(sample)

    assignment: dict[str, str] = {}
    for page_id in sorted(pages):
        page = sorted(pages[page_id], key=lambda item: item.sample_id)
        page_locked = {locked[s.sample_id] for s in page if s.sample_id in locked}
        member = next(iter(page_locked)) if page_locked else min(
            MEMBERS, key=lambda name: (counts[name], MEMBERS.index(name))
        )
        for sample in page:
            assignment[sample.sample_id] = locked.get(sample.sample_id, member)
            if sample.sample_id not in locked:
                counts[member] += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("sample_id", "assignee", "label", "doc_page_id")
        )
        writer.writeheader()
        for sample in sorted(train, key=lambda item: (item.doc_page_id, item.sample_id)):
            writer.writerow(
                {
                    "sample_id": sample.sample_id,
                    "assignee": assignment[sample.sample_id],
                    "label": sample.content_label or "",
                    "doc_page_id": sample.doc_page_id,
                }
            )

    print(f"assigned {len(train)} training samples, locked {len(locked)}")
    for member in MEMBERS:
        print(f"  {member}: {counts[member]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
