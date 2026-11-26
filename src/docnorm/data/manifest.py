"""样本清单解析与校验。

字段契约见 docs/03-架构设计.md 第 6.1 节与 data/manifests/README.md。
评估标签映射（内容二分类）见 ADR-0008。
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

LABEL_TO_CONTENT = {
    "ppt_text": "text",
    "paper_text": "text",
    "ppt_formula": "formula",
    "paper_formula": "formula",
}
SCENES = {"classroom", "corridor", "dorm", "outdoor"}
LIGHTINGS = {"natural", "ceiling", "side_lamp", "backlight"}
REQUIRED = (
    "sample_id", "file", "doc_page_id", "shooter", "device", "scene",
    "angle_deg", "lighting", "resolution", "shot_at",
    "privacy_masked", "privacy_regions",
)
FIELDS = (
    "sample_id", "file", "label", "doc_page_id", "shooter", "device", "scene",
    "angle_deg", "lighting", "resolution", "shot_at", "notes",
    "privacy_masked", "privacy_regions", "release_file",
)


class ManifestError(ValueError):
    """清单不符合数据契约。"""


@dataclass(frozen=True)
class Sample:
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
    def content_label(self) -> str | None:
        """归档标签映射为内容二分类标签；存疑空标签返回 None。"""
        return LABEL_TO_CONTENT.get(self.label)


def _parse_bool(value: str, row_no: int) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ManifestError(f"第 {row_no} 行 privacy_masked 取值非法: {value!r}")


def load_manifest(
    path: Path, exclusions_path: Path | None = None
) -> list[Sample]:
    """读取并校验样本清单，可选按排除表过滤。

    Args:
        path: 清单 CSV 路径。
        exclusions_path: 排除表 CSV（sample_id,reason），见决定 D-01。

    Returns:
        通过校验且未被排除的样本列表，保持清单行序。

    Raises:
        ManifestError: 字段缺失、取值非法、标识重复或排除表引用未知样本。
    """
    path = Path(path)
    samples: list[Sample] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(FIELDS):
            raise ManifestError(f"表头与契约不一致: {reader.fieldnames}")
        for row_no, row in enumerate(reader, start=2):
            for field in REQUIRED:
                if not (row.get(field) or "").strip():
                    raise ManifestError(f"第 {row_no} 行必填字段为空: {field}")
            sid = row["sample_id"]
            if sid in seen:
                raise ManifestError(f"第 {row_no} 行 sample_id 重复: {sid}")
            seen.add(sid)
            if row["scene"] not in SCENES:
                raise ManifestError(f"第 {row_no} 行 scene 取值非法: {row['scene']}")
            if row["lighting"] not in LIGHTINGS:
                raise ManifestError(f"第 {row_no} 行 lighting 取值非法: {row['lighting']}")
            try:
                angle = int(row["angle_deg"])
            except ValueError as exc:
                raise ManifestError(f"第 {row_no} 行 angle_deg 非整数") from exc
            if not 0 <= angle <= 90:
                raise ManifestError(f"第 {row_no} 行 angle_deg 超出 0 至 90: {angle}")
            if row["label"] and row["label"] not in LABEL_TO_CONTENT and row["label"] != "99_unlabeled":
                raise ManifestError(f"第 {row_no} 行 label 取值非法: {row['label']}")
            samples.append(
                Sample(
                    sample_id=sid,
                    file=row["file"],
                    label=row["label"],
                    doc_page_id=row["doc_page_id"],
                    shooter=row["shooter"],
                    device=row["device"],
                    scene=row["scene"],
                    angle_deg=angle,
                    lighting=row["lighting"],
                    resolution=row["resolution"],
                    shot_at=row["shot_at"],
                    notes=row.get("notes") or "",
                    privacy_masked=_parse_bool(row["privacy_masked"], row_no),
                    privacy_regions=int(row["privacy_regions"]),
                    release_file=row.get("release_file") or "",
                )
            )
    if exclusions_path is not None:
        with Path(exclusions_path).open(encoding="utf-8-sig", newline="") as stream:
            excluded = {r["sample_id"] for r in csv.DictReader(stream)}
        unknown = excluded - seen
        if unknown:
            raise ManifestError(f"排除表引用未知样本: {sorted(unknown)}")
        samples = [s for s in samples if s.sample_id not in excluded]
    return samples