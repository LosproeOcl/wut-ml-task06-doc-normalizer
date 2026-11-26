"""基于既有冻结划分重建新版本。

用途：在不改变既有分组归属的前提下，剔除失效分组、重算样本计数与清单哈希。
契约见 docs/03-架构设计.md 第 6.2 节与 data/splits/README.md。

示例：
    python scripts/rebuild_split.py --base data/splits/split_v1.json \
        --manifest data/manifests/sample_manifest.csv \
        --exclusions data/manifests/exclusions.csv \
        --version v2 --drop-group PT-012 \
        --out data/splits/split_v2.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def load_qualified(manifest: Path, exclusions: Path) -> list[dict[str, str]]:
    excluded = {
        row["sample_id"]
        for row in csv.DictReader(exclusions.open(encoding="utf-8-sig", newline=""))
    }
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        return [row for row in csv.DictReader(stream) if row["sample_id"] not in excluded]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--drop-group", action="append", default=[])
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    base = json.loads(args.base.read_text(encoding="utf-8"))
    groups = {name: [g for g in gs if g not in set(args.drop_group)]
              for name, gs in base["groups"].items()}
    duplicates = [g for g, n in Counter(g for gs in groups.values() for g in gs).items() if n > 1]
    if duplicates:
        raise SystemExit(f"分组重复: {duplicates}")

    samples = load_qualified(args.manifest, args.exclusions)
    group_to_set = {g: name for name, gs in groups.items() for g in gs}
    unknown = sorted({s["doc_page_id"] for s in samples} - set(group_to_set))
    if unknown:
        raise SystemExit(f"合格样本存在未登记分组: {unknown}")

    counts = Counter(group_to_set[s["doc_page_id"]] for s in samples)
    doc = {
        "version": args.version,
        "seed": base["seed"],
        "group_key": base["group_key"],
        "ratio": base["ratio"],
        "groups": groups,
        "counts": {name: counts.get(name, 0) for name in ("train", "val", "test")},
        "frozen_at": "2026-11-26",
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "excluded_samples": sum(
            1 for _ in csv.DictReader(args.exclusions.open(encoding="utf-8-sig", newline=""))
        ),
    }
    if args.note:
        doc["note"] = args.note
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(
        f"{args.out}: {doc['version']} "
        f"train={doc['counts']['train']} val={doc['counts']['val']} "
        f"test={doc['counts']['test']} excluded={doc['excluded_samples']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
