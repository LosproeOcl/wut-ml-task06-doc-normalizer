"""样本清单的解析、校验与索引。

样本清单是样本的唯一可信来源，字段定义见 ``docs/03-架构设计.md`` 第 6.1 节。
本模块只做解析与校验，不修改清单，也不访问图像文件。

内容二分类（文字/公式）的评估口径见 ``docs/adr/0008``；采集配额见
``docs/04-数据采集与标注规范.md`` 第 1 节。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 归档标签（四格）到内容二分类的映射，见 ADR-0008。
LABEL_TO_CONTENT = {
    "ppt_text": "text",
    "paper_text": "text",
    "ppt_formula": "formula",
    "paper_formula": "formula",
}
ARCHIVE_LABELS = frozenset(LABEL_TO_CONTENT)
# 存疑样本的占位标签（待数据负责人裁定），见 data/manifests/待填清单使用说明.md。
UNLABELED_LABEL = "99_unlabeled"
VALID_LABELS = ARCHIVE_LABELS | {UNLABELED_LABEL}
SCENES = frozenset({"classroom", "corridor", "dorm", "outdoor"})
LIGHTINGS = frozenset({"natural", "ceiling", "side_lamp", "backlight"})

# 清单列顺序（docs/03 第 6.1 节）。
MANIFEST_COLUMNS = [
    "sample_id",
    "file",
    "label",
    "doc_page_id",
    "shooter",
    "device",
    "scene",
    "angle_deg",
    "lighting",
    "resolution",
    "shot_at",
    "notes",
    "privacy_masked",
    "privacy_regions",
    "release_file",
]

# 数据负责人裁定排除样本时在 notes 中写入的标记。
EXCLUDE_MARKER = "排除"

# 内容二分类配额约束（docs/04 第 1 节）。
CONTENT_MIN_COUNT = 80  # 任一类不少于 80 张
CONTENT_RATIO_RANGE = (0.4, 0.6)  # 每类占比 40%–60%
CARRIER_PAPER_MIN_RATIO = 0.25  # 纸质与板书合计不少于 25%

# 同一文档页的拍摄角度上限（docs/04 第 7 节质检清单）。
MAX_VIEWS_PER_PAGE = 6

_RESOLUTION_RE = re.compile(r"^(\d+)x(\d+)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class ManifestRow:
    """样本清单中的一行。"""

    sample_id: str
    file: str
    label: str
    doc_page_id: str
    shooter: str
    device: str
    scene: str
    angle_deg: int
    lighting: str
    resolution: str
    shot_at: str
    notes: str
    privacy_masked: bool
    privacy_regions: int
    release_file: str

    @property
    def content_class(self) -> Optional[str]:
        """内容二分类标签（``text`` / ``formula``）；排除样本返回 None。"""
        return LABEL_TO_CONTENT.get(self.label)

    @property
    def carrier(self) -> Optional[str]:
        """载体标签（``ppt`` / ``paper``）；非归档标签返回 None。"""
        if self.label not in ARCHIVE_LABELS:
            return None
        return "ppt" if self.label.startswith("ppt") else "paper"

    @property
    def is_excluded(self) -> bool:
        """是否不计入训练与评估集。

        判定规则：归档标签为空或为 ``99_unlabeled``，或 notes 中含数据负责人
        写入的排除标记。
        """
        return (
            not self.label
            or self.label == UNLABELED_LABEL
            or EXCLUDE_MARKER in self.notes
        )


@dataclass
class ManifestReport:
    """清单校验结果汇总。"""

    n_rows: int = 0
    n_included: int = 0
    n_excluded: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    content_counts: dict[str, int] = field(default_factory=dict)
    carrier_counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class Manifest:
    """样本清单及其索引。"""

    rows: list[ManifestRow]

    _by_sample_id: dict[str, ManifestRow] = field(init=False, repr=False)
    _by_page_id: dict[str, list[ManifestRow]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._by_sample_id = {row.sample_id: row for row in self.rows}
        self._by_page_id = {}
        for row in self.rows:
            if row.doc_page_id:
                self._by_page_id.setdefault(row.doc_page_id, []).append(row)

    def by_sample_id(self, sample_id: str) -> Optional[ManifestRow]:
        return self._by_sample_id.get(sample_id)

    def by_page_id(self, page_id: str) -> list[ManifestRow]:
        return list(self._by_page_id.get(page_id, []))

    def page_ids(self) -> list[str]:
        return list(self._by_page_id)


def _row_from_record(record: dict) -> ManifestRow:
    """把 pandas 一行记录转换为 ManifestRow，做基础类型转换。"""
    def _to_int(value: str) -> int:
        value = value.strip()
        return int(value) if value else 0

    def _to_bool(value: str) -> bool:
        return str(value).strip().lower() == "true"

    return ManifestRow(
        sample_id=str(record.get("sample_id", "")).strip(),
        file=str(record.get("file", "")).strip(),
        label=str(record.get("label", "")).strip(),
        doc_page_id=str(record.get("doc_page_id", "")).strip(),
        shooter=str(record.get("shooter", "")).strip(),
        device=str(record.get("device", "")).strip(),
        scene=str(record.get("scene", "")).strip(),
        angle_deg=_to_int(record.get("angle_deg", "")),
        lighting=str(record.get("lighting", "")).strip(),
        resolution=str(record.get("resolution", "")).strip(),
        shot_at=str(record.get("shot_at", "")).strip(),
        notes=str(record.get("notes", "")).strip(),
        privacy_masked=_to_bool(record.get("privacy_masked", "")),
        privacy_regions=_to_int(record.get("privacy_regions", "")),
        release_file=str(record.get("release_file", "")).strip(),
    )


def parse_manifest(path: str | Path) -> Manifest:
    """读取样本清单 CSV 并构造 :class:`Manifest`。"""
    df = pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")
    missing = [c for c in MANIFEST_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"清单缺少字段：{', '.join(missing)}")
    rows = [_row_from_record(rec) for rec in df.to_dict("records")]
    return Manifest(rows)


def validate(manifest: Manifest) -> ManifestReport:
    """校验清单，返回错误（阻断）与警告（提示）列表。"""
    report = ManifestReport(n_rows=len(manifest.rows))
    included = [r for r in manifest.rows if not r.is_excluded]
    report.n_excluded = len(manifest.rows) - len(included)
    report.n_included = len(included)

    # 1. sample_id 唯一性
    seen: dict[str, int] = {}
    for row in manifest.rows:
        seen[row.sample_id] = seen.get(row.sample_id, 0) + 1
    for sid, count in seen.items():
        if count > 1:
            report.errors.append(f"sample_id 重复：{sid} 出现 {count} 次")
    if "" in seen:
        report.errors.append("存在空 sample_id")

    # 2. 逐行字段校验（仅针对纳入评估的样本）
    for row in manifest.rows:
        tag = f"[{row.sample_id}]"
        if row.label and row.label not in VALID_LABELS:
            report.errors.append(f"{tag} 非法的 label：{row.label!r}")
        if row.label == UNLABELED_LABEL:
            report.warnings.append(f"{tag} 标签为 99_unlabeled，待数据负责人裁定")
        if not row.is_excluded:
            if not row.doc_page_id:
                report.errors.append(
                    f"{tag} 纳入评估但 doc_page_id 为空（划分会泄漏）"
                )
            if row.scene not in SCENES:
                report.errors.append(f"{tag} 非法的 scene：{row.scene!r}")
            if row.lighting not in LIGHTINGS:
                report.errors.append(f"{tag} 非法的 lighting：{row.lighting!r}")
            if not 0 <= row.angle_deg <= 90:
                report.errors.append(
                    f"{tag} angle_deg 越界（0–90）：{row.angle_deg}"
                )
        if row.resolution and not _RESOLUTION_RE.match(row.resolution):
            report.errors.append(f"{tag} 非法的 resolution：{row.resolution!r}")
        if row.shot_at and not _DATE_RE.match(row.shot_at):
            report.warnings.append(f"{tag} shot_at 非 YYYY-MM-DD：{row.shot_at!r}")
        if row.privacy_regions < 0:
            report.errors.append(f"{tag} privacy_regions 为负：{row.privacy_regions}")
        if row.privacy_masked and not row.release_file:
            report.warnings.append(f"{tag} 已打码但缺少 release_file")
        if not row.privacy_masked and row.release_file:
            report.warnings.append(f"{tag} 有 release_file 但 privacy_masked 为 false")

    # 3. 同一文档页标注一致性（内容二分类应唯一）
    for page_id, page_rows in manifest._by_page_id.items():
        classes = {
            r.content_class
            for r in page_rows
            if not r.is_excluded and r.content_class
        }
        if len(classes) > 1:
            report.warnings.append(
                f"doc_page_id={page_id} 跨越多个内容类别：{sorted(classes)}"
            )
        if len(page_rows) > MAX_VIEWS_PER_PAGE:
            report.warnings.append(
                f"doc_page_id={page_id} 有 {len(page_rows)} 个角度，超过 "
                f"{MAX_VIEWS_PER_PAGE} 个上限"
            )

    # 4. 类别分布与配额（docs/04 第 1 节）
    report.content_counts = {cls: 0 for cls in ("text", "formula")}
    report.carrier_counts = {"ppt": 0, "paper": 0}
    for row in included:
        if row.content_class:
            report.content_counts[row.content_class] += 1
        if row.carrier:
            report.carrier_counts[row.carrier] += 1

    n = sum(report.content_counts.values())
    if n:
        for cls in ("text", "formula"):
            cnt = report.content_counts[cls]
            ratio = cnt / n
            if cnt < CONTENT_MIN_COUNT:
                report.warnings.append(
                    f"内容类别 {cls} 仅 {cnt} 张，低于 {CONTENT_MIN_COUNT} 下限"
                )
            if not (CONTENT_RATIO_RANGE[0] <= ratio <= CONTENT_RATIO_RANGE[1]):
                report.warnings.append(
                    f"内容类别 {cls} 占比 {ratio:.1%}，超出 40%–60% 区间"
                )
        paper = report.carrier_counts["paper"]
        if paper / n < CARRIER_PAPER_MIN_RATIO:
            report.warnings.append(
                f"纸质与板书合计占比 {paper / n:.1%}，低于 25% 下限"
            )

    return report
