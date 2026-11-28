"""生成 split_v5：外部测试集 + 从 v4 训练集分层留出的自采样本。

设计（2026-11-28）：
- 03-captured-nexus 30 张（全部 paper_text）只进入 test，不参与训练；
- 从 v4 train 按 doc_page_id 分组、按载体×内容分层留出目标 42 张：
  ppt_text 6、ppt_formula 15、paper_text 6、paper_formula 15；
- v4 val 51 张继续保持 val；
- v4 test 53 张并入 train（v4 结果仅作历史，不再用于 v5 模型比较）；
- 生成 data/manifests/sample_manifest_v5.csv 与 data/splits/split_v5.json。

用法：
    python scripts/build_split_v5.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "sample_id", "file", "label", "doc_page_id", "shooter", "device", "scene",
    "angle_deg", "lighting", "resolution", "shot_at", "notes",
    "privacy_masked", "privacy_regions", "release_file",
)
TARGETS = {
    "ppt_text": 6,
    "ppt_formula": 15,
    "paper_text": 6,
    "paper_formula": 15,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", type=Path, default=ROOT / "data/manifests/sample_manifest.csv")
    parser.add_argument("--exclusions", type=Path, default=ROOT / "data/manifests/exclusions.csv")
    parser.add_argument("--external-manifest", type=Path, default=ROOT / "data/manifests/external_nexus_test.csv")
    parser.add_argument("--base-split", type=Path, default=ROOT / "data/splits/split_v4.json")
    parser.add_argument("--manifest-out", type=Path, default=ROOT / "data/manifests/sample_manifest_v5.csv")
    parser.add_argument("--split-out", type=Path, default=ROOT / "data/splits/split_v5.json")
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--frozen-at", default="2026-11-28")
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def choose_groups(
    groups: list[tuple[str, int]], target: int, seed: int
) -> list[str]:
    """从候选组中选一组，使样本数尽量接近 target；同分时优先更多分组。"""
    rng = random.Random(seed)
    shuffled = list(groups)
    rng.shuffle(shuffled)
    max_size = max((size for _, size in shuffled), default=0)
    limit = target + max_size
    dp: dict[int, list[str]] = {0: []}
    for group, size in shuffled:
        for total, chosen in list(dp.items()):
            new_total = total + size
            if new_total > limit:
                continue
            candidate = chosen + [group]
            current = dp.get(new_total)
            if current is None or len(candidate) > len(current):
                dp[new_total] = candidate
    best = min(
        dp,
        key=lambda total: (abs(total - target), -len(dp[total]), total),
    )
    return dp[best]


def main() -> int:
    args = parse_args()
    base_rows = read_rows(args.base_manifest)
    external_rows = read_rows(args.external_manifest)
    excluded = {row["sample_id"] for row in read_rows(args.exclusions)}
    base_ids = {row["sample_id"] for row in base_rows}
    external_ids = {row["sample_id"] for row in external_rows}
    duplicates = base_ids & external_ids
    if duplicates:
        raise SystemExit(f"样本标识重复: {sorted(duplicates)}")

    merged = base_rows + external_rows
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest_out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(merged)

    base_split = json.loads(args.base_split.read_text(encoding="utf-8"))
    self_groups = {
        name: set(groups) for name, groups in base_split["groups"].items()
    }
    by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in merged:
        by_group[row["doc_page_id"]].append(row)

    qualified = [
        row
        for row in merged
        if row["sample_id"] not in excluded
        and row["label"] not in {"", "99_unlabeled"}
    ]
    qualified_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in qualified:
        qualified_by_group[row["doc_page_id"]].append(row)

    external_groups = {
        row["doc_page_id"] for row in external_rows
    }
    if len(external_groups) != len(external_rows):
        raise SystemExit("外部样本 doc_page_id 不唯一")

    train_groups = sorted(self_groups["train"])
    candidates: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for group in train_groups:
        rows = qualified_by_group[group]
        if not rows:
            continue
        label = Counter(row["label"] for row in rows).most_common(1)[0][0]
        if label not in TARGETS:
            continue
        candidates[label].append((group, len(rows)))

    selected: list[str] = []
    for offset, (cell, target) in enumerate(TARGETS.items()):
        chosen = choose_groups(candidates[cell], target, args.seed + offset)
        selected.extend(chosen)
        chosen_samples = sum(len(qualified_by_group[group]) for group in chosen)
        print(f"{cell}: target={target} groups={len(chosen)} samples={chosen_samples}")

    selected_set = set(selected)
    if len(selected_set) != len(selected):
        raise SystemExit("留出分组重复")

    groups = {
        "train": sorted(
            (self_groups["train"] - selected_set) | self_groups["test"]
        ),
        "val": sorted(self_groups["val"]),
        "test": sorted(selected_set | external_groups),
    }
    overlap = (
        (set(groups["train"]) & set(groups["val"]))
        | (set(groups["train"]) & set(groups["test"]))
        | (set(groups["val"]) & set(groups["test"]))
    )
    if overlap:
        raise SystemExit(f"分组跨集合: {sorted(overlap)}")

    covered = set().union(*groups.values())
    unknown = {row["doc_page_id"] for row in qualified} - covered
    if unknown:
        raise SystemExit(f"存在未分配分组: {sorted(unknown)}")

    group_to_set = {
        group: name for name, group_list in groups.items() for group in group_list
    }
    counts = Counter(
        group_to_set[row["doc_page_id"]] for row in qualified
    )
    payload = {
        "version": "v5",
        "seed": args.seed,
        "group_key": "doc_page_id",
        "ratio": base_split["ratio"],
        "groups": groups,
        "counts": {name: counts[name] for name in ("train", "val", "test")},
        "frozen_at": args.frozen_at,
        "manifest": str(args.manifest_out.relative_to(ROOT)),
        "manifest_sha256": hashlib.sha256(args.manifest_out.read_bytes()).hexdigest(),
        "note": (
            "2026-11-28 重建：test=SmartDoc 2015 03-captured-nexus 30 张"
            "（全部 paper_text）+ 从 v4 train 按 doc_page_id 分层留出的自采样本"
            "（ppt_text 6 / ppt_formula 15 / paper_text 6 / paper_formula 15）；"
            "v4 val 保持 val；v4 test 并入 train；外部 30 张只进 test，不参与训练；"
            "v5 全部实验重跑，v4 的 67.92% 仅作历史结果，不与 v5 混用"
        ),
    }
    args.split_out.parent.mkdir(parents=True, exist_ok=True)
    args.split_out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    print(f"\n写入 {args.manifest_out} ({len(merged)} 行，合格 {len(qualified)} 行)")
    print(f"写入 {args.split_out}: {payload['counts']}")
    for name in ("train", "val", "test"):
        rows = [
            row for row in qualified if group_to_set[row["doc_page_id"]] == name
        ]
        print(f"\n== {name} {len(rows)} 张 ==")
        print(" label", dict(Counter(row["label"] for row in rows)))
        print(" carrier", dict(Counter(row["label"].split("_")[0] for row in rows)))
        print(" shooter", dict(Counter(row["shooter"] for row in rows).most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
