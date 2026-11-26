"""网页层业务逻辑：样本索引、处理链路、临时结果与人工标注。"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import yaml

from docnorm.classify.classic import ClassicClassifier
from docnorm.data.annotations import (
    ManualCornerStore,
    ManualLabelStore,
    clamp_points,
    rescale_points,
)
from docnorm.data.loader import load_image
from docnorm.data.manifest import load_manifest
from docnorm.data.split import assign_samples, check_manifest_hash, load_split
from docnorm.enhance.clahe import enhance_document
from docnorm.features.classic import extract_features
from docnorm.rectify.detector import detect_document
from docnorm.rectify.geometry import DocumentQuad, RectifyError
from docnorm.rectify.warp import warp_document

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
RESULT_DIR = ROOT / "web/results"
MODEL_ENV = "DOCNORM_CLASSIC_MODEL"
RESULT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
STAGES = ("original", "quad", "rectified", "enhanced")


class WebError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _annotation_store() -> ManualLabelStore:
    return ManualLabelStore(Path(os.environ.get(
        "DOCNORM_ANNOTATION_PATH", ROOT / "data/annotations/manual_labels.csv"
    )))


def _corner_store() -> ManualCornerStore:
    return ManualCornerStore(Path(os.environ.get(
        "DOCNORM_CORNER_PATH", ROOT / "data/annotations/manual_corners.csv"
    )))


def _assignments() -> dict[str, str]:
    path = ROOT / "data/annotations/assignees.csv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {
            row["sample_id"]: row["assignee"]
            for row in csv.DictReader(stream)
            if row.get("sample_id") and row.get("assignee")
        }


def _members() -> list[str]:
    values = _assignments().values()
    ordered: list[str] = []
    for value in values:
        if value not in ordered:
            ordered.append(value)
    return ordered


def _check_assignment(sample_id: str, annotator: str) -> None:
    assigned = _assignments().get(sample_id)
    if assigned and annotator in set(_members()) and annotator != assigned:
        raise WebError(f"该样本分配给 {assigned}，不能由 {annotator} 标注", status=403)


def _sample_index() -> dict[str, dict]:
    samples = load_manifest(
        ROOT / CONFIG["data"]["manifest"],
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(ROOT / CONFIG["data"]["split"])
    check_manifest_hash(split, ROOT / CONFIG["data"]["manifest"])
    assignment = assign_samples(split, samples)
    index: dict[str, dict] = {}
    for sample in samples:
        index[sample.sample_id] = {
            "sample_id": sample.sample_id,
            "file": sample.file,
            "original_label": sample.content_label,
            "split": assignment[sample.sample_id],
            "carrier": "ppt" if sample.file.startswith(("01_", "02_")) else "paper",
            "resolution": sample.resolution,
        }
    return index


def list_samples(
    *,
    split: str | None = None,
    label: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> dict:
    index = _sample_index()
    overrides = _annotation_store().load()
    items = []
    for sample in index.values():
        current = overrides.get(sample["sample_id"], sample["original_label"])
        if split and sample["split"] != split:
            continue
        if label and current != label:
            continue
        items.append(
            {
                **sample,
                "label": current,
                "annotated": sample["sample_id"] in overrides,
            }
        )
    annotated_first = sorted(
        items,
        key=lambda item: (item["split"] != "train", item["annotated"], item["sample_id"]),
    )
    return {
        "total": len(annotated_first),
        "items": annotated_first[offset: offset + limit],
    }


def get_sample(sample_id: str) -> dict:
    sample = _sample_index().get(sample_id)
    if sample is None:
        raise WebError("样本不存在", status=404)
    return sample


def sample_path(sample_id: str) -> Path:
    sample = get_sample(sample_id)
    return ROOT / CONFIG["data"]["raw_dir"] / sample["file"]


def _result_dir(result_id: str) -> Path:
    if not RESULT_ID_PATTERN.fullmatch(result_id):
        raise WebError("结果标识非法", status=404)
    path = RESULT_DIR / result_id
    if not path.is_dir():
        raise WebError("结果不存在", status=404)
    return path


def _model_path() -> Path | None:
    override = os.environ.get(MODEL_ENV)
    if override and Path(override).is_file():
        return Path(override)
    candidates = sorted(
        (ROOT / "runs").glob("exp-*/svm.joblib"), key=lambda p: p.stat().st_mtime
    )
    return candidates[-1] if candidates else None


_MODEL: ClassicClassifier | None = None


def _classifier() -> ClassicClassifier | None:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    path = _model_path()
    if path is None:
        return None
    _MODEL = ClassicClassifier.load(path)
    return _MODEL


def _classify(array: np.ndarray) -> tuple[str | None, dict[str, float] | None]:
    model = _classifier()
    if model is None:
        return None, None
    features = extract_features(array).reshape(1, -1)
    probabilities = model.predict_proba(features)[0]
    classes = list(model.classes_)
    scores = {name: float(probabilities[classes.index(name)]) for name in classes}
    label = max(scores, key=scores.get)
    return label, scores


def _apply_rectify(array: np.ndarray) -> tuple[np.ndarray, DocumentQuad | None, str]:
    quad = detect_document(
        array,
        canny_low=int(CONFIG["rectify"]["canny_low"]),
        canny_high=int(CONFIG["rectify"]["canny_high"]),
        min_area_ratio=float(CONFIG["rectify"]["min_area_ratio"]),
        max_area_ratio=float(CONFIG["rectify"]["max_area_ratio"]),
    )
    if quad is None:
        return array, None, "rectify_failed"
    return (
        warp_document(
            array,
            quad,
            output_long_edge=int(CONFIG["rectify"]["output_long_edge"]),
        ),
        quad,
        "ok",
    )


def _apply_enhance(array: np.ndarray) -> np.ndarray:
    return enhance_document(
        array,
        clip_limit=float(CONFIG["enhance"]["clahe_clip"]),
        tile_grid_size=int(CONFIG["enhance"]["clahe_grid"]),
        correct_shadows=bool(CONFIG["enhance"]["correct_shadows"]),
        shadow_kernel=int(CONFIG["enhance"]["shadow_kernel"]),
        shadow_strength=float(CONFIG["enhance"]["shadow_strength"]),
        denoise=bool(CONFIG["enhance"]["denoise"]),
    )


def _draw_quad(original: np.ndarray, quad: DocumentQuad | None) -> np.ndarray:
    canvas = original.copy()
    if quad is not None:
        points = quad.points.astype(np.int32)
        cv2.polylines(canvas, [points], True, (0, 0, 255), 3)
        for index, point in enumerate(points):
            cv2.circle(canvas, tuple(point), 6, (0, 255, 255), -1)
            cv2.putText(
                canvas,
                str(index + 1),
                tuple(point + 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
            )
    return canvas


def _save_result(
    *,
    result_id: str,
    original: np.ndarray,
    quad: DocumentQuad | None,
    rectified: np.ndarray,
    enhanced: np.ndarray,
    status: str,
    label: str | None,
    probabilities: dict[str, float] | None,
    runtime_ms: float,
    rectify: bool,
    enhance: bool,
    source: str,
) -> dict:
    directory = RESULT_DIR / result_id
    directory.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(directory / "original.png"), original)
    cv2.imwrite(str(directory / "quad.png"), _draw_quad(original, quad))
    cv2.imwrite(str(directory / "rectified.png"), rectified)
    cv2.imwrite(str(directory / "enhanced.png"), enhanced)
    metadata = {
        "result_id": result_id,
        "status": status,
        "method": quad.method if quad else "none",
        "quad": quad.points.tolist() if quad else None,
        "label": label,
        "probabilities": probabilities,
        "runtime_ms": round(runtime_ms, 2),
        "rectify": rectify,
        "enhance": enhance,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "width": int(original.shape[1]),
        "height": int(original.shape[0]),
    }
    (directory / "meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadata


def analyze_array(
    original: np.ndarray,
    *,
    rectify: bool = True,
    enhance: bool = False,
    source: str = "upload",
) -> dict:
    if original.ndim == 2:
        original = cv2.cvtColor(original, cv2.COLOR_GRAY2BGR)
    if min(original.shape[:2]) < 32:
        raise WebError("图像尺寸过小，短边至少 32 像素")
    started = time.perf_counter()
    if rectify:
        rectified, quad, status = _apply_rectify(original)
    else:
        rectified, quad, status = original, None, "ok"
    enhanced = _apply_enhance(rectified) if enhance else rectified
    label, probabilities = _classify(enhanced)
    runtime = (time.perf_counter() - started) * 1000
    return _save_result(
        result_id=uuid.uuid4().hex,
        original=original,
        quad=quad,
        rectified=rectified,
        enhanced=enhanced,
        status=status,
        label=label,
        probabilities=probabilities,
        runtime_ms=runtime,
        rectify=rectify,
        enhance=enhance,
        source=source,
    )


def analyze_upload(data: bytes, *, rectify: bool = True, enhance: bool = False) -> dict:
    array = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if array is None:
        raise WebError("无法解码上传图像")
    return analyze_array(array, rectify=rectify, enhance=enhance, source="upload")


def analyze_sample(sample_id: str, *, rectify: bool = True, enhance: bool = False) -> dict:
    array = load_image(sample_path(sample_id), max_long_edge=1280).image
    return analyze_array(array, rectify=rectify, enhance=enhance, source=sample_id)


def get_result(result_id: str) -> dict:
    directory = _result_dir(result_id)
    metadata = directory / "meta.json"
    if not metadata.is_file():
        raise WebError("结果元数据缺失", status=404)
    return json.loads(metadata.read_text(encoding="utf-8"))


def result_stage(result_id: str, stage: str) -> Path:
    if stage.endswith(".png"):
        stage = stage[:-4]
    if stage not in STAGES:
        raise WebError("阶段名称非法", status=404)
    directory = _result_dir(result_id)
    path = directory / f"{stage}.png"
    if not path.is_file():
        raise WebError("阶段图不存在", status=404)
    return path


def reprocess(result_id: str, points: list[tuple[float, float]]) -> dict:
    metadata = get_result(result_id)
    directory = _result_dir(result_id)
    original = cv2.imread(str(directory / "original.png"), cv2.IMREAD_COLOR)
    if original is None:
        raise WebError("原始结果图缺失", status=404)
    try:
        quad = DocumentQuad(np.asarray(points, dtype=np.float32))
    except (RectifyError, ValueError) as exc:
        raise WebError(f"四角非法: {exc}") from exc

    started = time.perf_counter()
    rectified = warp_document(
        original,
        quad,
        output_long_edge=int(CONFIG["rectify"]["output_long_edge"]),
    )
    enhanced = _apply_enhance(rectified) if metadata["enhance"] else rectified
    label, probabilities = _classify(enhanced)
    runtime = (time.perf_counter() - started) * 1000
    return _save_result(
        result_id=result_id,
        original=original,
        quad=quad,
        rectified=rectified,
        enhanced=enhanced,
        status="ok",
        label=label,
        probabilities=probabilities,
        runtime_ms=runtime,
        rectify=True,
        enhance=bool(metadata["enhance"]),
        source=metadata.get("source", "upload"),
    )


def prune_results(ttl_seconds: int | None = None) -> int:
    ttl = ttl_seconds or int(CONFIG["web"]["result_ttl_seconds"])
    now = time.time()
    removed = 0
    if not RESULT_DIR.is_dir():
        return 0
    for directory in RESULT_DIR.iterdir():
        if directory.is_dir() and now - directory.stat().st_mtime > ttl:
            shutil.rmtree(directory, ignore_errors=True)
            removed += 1
    return removed


def _member_scope(annotator: str) -> str | None:
    return annotator if annotator in set(_members()) else None


def annotation_stats(assignee: str | None = None) -> dict:
    index = _sample_index()
    assignment = _assignments()
    train = [
        item for item in index.values()
        if item["split"] == "train" and (not assignee or assignment.get(item["sample_id"]) == assignee)
    ]
    overrides = _annotation_store().load()
    counts = {"text": 0, "formula": 0}
    for item in train:
        label = overrides.get(item["sample_id"], item["original_label"])
        if label in counts:
            counts[label] += 1
    return {
        "train_total": len(train),
        "annotated": sum(1 for item in train if item["sample_id"] in overrides),
        "counts": counts,
    }


def annotation_candidates(
    *, limit: int = 30, only_unlabeled: bool = False, assignee: str | None = None
) -> list[dict]:
    index = _sample_index()
    overrides = _annotation_store().load()
    assignment = _assignments()
    items = []
    for sample in index.values():
        if sample["split"] != "train":
            continue
        if assignee and assignment.get(sample["sample_id"]) != assignee:
            continue
        annotated = sample["sample_id"] in overrides
        if only_unlabeled and annotated:
            continue
        items.append(
            {
                **sample,
                "label": overrides.get(sample["sample_id"], sample["original_label"]),
                "annotated": annotated,
                "assignee": assignment.get(sample["sample_id"], ""),
            }
        )
    items.sort(key=lambda item: (item["annotated"], item["sample_id"]))
    return items[:limit]


def save_annotation(sample_id: str, label: str, annotator: str = "web") -> dict:
    sample = get_sample(sample_id)
    if sample["split"] != "train":
        raise WebError("只允许标注训练集样本", status=403)
    _check_assignment(sample_id, annotator)
    _annotation_store().set(sample_id, label, annotator=annotator)
    return annotation_stats(_member_scope(annotator))


def corner_stats(assignee: str | None = None) -> dict:
    index = _sample_index()
    assignment = _assignments()
    train = [
        item for item in index.values()
        if item["split"] == "train" and (not assignee or assignment.get(item["sample_id"]) == assignee)
    ]
    saved = _corner_store().load()
    return {
        "train_total": len(train),
        "annotated": sum(1 for item in train if item["sample_id"] in saved),
    }


def annotators() -> dict:
    index = _sample_index()
    assignment = _assignments()
    saved_corners = _corner_store().load()
    saved_labels = _annotation_store().load()
    members = _members()
    rows = []
    for member in members:
        assigned = [item for item in index.values() if assignment.get(item["sample_id"]) == member]
        rows.append(
            {
                "name": member,
                "assigned": len(assigned),
                "corners": sum(1 for item in assigned if item["sample_id"] in saved_corners),
                "labels": sum(1 for item in assigned if item["sample_id"] in saved_labels),
            }
        )
    return {"members": rows}


def corner_candidates(
    *, limit: int = 20, only_unannotated: bool = True, assignee: str | None = None
) -> list[dict]:
    index = _sample_index()
    saved = _corner_store().load()
    assignment = _assignments()
    items = []
    for sample in index.values():
        if sample["split"] != "train":
            continue
        if assignee and assignment.get(sample["sample_id"]) != assignee:
            continue
        annotated = sample["sample_id"] in saved
        if only_unannotated and annotated:
            continue
        width, height = (int(value) for value in sample["resolution"].split("x"))
        points = saved.get(sample["sample_id"])
        source = "manual" if points else "none"
        if points is not None:
            points = clamp_points(points, width, height)
        else:
            auto = _auto_points(sample["sample_id"])
            if auto is not None:
                points = [list(point) for point in auto]
                source = "auto"
        items.append(
            {
                **sample,
                "points": points,
                "source": source,
                "annotated": annotated,
                "assignee": assignment.get(sample["sample_id"], ""),
            }
        )
    items.sort(key=lambda item: (item["annotated"], item["sample_id"]))
    return items[:limit]


@lru_cache(maxsize=512)
def _auto_points(sample_id: str) -> tuple[tuple[float, float], ...] | None:
    sample = get_sample(sample_id)
    width, height = (int(value) for value in sample["resolution"].split("x"))
    loaded = load_image(sample_path(sample_id), max_long_edge=1280)
    quad = detect_document(
        loaded.image,
        canny_low=int(CONFIG["rectify"]["canny_low"]),
        canny_high=int(CONFIG["rectify"]["canny_high"]),
        min_area_ratio=float(CONFIG["rectify"]["min_area_ratio"]),
        max_area_ratio=float(CONFIG["rectify"]["max_area_ratio"]),
    )
    if quad is None:
        return None
    points = rescale_points(
        quad.points.tolist(),
        (loaded.image.shape[1], loaded.image.shape[0]),
        (width, height),
    )
    return tuple((float(x), float(y)) for x, y in clamp_points(points, width, height))


def save_corners(
    sample_id: str, points: object, annotator: str = "web"
) -> dict:
    sample = get_sample(sample_id)
    if sample["split"] != "train":
        raise WebError("只允许标注训练集样本", status=403)
    _check_assignment(sample_id, annotator)
    width, height = (int(value) for value in sample["resolution"].split("x"))
    clamped = clamp_points(float_points(points), width, height)
    try:
        quad = DocumentQuad(np.asarray(clamped, dtype=np.float32))
    except (RectifyError, ValueError) as exc:
        raise WebError(f"四角非法: {exc}") from exc
    _corner_store().set(sample_id, quad.points.tolist(), annotator=annotator)
    return corner_stats(_member_scope(annotator))


def float_points(points: object) -> list[list[float]]:
    if not isinstance(points, (list, tuple)) or len(points) != 4:
        raise WebError("需要 4 个顶点")
    try:
        return [[float(point[0]), float(point[1])] for point in points]
    except (TypeError, ValueError, IndexError) as exc:
        raise WebError("四角坐标格式非法") from exc
