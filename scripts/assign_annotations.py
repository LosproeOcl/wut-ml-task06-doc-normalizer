"""把训练集四角/标签标注任务均衡分配给组员。

规则：按内容类别分别轮转，优先选择该类别已分配数量最少的成员；
同一文档页尽量分给同一人，避免上下文被拆散。
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402

MEMBERS = ("余青阳", "张毅卓", "任万东", "王康琦", "蒋翔恒", "张艺萧", "孔泽宇", "李念")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, default=ROOT / "data/splits/split_v3.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data/annotations/assignees.csv")
    args = parser.parse_args()

    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    assignment = assign_samples(load_split(args.split), samples)
    train = [sample for sample in samples if assignment[sample.sample_id] == "train"]

    # 按文档页聚合，保证同页样本归同一人。
    pages: dict[str, list] = defaultdict(list)
    for sample in train:
        pages[sample.doc_page_id].append(sample)

    counts = {member: {"text": 0, "formula": 0} for member in MEMBERS}
    rows = []
    for page_id in sorted(pages):
        page = sorted(pages[page_id], key=lambda item: item.sample_id)
        content = page[0].content_label or "text"
        member = min(
            MEMBERS,
            key=lambda name: (counts[name][content], sum(counts[name].values()), MEMBERS.index(name)),
        )
        for sample in page:
            rows.append(
                {
                    "sample_id": sample.sample_id,
                    "assignee": member,
                    "label": sample.content_label or "",
                    "doc_page_id": page_id,
                }
            )
            counts[member][content] += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("sample_id", "assignee", "label", "doc_page_id")
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"assigned {len(rows)} training samples to {len(MEMBERS)} members")
    for member in MEMBERS:
        total = sum(counts[member].values())
        print(f"  {member}: {total} (text={counts[member]['text']}, formula={counts[member]['formula']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
