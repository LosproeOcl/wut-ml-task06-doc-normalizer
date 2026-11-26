"""训练集人工标签覆盖。

标注结果单独存放，不修改样本清单与冻结划分。仅允许训练集样本写入。
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

LABELS = ("text", "formula")
FIELDS = ("sample_id", "label", "annotator", "updated_at")


class AnnotationError(ValueError):
    """标注记录不合法。"""


def default_annotation_path() -> Path:
    override = os.environ.get("DOCNORM_ANNOTATION_PATH")
    if override:
        return Path(override)
    return Path("data/annotations/manual_labels.csv")


class ManualLabelStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_annotation_path()

    def _load_records(self) -> dict[str, dict[str, str]]:
        if not self.path.is_file():
            return {}
        records: dict[str, dict[str, str]] = {}
        with self.path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                sample_id = (row.get("sample_id") or "").strip()
                label = (row.get("label") or "").strip()
                if not sample_id:
                    continue
                if label not in LABELS:
                    raise AnnotationError(f"标注标签非法: {row}")
                records[sample_id] = {
                    "label": label,
                    "annotator": (row.get("annotator") or "unknown").strip(),
                    "updated_at": (row.get("updated_at") or "").strip(),
                }
        return records

    def _write_records(self, records: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            for sample_id in sorted(records):
                record = records[sample_id]
                writer.writerow(
                    [
                        sample_id,
                        record["label"],
                        record["annotator"],
                        record["updated_at"],
                    ]
                )
        temporary.replace(self.path)

    def load(self) -> dict[str, str]:
        return {sid: record["label"] for sid, record in self._load_records().items()}

    def save(self, labels: dict[str, str], annotator: str = "unknown") -> None:
        """批量写入标签；已有记录保留原标注人和时间。"""
        records = self._load_records()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for sample_id, label in labels.items():
            if label not in LABELS:
                raise AnnotationError(f"标签必须为 {LABELS} 之一: {label}")
            if sample_id in records:
                records[sample_id]["label"] = label
            else:
                records[sample_id] = {
                    "label": label,
                    "annotator": annotator,
                    "updated_at": timestamp,
                }
        self._write_records(records)

    def set(self, sample_id: str, label: str, annotator: str = "unknown") -> dict[str, str]:
        if label not in LABELS:
            raise AnnotationError(f"标签必须为 {LABELS} 之一: {label}")
        records = self._load_records()
        records[sample_id] = {
            "label": label,
            "annotator": annotator,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._write_records(records)
        return {sid: record["label"] for sid, record in records.items()}


CORNER_FIELDS = ("sample_id", "points", "annotator", "updated_at")


def rescale_points(
    points: list[list[float]],
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> list[list[float]]:
    """把坐标从 source_size 映射到 target_size。"""
    source_width, source_height = source_size
    target_width, target_height = target_size
    scale_x = target_width / source_width
    scale_y = target_height / source_height
    return [[float(x) * scale_x, float(y) * scale_y] for x, y in points]


def clamp_points(
    points: list[list[float]], width: int, height: int
) -> list[list[float]]:
    """把坐标限制在图像范围内，避免默认点落在画布外。"""
    return [
        [
            min(max(float(x), 0.0), float(width - 1)),
            min(max(float(y), 0.0), float(height - 1)),
        ]
        for x, y in points
    ]


def scale_points(
    points: list[list[float]],
    original_size: tuple[int, int],
    image_shape: tuple[int, ...],
) -> list[list[float]]:
    """把原图像素坐标映射到缩放后的图像坐标。"""
    target_height, target_width = image_shape[:2]
    return rescale_points(
        points,
        original_size,
        (target_width, target_height),
    )


class ManualCornerStore:
    """训练集四角覆盖，坐标为原图像素，顺序为左上、右上、右下、左下。"""

    def __init__(self, path: Path | None = None) -> None:
        override = os.environ.get("DOCNORM_CORNER_PATH")
        self.path = Path(path) if path is not None else Path(
            override or "data/annotations/manual_corners.csv"
        )

    @staticmethod
    def _validate(points: object) -> list[list[float]]:
        try:
            array = [[float(x), float(y)] for x, y in points]  # type: ignore[union-attr]
        except (TypeError, ValueError) as exc:
            raise AnnotationError(f"四角格式非法: {points!r}") from exc
        if len(array) != 4:
            raise AnnotationError(f"需要 4 个顶点，实际 {len(array)} 个")
        x = [p[0] for p in array]
        y = [p[1] for p in array]
        area = 0.5 * abs(
            sum(x[i] * y[(i + 1) % 4] - y[i] * x[(i + 1) % 4] for i in range(4))
        )
        if area < 1.0:
            raise AnnotationError("四角面积过小")
        return array

    def _load_records(self) -> dict[str, dict[str, object]]:
        if not self.path.is_file():
            return {}
        import json

        records: dict[str, dict[str, object]] = {}
        with self.path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                sample_id = (row.get("sample_id") or "").strip()
                if not sample_id:
                    continue
                try:
                    points = json.loads(row.get("points") or "[]")
                except ValueError as exc:
                    raise AnnotationError(f"四角 JSON 非法: {row}") from exc
                records[sample_id] = {
                    "points": self._validate(points),
                    "annotator": (row.get("annotator") or "unknown").strip(),
                    "updated_at": (row.get("updated_at") or "").strip(),
                }
        return records

    def _write_records(self, records: dict[str, dict[str, object]]) -> None:
        import json

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(CORNER_FIELDS)
            for sample_id in sorted(records):
                record = records[sample_id]
                writer.writerow(
                    [
                        sample_id,
                        json.dumps(
                            self._validate(record["points"]),
                            separators=(",", ":"),
                        ),
                        record["annotator"],
                        record["updated_at"],
                    ]
                )
        temporary.replace(self.path)

    def load(self) -> dict[str, list[list[float]]]:
        return {
            sid: record["points"]  # type: ignore[return-value]
            for sid, record in self._load_records().items()
        }

    def records(self) -> dict[str, dict[str, object]]:
        """返回包含坐标、标注人和更新时间的记录。"""
        return self._load_records()

    def remove(self, sample_id: str) -> bool:
        records = self._load_records()
        if sample_id not in records:
            return False
        del records[sample_id]
        self._write_records(records)
        return True

    def save(
        self, corners: dict[str, list[list[float]]], annotator: str = "unknown"
    ) -> None:
        """批量写入四角；已有记录保留原标注人和时间。"""
        records = self._load_records()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for sample_id, points in corners.items():
            if sample_id in records:
                records[sample_id]["points"] = self._validate(points)
            else:
                records[sample_id] = {
                    "points": self._validate(points),
                    "annotator": annotator,
                    "updated_at": timestamp,
                }
        self._write_records(records)

    def set(
        self, sample_id: str, points: object, annotator: str = "unknown"
    ) -> dict[str, list[list[float]]]:
        records = self._load_records()
        records[sample_id] = {
            "points": self._validate(points),
            "annotator": annotator,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._write_records(records)
        return {
            sid: record["points"]  # type: ignore[return-value]
            for sid, record in records.items()
        }
