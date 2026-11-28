"""生成按 doc_page_id 分组、按载体×内容分层的 5 折交叉验证划分。

每折 train=4/5 训练组，val=1/5；原验证组放入 holdout，原测试组保持 test。
同时生成纸质分支的折清单（只保留自采纸质折内样本 + 外部训练样本）。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import load_split, assign_samples  # noqa: E402

SPLIT = ROOT / "data/splits/split_v5.json"
MANIFEST = ROOT / "data/manifests/sample_manifest_v5.csv"
OUT = ROOT / "data/splits/cv"
PAPER_MANIFEST = ROOT / "data/manifests/paper_content_v5.csv"
PAPER_OUT = ROOT / "data/manifests/cv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--split", type=Path, default=SPLIT)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--paper-manifest", type=Path, default=PAPER_MANIFEST)
    parser.add_argument("--paper-out", type=Path, default=PAPER_OUT)
    return parser.parse_args()


def cell(sample) -> str:
    return f"{(sample.label or '').split('_')[0]}_{sample.content_label}"


def main() -> int:
    args = parse_args()
    samples = load_manifest(
        args.manifest,
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(args.split)
    assignment = assign_samples(split, samples)
    by_group: dict[str, list] = defaultdict(list)
    for sample in samples:
        if assignment[sample.sample_id] == "train":
            by_group[sample.doc_page_id].append(sample)
    groups = sorted(by_group)
    labels = [Counter(cell(s) for s in by_group[g]).most_common(1)[0][0] for g in groups]
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    folds = list(splitter.split(groups, labels, groups=groups))
    args.out.mkdir(parents=True, exist_ok=True)
    args.paper_out.mkdir(parents=True, exist_ok=True)

    original_val = list(split.groups["val"])
    original_test = list(split.groups["test"])
    for fold_index, (train_idx, val_idx) in enumerate(folds, 1):
        train_groups = [groups[i] for i in train_idx]
        val_groups = [groups[i] for i in val_idx]
        page_to_split = {}
        for g in train_groups:
            page_to_split[g] = "train"
        for g in val_groups:
            page_to_split[g] = "val"
        for g in original_val:
            page_to_split[g] = "holdout"
        for g in original_test:
            page_to_split[g] = "test"
        counts = Counter()
        for sample in samples:
            name = page_to_split.get(sample.doc_page_id)
            if name:
                counts[name] += 1
        payload = {
            "version": f"cv-fold-{fold_index}",
            "seed": 42,
            "group_key": "doc_page_id",
            "ratio": {"train": 0.8, "val": 0.2},
            "groups": {
                "train": train_groups,
                "val": val_groups,
                "holdout": original_val,
                "test": original_test,
            },
            "counts": {
                "train": counts["train"],
                "val": counts["val"],
                "test": counts["test"],
                "holdout": counts["holdout"],
            },
            "frozen_at": str(date.today()),
            "manifest_sha256": split.manifest_sha256,
            "note": f"5 折分组 CV，第 {fold_index} 折；原验证集 holdout，测试集不动",
        }
        (args.out / f"fold_{fold_index}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        val_cells = Counter(cell(s) for g in val_groups for s in by_group[g])
        print(f"fold {fold_index}: train_groups={len(train_groups)} val_groups={len(val_groups)} val_cells={dict(val_cells)}")

        # 纸质分支折清单：外部训练样本全部保留；自采纸质按折分组；原 val 排除
        paper_rows = list(csv.DictReader(args.paper_manifest.open(encoding="utf-8")))
        manifest_by_id = {s.sample_id: s for s in samples}
        fold_rows = []
        for row in paper_rows:
            source = row["source"]
            if source != "self-paper":
                if row["split"] == "train":
                    fold_rows.append(row)
                continue
            sample = manifest_by_id.get(row["sample_id"])
            if sample is None:
                continue
            name = page_to_split.get(sample.doc_page_id)
            if name not in {"train", "val"}:
                continue
            item = dict(row)
            item["split"] = name
            fold_rows.append(item)
        with (args.paper_out / f"paper_fold_{fold_index}.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=list(paper_rows[0].keys()))
            writer.writeheader()
            writer.writerows(fold_rows)
        print("  paper rows", Counter(r["split"] for r in fold_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
