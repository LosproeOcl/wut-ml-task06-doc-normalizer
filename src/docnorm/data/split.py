"""冻结划分的加载与校验。

契约见 docs/03-架构设计.md 第 6.2 节与 data/splits/README.md。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol


class SplitError(ValueError):
    """划分文件不符合契约或与清单脱节。"""


@dataclass(frozen=True)
class Split:
    version: str
    seed: int
    group_key: str
    groups: dict[str, list[str]]
    counts: dict[str, int]
    frozen_at: str
    manifest_sha256: str


class HasGroup(Protocol):
    sample_id: str
    doc_page_id: str


def load_split(path: Path) -> Split:
    """读取划分文件并校验三个集合的分组互斥。

    Raises:
        SplitError: 同一分组出现在多个集合。
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = {k: list(v) for k, v in doc["groups"].items()}
    seen: dict[str, str] = {}
    for set_name, gs in groups.items():
        for g in gs:
            if g in seen:
                raise SplitError(f"分组 {g} 同时出现在 {seen[g]} 与 {set_name}")
            seen[g] = set_name
    return Split(
        version=doc["version"],
        seed=doc["seed"],
        group_key=doc["group_key"],
        groups=groups,
        counts=doc["counts"],
        frozen_at=doc["frozen_at"],
        manifest_sha256=doc["manifest_sha256"],
    )


def check_manifest_hash(split: Split, manifest_path: Path) -> bool:
    """按原始字节校验清单哈希，防止清单改动后沿用旧划分。

    Raises:
        SplitError: 哈希不一致。
    """
    actual = hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()
    if actual != split.manifest_sha256:
        raise SplitError("manifest_sha256 与清单文件不一致，评估终止")
    return True


def assign_samples(split: Split, samples: Iterable[HasGroup]) -> dict[str, str]:
    """按分组键把样本映射到 train/val/test。

    Raises:
        SplitError: 样本分组不在冻结划分中。
    """
    group_to_set = {g: s for s, gs in split.groups.items() for g in gs}
    mapping: dict[str, str] = {}
    for sample in samples:
        group = sample.doc_page_id
        if group not in group_to_set:
            raise SplitError(f"样本 {sample.sample_id} 的分组 {group} 不在冻结划分中")
        mapping[sample.sample_id] = group_to_set[group]
    return mapping