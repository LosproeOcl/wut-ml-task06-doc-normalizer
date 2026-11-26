"""按文档页分组划分数据集，并生成、校验划分文件。

划分规则见 ``docs/04-数据采集与标注规范.md`` 第 6 节，文件结构见
``docs/03-架构设计.md`` 第 6.2 节。核心约束是：以 ``doc_page_id`` 为分组键，
同一文档页的多角度样本必须落在同一集合，避免数据泄漏导致指标虚高。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from sklearn.model_selection import StratifiedGroupKFold

from .manifest import Manifest, ManifestRow

logger = logging.getLogger(__name__)

DEFAULT_RATIO = {"train": 0.7, "val": 0.15, "test": 0.15}
DEFAULT_SEED = 42
GROUP_KEY = "doc_page_id"


def sha256_file(path: str | Path) -> str:
    """计算文件的 SHA-256 哈希（十六进制小写）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _grouped_stratified_fold(page_ids, y, groups, n_splits, seed):
    """用 StratifiedGroupKFold 返回第一个 fold 的 (train 索引, test 索引)。"""
    sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return next(iter(sgkf.split(page_ids, y, groups=groups)))


def _collect_pages(manifest: Manifest) -> tuple[dict[str, str], dict[str, set[str]]]:
    """收集纳入评估的样本，按 doc_page_id 归并内容类别与拍摄者。"""
    page_to_class: dict[str, str] = {}
    page_to_shooters: dict[str, set[str]] = defaultdict(set)
    for row in manifest.rows:
        if row.is_excluded or not row.doc_page_id or not row.content_class:
            continue
        page_to_class[row.doc_page_id] = row.content_class
        page_to_shooters[row.doc_page_id].add(row.shooter)
    return page_to_class, page_to_shooters


def make_split(
    manifest: Manifest,
    seed: int = DEFAULT_SEED,
    ratio: Optional[dict[str, float]] = None,
) -> dict:
    """按 ``doc_page_id`` 分组、按内容类别分层，生成训练/验证/测试划分。

    返回结构见 ``docs/03`` 第 6.2 节。``manifest_sha256`` 由调用方在写入前
    基于清单文件路径填充（本函数只拿到已解析的 Manifest 对象）。
    """
    ratio = dict(ratio or DEFAULT_RATIO)
    page_to_class, page_to_shooters = _collect_pages(manifest)
    page_ids = sorted(page_to_class)
    y = [page_to_class[pid] for pid in page_ids]

    if not page_ids:
        raise ValueError("没有可划分的样本（全部被排除或缺少 doc_page_id）")

    # 第一次切出测试集（约 ratio["test"]）。fold 数受每类页面数下限约束。
    min_per_class = min(Counter(y).values())
    n_test = min(max(2, round(1.0 / ratio["test"])), min_per_class)
    train_val_idx, test_idx = _grouped_stratified_fold(
        page_ids, y, page_ids, n_test, seed
    )
    test_pages = [page_ids[i] for i in test_idx]

    # 第二次在 train+val 内切出验证集。
    train_val_pages = [page_ids[i] for i in train_val_idx]
    tv_y = [page_to_class[pid] for pid in train_val_pages]
    val_share = ratio["val"] / (ratio["train"] + ratio["val"])
    min_tv = min(Counter(tv_y).values())
    n_val = min(max(2, round(1.0 / val_share)), min_tv)
    train_idx2, val_idx2 = _grouped_stratified_fold(
        train_val_pages, tv_y, train_val_pages, n_val, seed
    )
    train_pages = [train_val_pages[i] for i in train_idx2]
    val_pages = [train_val_pages[i] for i in val_idx2]

    page_to_split = {}
    for pid in train_pages:
        page_to_split[pid] = "train"
    for pid in val_pages:
        page_to_split[pid] = "val"
    for pid in test_pages:
        page_to_split[pid] = "test"

    counts = {"train": 0, "val": 0, "test": 0}
    for row in manifest.rows:
        split_name = page_to_split.get(row.doc_page_id)
        if split_name and not row.is_excluded:
            counts[split_name] += 1

    return {
        "version": "v1",
        "seed": seed,
        "group_key": GROUP_KEY,
        "ratio": ratio,
        "groups": {
            "train": sorted(train_pages),
            "val": sorted(val_pages),
            "test": sorted(test_pages),
        },
        "counts": counts,
        "frozen_at": date.today().isoformat(),
        "manifest_sha256": None,
        "excluded_samples": sum(1 for r in manifest.rows if r.is_excluded),
        "note": "冻结后不得修改；后续补采只能加入训练集，重建须出 split_v2",
    }


def validate_split(split: dict, manifest: Manifest) -> list[str]:
    """校验划分文件与清单的一致性，返回问题列表。

    重点检查数据泄漏：同一 ``doc_page_id`` 不得出现在多个集合，且所有纳入
    评估的页面都被分配且只被分配一次。
    """
    problems: list[str] = []
    groups = split.get("groups", {})
    page_to_split: dict[str, str] = {}
    for name in ("train", "val", "test"):
        for pid in groups.get(name, []):
            if pid in page_to_split:
                problems.append(f"doc_page_id={pid} 同时出现在多个集合")
            page_to_split[pid] = name

    expected = {
        pid
        for pid, _ in _collect_pages(manifest)[0].items()
    }
    assigned = set(page_to_split)
    missing = expected - assigned
    if missing:
        problems.append(f"{len(missing)} 个页面未分配，如 {sorted(missing)[:5]}")
    extra = assigned - expected
    if extra:
        problems.append(f"{len(extra)} 个页面不在清单中，如 {sorted(extra)[:5]}")

    # 测试集须包含至少两名非主要拍摄者（docs/04 第 6 节第 3 条）。
    page_to_shooters = _collect_pages(manifest)[1]
    test_shooters = {
        s for pid in groups.get("test", []) for s in page_to_shooters.get(pid, set())
    }
    if len(test_shooters) < 2:
        problems.append(f"测试集仅覆盖 {len(test_shooters)} 名拍摄者，少于 2 名")

    return problems


def write_split(split: dict, path: str | Path) -> None:
    """把划分结构写入 JSON 文件（UTF-8、两空格缩进）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(split, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_split(path: str | Path) -> dict:
    """读取划分文件。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)
