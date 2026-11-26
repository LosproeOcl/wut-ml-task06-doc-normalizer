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

    def load(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        labels: dict[str, str] = {}
        with self.path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                sample_id = (row.get("sample_id") or "").strip()
                label = (row.get("label") or "").strip()
                if not sample_id:
                    continue
                if label not in LABELS:
                    raise AnnotationError(f"标注标签非法: {row}")
                labels[sample_id] = label
        return labels

    def save(self, labels: dict[str, str], annotator: str = "unknown") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            for sample_id in sorted(labels):
                writer.writerow([sample_id, labels[sample_id], annotator, timestamp])
        temporary.replace(self.path)

    def set(self, sample_id: str, label: str, annotator: str = "unknown") -> dict[str, str]:
        if label not in LABELS:
            raise AnnotationError(f"标签必须为 {LABELS} 之一: {label}")
        labels = self.load()
        labels[sample_id] = label
        self.save(labels, annotator=annotator)
        return labels


CORNER_FIELDS = ("sample_id", "points", "annotator", "updated_at")


def scale_points(
    points: list[list[float]],
    original_size: tuple[int, int],
    image_shape: tuple[int, ...],
) -> list[list[float]]:
    """把原图像素坐标映射到缩放后的图像坐标。"""
    original_width, original_height = original_size
    target_height, target_width = image_shape[:2]
    scale_x = target_width / original_width
    scale_y = target_height / original_height
    return [[float(x) * scale_x, float(y) * scale_y] for x, y in points]


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

    def load(self) -> dict[str, list[list[float]]]:
        if not self.path.is_file():
            return {}
        import json

        corners: dict[str, list[list[float]]] = {}
        with self.path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                sample_id = (row.get("sample_id") or "").strip()
                if not sample_id:
                    continue
                try:
                    points = json.loads(row.get("points") or "[]")
                except ValueError as exc:
                    raise AnnotationError(f"四角 JSON 非法: {row}") from exc
                corners[sample_id] = self._validate(points)
        return corners

    def save(
        self, corners: dict[str, list[list[float]]], annotator: str = "unknown"
    ) -> None:
        import json

        self.path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(CORNER_FIELDS)
            for sample_id in sorted(corners):
                writer.writerow(
                    [
                        sample_id,
                        json.dumps(self._validate(corners[sample_id]), separators=(",", ":")),
                        annotator,
                        timestamp,
                    ]
                )
        temporary.replace(self.path)

    def set(
        self, sample_id: str, points: object, annotator: str = "unknown"
    ) -> dict[str, list[list[float]]]:
        corners = self.load()
        corners[sample_id] = self._validate(points)
        self.save(corners, annotator=annotator)
        return corners

