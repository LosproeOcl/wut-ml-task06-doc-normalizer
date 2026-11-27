"""把新增实拍样本的四角标注任务平均分配给指定成员。

只处理训练集、指定页面前缀、尚未分配且尚无四角记录的样本；
先按公式/文字分组，再在组内轮转分配，保证每人总量与类别量尽量均衡。
已有记录与既有分配保持不变。

用法：
    python scripts/assign_inbox_corners.py --dry-run
    python scripts/assign_inbox_corners.py
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

MEMBERS = ("任万东", "王康琦", "余青阳")
FIELDS = ("sample_id", "assignee", "label", "doc_page_id")


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="PT-INBOX", help="只分配该页面前缀的新样本")
    parser.add_argument("--members", nargs="+", default=list(MEMBERS))
    parser.add_argument(
        "--assignees", type=Path, default=ROOT / "data/annotations/assignees.csv"
    )
    parser.add_argument(
        "--corners", type=Path, default=ROOT / "data/annotations/manual_corners.csv"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    members = list(dict.fromkeys(args.members))
    if not members:
        raise SystemExit("至少需要一个成员")

    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = assign_samples(load_split(ROOT / "data/splits/split_v4.json"), samples)
    existing = read_rows(args.assignees)
    assigned = {(row.get("sample_id") or "").strip() for row in existing}
    annotated = {
        (row.get("sample_id") or "").strip() for row in read_rows(args.corners)
    }

    candidates = [
        sample
        for sample in samples
        if split.get(sample.sample_id) == "train"
        and sample.doc_page_id.startswith(args.prefix)
        and sample.sample_id not in assigned
        and sample.sample_id not in annotated
    ]
    if not candidates:
        print("没有需要分配的新样本。")
        return 0

    by_label: dict[str, list] = defaultdict(list)
    for sample in candidates:
        by_label[sample.content_label or "unknown"].append(sample)

    counts: Counter = Counter()
    label_counts: Counter = Counter()
    assignment: dict[str, str] = {}
    # 公式样本通常更少，先分公式，再分文字，保持类别量均衡。
    for label in sorted(by_label, key=lambda name: (name != "formula", name)):
        items = sorted(
            by_label[label], key=lambda item: (item.doc_page_id, item.sample_id)
        )
        for sample in items:
            member = min(
                members,
                key=lambda name: (
                    label_counts[(name, label)],
                    counts[name],
                    members.index(name),
                ),
            )
            assignment[sample.sample_id] = member
            counts[member] += 1
            label_counts[(member, label)] += 1

    print(f"待分配 {len(candidates)} 张，成员：{'、'.join(members)}")
    for member in members:
        labels = {
            label: label_counts[(member, label)]
            for label in sorted(by_label)
            if label_counts[(member, label)]
        }
        print(f"  {member}: {counts[member]} 张 {labels}")
    if args.dry_run:
        print("预演模式，未写入。")
        return 0

    rows = list(existing)
    for sample in sorted(candidates, key=lambda item: (item.doc_page_id, item.sample_id)):
        rows.append(
            {
                "sample_id": sample.sample_id,
                "assignee": assignment[sample.sample_id],
                "label": sample.content_label or "",
                "doc_page_id": sample.doc_page_id,
            }
        )
    args.assignees.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.assignees.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(args.assignees)
    print(f"写入 {args.assignees}，共 {len(rows)} 行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
