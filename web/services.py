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
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import torch
import yaml
from PIL import Image, ImageOps

from docnorm.classify.classic import ClassicClassifier
from docnorm.classify.cnn import CLASSES as CNN_CLASSES, CnnClassifier
from docnorm.classify.gate import ScreenGate
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
CARRIER_GATE_ENV = "DOCNORM_CARRIER_GATE"
PAPER_MODELS_ENV = "DOCNORM_PAPER_MODELS"
PPT_MODEL_ENV = "DOCNORM_PPT_MODEL"
DEFAULT_CARRIER_GATE = ROOT / "runs/carrier-gate-01/screen_gate.pt"
DEFAULT_PAPER_MODELS = (
    ROOT / "runs/paper-cnn-extctl-01/paper_cnn.pt",
    ROOT / "runs/paper-cnn-extctl-43/paper_cnn.pt",
    ROOT / "runs/paper-cnn-extctl-44/paper_cnn.pt",
)
DEFAULT_PPT_MODEL = ROOT / "runs/exp-cnn-05/cnn.pt"
RESULT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
STAGES = ("original", "quad", "rectified", "enhanced", "scan")


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


def _redo_index() -> dict[str, dict]:
    path = _redo_path()
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {
            row["sample_id"]: row
            for row in csv.DictReader(stream)
            if row.get("sample_id") and row.get("status", "pending") == "pending"
        }


def _clear_redo(sample_id: str) -> None:
    path = _redo_path()
    if not path.is_file():
        return
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    fields = list(rows[0].keys()) if rows else [
        "sample_id", "assignee", "previous_points", "reason", "requested_at", "status"
    ]
    rows = [row for row in rows if row["sample_id"] != sample_id]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


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
    """优先选当前划分上验证准确率最高的 SVM，避免重启后误用较差实验。"""
    override = os.environ.get(MODEL_ENV)
    if override and Path(override).is_file():
        return Path(override)
    split_name = Path(CONFIG["data"]["split"]).name
    ranked: list[tuple[float, float, Path]] = []
    for path in (ROOT / "runs").glob("exp-*/svm.joblib"):
        metrics_path = path.parent / "metrics.json"
        if not metrics_path.is_file():
            continue
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if metrics.get("split") != split_name:
            continue
        svm_metrics = (metrics.get("models") or {}).get("svm") or {}
        accuracy = svm_metrics.get("accuracy")
        if accuracy is None:
            continue
        ranked.append((float(accuracy), path.stat().st_mtime, path))
    if ranked:
        return max(ranked)[2]
    candidates = sorted(
        (ROOT / "runs").glob("exp-*/svm.joblib"), key=lambda p: p.stat().st_mtime
    )
    return candidates[-1] if candidates else None


def _carrier_gate_path() -> Path | None:
    override = os.environ.get(CARRIER_GATE_ENV)
    path = Path(override) if override else DEFAULT_CARRIER_GATE
    return path if path.is_file() else None


def _paper_model_paths() -> list[Path]:
    override = os.environ.get(PAPER_MODELS_ENV)
    if override:
        return [Path(item) for item in override.split(os.pathsep) if item]
    paths = [path for path in DEFAULT_PAPER_MODELS if path.is_file()]
    if paths:
        return paths
    fallback = ROOT / "runs/paper-cnn-01/paper_cnn.pt"
    return [fallback] if fallback.is_file() else []


def _ppt_model_path() -> Path | None:
    override = os.environ.get(PPT_MODEL_ENV)
    path = Path(override) if override else DEFAULT_PPT_MODEL
    return path if path.is_file() else None


def model_status() -> dict:
    """返回双分支模型可用性，供 /api/health 与页面提示使用。"""
    carrier = _carrier_gate_path()
    paper = _paper_model_paths()
    ppt = _ppt_model_path()
    return {
        "carrier_gate": str(carrier) if carrier else None,
        "paper_models": [str(path) for path in paper],
        "ppt_model": str(ppt) if ppt else None,
        "routing_ready": bool(carrier and paper and ppt),
    }


_MODEL: ClassicClassifier | None = None
_CARRIER_GATE: ScreenGate | None = None
_PAPER_MODELS: list[CnnClassifier] | None = None
_PPT_MODEL: CnnClassifier | None = None


def _classifier() -> ClassicClassifier | None:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    path = _model_path()
    if path is None:
        return None
    _MODEL = ClassicClassifier.load(path)
    return _MODEL


def _carrier_gate() -> ScreenGate | None:
    global _CARRIER_GATE
    if _CARRIER_GATE is not None:
        return _CARRIER_GATE
    path = _carrier_gate_path()
    if path is None:
        return None
    _CARRIER_GATE = ScreenGate.from_checkpoint(path)
    return _CARRIER_GATE


def _paper_models() -> list[CnnClassifier]:
    global _PAPER_MODELS
    if _PAPER_MODELS is not None:
        return _PAPER_MODELS
    models: list[CnnClassifier] = []
    for path in _paper_model_paths():
        try:
            models.append(CnnClassifier.load(path, device="cpu"))
        except (OSError, RuntimeError, ValueError):
            continue
    _PAPER_MODELS = models
    return models


def _ppt_model() -> CnnClassifier | None:
    global _PPT_MODEL
    if _PPT_MODEL is not None:
        return _PPT_MODEL
    path = _ppt_model_path()
    if path is None:
        return None
    _PPT_MODEL = CnnClassifier.load(path, device="cpu")
    return _PPT_MODEL


def _classic_scores(array: np.ndarray) -> tuple[str, dict[str, float]] | None:
    model = _classifier()
    if model is None:
        return None
    features = extract_features(array).reshape(1, -1)
    probabilities = model.predict_proba(features)[0]
    classes = list(model.classes_)
    scores = {name: float(probabilities[classes.index(name)]) for name in classes}
    return max(scores, key=scores.get), scores


@torch.no_grad()
def _cnn_scores(
    models: list[CnnClassifier], array: np.ndarray
) -> tuple[str, dict[str, float]]:
    total = torch.zeros(1, len(CNN_CLASSES))
    for model in models:
        tensor = model._prepare(array).unsqueeze(0)
        total += torch.softmax(model.model(tensor), dim=1)
    probabilities = (total / len(models))[0].cpu().numpy()
    scores = {
        name: float(probabilities[index]) for index, name in enumerate(CNN_CLASSES)
    }
    return max(scores, key=scores.get), scores


def _classify(
    original: np.ndarray, array: np.ndarray
) -> tuple[str | None, dict[str, float] | None, dict]:
    """载体门控 → 纸质稿集成 / PPT CNN → SVM 兜底。"""
    carrier = None
    carrier_probabilities = None
    branch = "classic-svm"
    gate = _carrier_gate()
    if gate is not None:
        gate_probabilities = gate.predict_proba(original)
        carrier = "ppt" if gate_probabilities[1] >= 0.5 else "paper"
        carrier_probabilities = {
            "paper": float(gate_probabilities[0]),
            "ppt": float(gate_probabilities[1]),
        }

    routed = None
    if carrier == "paper":
        models = _paper_models()
        if models:
            routed = _cnn_scores(models, array)
            branch = f"paper-cnn-ensemble-{len(models)}"
    elif carrier == "ppt":
        model = _ppt_model()
        if model is not None:
            routed = _cnn_scores([model], array)
            branch = "ppt-cnn-exp-cnn-05"

    if routed is None:
        routed = _classic_scores(array)
    if routed is None:
        return None, None, {
            "carrier": carrier or "unknown",
            "carrier_probabilities": carrier_probabilities,
            "branch": branch,
        }
    label, scores = routed
    return label, scores, {
        "carrier": carrier or "unknown",
        "carrier_probabilities": carrier_probabilities,
        "branch": branch,
    }


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


def _scan_unsharp(image: np.ndarray, amount: float, sigma: float) -> np.ndarray:
    blurred = cv2.GaussianBlur(image, (0, 0), sigma)
    return cv2.addWeighted(image, amount, blurred, -(amount - 1), 0)


def _limit_long_edge(image: np.ndarray, max_edge: int) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_edge:
        return image
    scale = max_edge / float(longest)
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def _scan_gamma(image: np.ndarray, gamma: float) -> np.ndarray:
    table = np.array(
        [((value / 255.0) ** gamma) * 255.0 for value in range(256)],
        dtype=np.uint8,
    )
    return cv2.LUT(image, table)


def _scan_block(gray: np.ndarray, preferred: int) -> int:
    block = min(preferred, min(gray.shape[:2]))
    if block % 2 == 0:
        block -= 1
    return max(3, block)


def _apply_scan(array: np.ndarray) -> np.ndarray:
    """生成扫描件：浅色纸面锐化后二值化，深色黑板反相后去噪二值化。

    统一输出白底黑字，避免深色背景被自适应阈值整片漂白（过曝）。
    """
    array = _limit_long_edge(np.asarray(array), 1600)
    gray = (
        cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
        if array.ndim == 3
        else array
    )
    if float(gray.mean()) < 120.0:
        inverted = 255 - gray
        inverted = cv2.fastNlMeansDenoising(inverted, None, 7, 7, 21)
        inverted = cv2.bilateralFilter(inverted, 7, 50, 50)
        sigma = max(7.0, min(gray.shape[:2]) / 20.0)
        background = cv2.GaussianBlur(inverted, (0, 0), sigma)
        normalized = cv2.divide(inverted, background, scale=255)
        normalized = _scan_gamma(normalized, 1.08)
        sharpened = _scan_unsharp(normalized, 1.7, 1.0)
        binary = cv2.adaptiveThreshold(
            sharpened,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            _scan_block(gray, 61),
            12,
        )
        return cv2.medianBlur(binary, 3)

    sharpened = _scan_unsharp(_scan_gamma(gray, 1.12), 1.25, 1.0)
    return cv2.adaptiveThreshold(
        sharpened,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        _scan_block(gray, 35),
        14,
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
    scan: np.ndarray,
    status: str,
    label: str | None,
    probabilities: dict[str, float] | None,
    routing: dict | None,
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
    cv2.imwrite(str(directory / "scan.png"), scan)
    metadata = {
        "result_id": result_id,
        "status": status,
        "method": quad.method if quad else "none",
        "quad": quad.points.tolist() if quad else None,
        "label": label,
        "probabilities": probabilities,
        "carrier": (routing or {}).get("carrier", "unknown"),
        "carrier_probabilities": (routing or {}).get("carrier_probabilities"),
        "branch": (routing or {}).get("branch", "classic-svm"),
        "runtime_ms": round(runtime_ms, 2),
        "rectify": rectify,
        "enhance": enhance,
        "scan": True,
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
    # 手机原图可能远超网页演示所需；先限制长边，避免检测/扫描阶段
    # 在容器内申请过大内存导致整机卡死。
    original = _limit_long_edge(original, 2000)
    started = time.perf_counter()
    if rectify:
        rectified, quad, status = _apply_rectify(original)
    else:
        rectified, quad, status = original, None, "ok"
    enhanced = _apply_enhance(rectified) if enhance else rectified
    scan = _apply_scan(rectified)
    label, probabilities, routing = _classify(original, enhanced)
    runtime = (time.perf_counter() - started) * 1000
    return _save_result(
        result_id=uuid.uuid4().hex,
        original=original,
        quad=quad,
        rectified=rectified,
        enhanced=enhanced,
        scan=scan,
        status=status,
        label=label,
        probabilities=probabilities,
        routing=routing,
        runtime_ms=runtime,
        rectify=rectify,
        enhance=enhance,
        source=source,
    )


def _decode_upload(data: bytes) -> np.ndarray | None:
    """按 EXIF 方向转正后解码上传图像，避免电脑原图与手机转码图方向不一致。"""
    try:
        with Image.open(BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            rgb = np.asarray(image, dtype=np.uint8)
    except (OSError, ValueError):
        return None
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def analyze_upload(data: bytes, *, rectify: bool = True, enhance: bool = False) -> dict:
    array = _decode_upload(data)
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
    scan = _apply_scan(rectified)
    label, probabilities, routing = _classify(original, enhanced)
    runtime = (time.perf_counter() - started) * 1000
    return _save_result(
        result_id=result_id,
        original=original,
        quad=quad,
        rectified=rectified,
        enhanced=enhanced,
        scan=scan,
        status="ok",
        label=label,
        probabilities=probabilities,
        routing=routing,
        runtime_ms=runtime,
        rectify=True,
        enhance=bool(metadata["enhance"]),
        source=metadata.get("source", "upload"),
    )


def build_pdf(result_ids: list[str], mode: str = "scan") -> BytesIO:
    """把多个结果页导出为 PDF；mode 取 scan/rectified/original。"""
    if mode not in {"scan", "rectified", "original"}:
        raise WebError("PDF 模式非法", status=400)
    if not result_ids:
        raise WebError("至少需要一个结果", status=400)
    if len(result_ids) > 50:
        raise WebError("单次最多导出 50 页", status=400)
    pages: list[Image.Image] = []
    for result_id in result_ids:
        directory = _result_dir(result_id)
        path = directory / f"{mode}.png"
        if not path.is_file():
            raise WebError(f"结果页缺失: {result_id}/{mode}", status=404)
        with Image.open(path) as image:
            pages.append(image.convert("RGB"))
    buffer = BytesIO()
    pages[0].save(
        buffer,
        format="PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=150,
    )
    buffer.seek(0)
    return buffer


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
    redo = _redo_index()
    train = [
        item for item in index.values()
        if item["split"] == "train" and (not assignee or assignment.get(item["sample_id"]) == assignee)
    ]
    saved = _corner_store().load()
    return {
        "train_total": len(train),
        "annotated": sum(1 for item in train if item["sample_id"] in saved),
        "redo": sum(1 for item in train if item["sample_id"] in redo),
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
    redo = _redo_index()
    items = []
    for sample in index.values():
        if sample["split"] != "train":
            continue
        if assignee and assignment.get(sample["sample_id"]) != assignee:
            continue
        annotated = sample["sample_id"] in saved
        if only_unannotated and annotated and sample["sample_id"] not in redo:
            continue
        width, height = (int(value) for value in sample["resolution"].split("x"))
        points = None if sample["sample_id"] in redo else saved.get(sample["sample_id"])
        source = "manual" if points else "none"
        if sample["sample_id"] in redo:
            source = "redo"
        if points is not None:
            points = clamp_points(points, width, height)
        else:
            auto = _auto_points(sample["sample_id"])
            if auto is not None:
                points = [list(point) for point in auto]
                source = "auto" if sample["sample_id"] not in redo else "redo"
        items.append(
            {
                **sample,
                "points": points,
                "source": source,
                "annotated": annotated,
                "redo": sample["sample_id"] in redo,
                "redo_reason": redo.get(sample["sample_id"], {}).get("reason", ""),
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
    _clear_redo(sample_id)
    return corner_stats(_member_scope(annotator))


def float_points(points: object) -> list[list[float]]:
    if not isinstance(points, (list, tuple)) or len(points) != 4:
        raise WebError("需要 4 个顶点")
    try:
        return [[float(point[0]), float(point[1])] for point in points]
    except (TypeError, ValueError, IndexError) as exc:
        raise WebError("四角坐标格式非法") from exc


def _redo_path() -> Path:
    return Path(os.environ.get(
        "DOCNORM_REDO_PATH", ROOT / "data/annotations/redo_corners.csv"
    ))


def _read_redo_rows() -> list[dict]:
    path = _redo_path()
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_redo_rows(rows: list[dict]) -> None:
    path = _redo_path()
    fields = [
        "sample_id", "assignee", "previous_points", "reason", "requested_at", "status"
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def review_stats(assignee: str | None = None) -> dict:
    index = _sample_index()
    assignment = _assignments()
    records = _corner_store().records()
    redo = _redo_index()
    train = [
        item for item in index.values()
        if item["split"] == "train" and (not assignee or assignment.get(item["sample_id"]) == assignee)
    ]
    return {
        "total": len(train),
        "saved": sum(1 for item in train if item["sample_id"] in records),
        "redo": sum(1 for item in train if item["sample_id"] in redo),
        "unannotated": sum(
            1 for item in train
            if item["sample_id"] not in records and item["sample_id"] not in redo
        ),
    }


def review_corners(
    *,
    assignee: str | None = None,
    status: str | None = None,
    limit: int = 12,
    offset: int = 0,
) -> dict:
    index = _sample_index()
    assignment = _assignments()
    records = _corner_store().records()
    redo = _redo_index()
    items = []
    for sample in index.values():
        if sample["split"] != "train":
            continue
        if assignee and assignment.get(sample["sample_id"]) != assignee:
            continue
        record = records.get(sample["sample_id"])
        redo_row = redo.get(sample["sample_id"])
        if record:
            state = "saved"
            points = record["points"]
            annotator = record["annotator"]
        elif redo_row:
            state = "redo"
            points = json.loads(redo_row["previous_points"])
            annotator = assignment.get(sample["sample_id"], "")
        else:
            state = "unannotated"
            points = None
            annotator = assignment.get(sample["sample_id"], "")
        if status and status != "all" and state != status:
            continue
        items.append(
            {
                **sample,
                "points": points,
                "annotator": annotator,
                "review_status": state,
                "redo": state == "redo",
                "redo_reason": redo_row["reason"] if redo_row else "",
            }
        )
    items.sort(key=lambda item: (item["review_status"] != "redo", item["sample_id"]))
    return {
        "total": len(items),
        "stats": review_stats(assignee),
        "items": items[offset: offset + limit],
    }


def send_back_corner(sample_id: str, reason: str) -> dict:
    sample = get_sample(sample_id)
    if sample["split"] != "train":
        raise WebError("只允许退回训练集样本", status=403)
    records = _corner_store().records()
    if sample_id not in records:
        if sample_id in _redo_index():
            raise WebError("样本已在退回队列", status=409)
        raise WebError("样本没有已保存四角", status=404)
    row = {
        "sample_id": sample_id,
        "assignee": _assignments().get(sample_id, ""),
        "previous_points": json.dumps(records[sample_id]["points"], separators=(",", ":")),
        "reason": reason,
        "requested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "pending",
    }
    rows = [item for item in _read_redo_rows() if item["sample_id"] != sample_id]
    rows.append(row)
    _write_redo_rows(rows)
    _corner_store().remove(sample_id)
    return review_stats(_assignments().get(sample_id))
