"""文档四边形检测。

候选来源与评分：

1. 边缘检测配合多次多边形近似，保留透视关系，权重最高。
2. 亮度阈值分割，分别取亮区与暗区，适配白纸与黑板两类载体。
3. 分割轮廓的最小外接矩形，作为边界不规则时的兜底，权重最低。

所有候选统一按“面积 × 边界对比度 × 来源权重”评分，取最高分。
低于置信门槛时返回 None，交由人工兜底，不输出错误的四边形。
"""
from __future__ import annotations

import cv2
import numpy as np

from docnorm.rectify.geometry import (
    DocumentQuad,
    RectifyError,
    quad_dimensions,
)

METHOD_WEIGHTS = {"edge": 1.0, "mask_quad": 0.95, "mask_rect": 0.75}
MIN_CONFIDENCE_AREA = 0.15
MIN_BOUNDARY_CONTRAST = 8.0


def _quad_area_ratio(points: np.ndarray, width: int, height: int) -> float:
    x = points[:, 0]
    y = points[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    return area / float(width * height)


def _covers_full_frame(points: np.ndarray, width: int, height: int, margin: int = 3) -> bool:
    """四边形的包围盒是否同时贴住四条边。"""
    return bool(
        points[:, 0].min() < margin
        and points[:, 1].min() < margin
        and points[:, 0].max() > width - 1 - margin
        and points[:, 1].max() > height - 1 - margin
    )


def _boundary_contrast(points: np.ndarray, gray: np.ndarray, offset: int = 6) -> float:
    """沿四条边比较内外两侧的灰度差，用于排除墙面等弱边界区域。"""
    height, width = gray.shape[:2]
    center = points.mean(axis=0)
    inside_values: list[float] = []
    outside_values: list[float] = []
    for index in range(4):
        start = points[index]
        end = points[(index + 1) % 4]
        edge = end - start
        normal = np.array([-edge[1], edge[0]], dtype=np.float32)
        length = float(np.linalg.norm(normal))
        if length < 1e-6:
            return 0.0
        normal /= length
        midpoint = (start + end) / 2.0
        if float(np.dot(normal, center - midpoint)) < 0:
            normal = -normal
        for ratio in np.linspace(0.1, 0.9, 24):
            base = start + (end - start) * ratio
            for sign, bucket in ((1.0, inside_values), (-1.0, outside_values)):
                x = int(round(base[0] + sign * normal[0] * offset))
                y = int(round(base[1] + sign * normal[1] * offset))
                if 0 <= y < height and 0 <= x < width:
                    bucket.append(float(gray[y, x]))
    if not inside_values or not outside_values:
        return 0.0
    return abs(float(np.mean(inside_values)) - float(np.mean(outside_values)))


def _build_candidate(
    points: np.ndarray,
    gray: np.ndarray,
    method: str,
) -> tuple[float, DocumentQuad] | None:
    """校验候选几何并计算置信分数。"""
    height, width = gray.shape[:2]
    ratio = _quad_area_ratio(points, width, height)
    if ratio < MIN_CONFIDENCE_AREA or ratio > 0.98:
        return None
    if _covers_full_frame(points, width, height):
        return None
    try:
        quad = DocumentQuad(points, area_ratio=ratio, method=method)
    except RectifyError:
        return None
    quad_width, quad_height = quad_dimensions(quad.points)
    if min(quad_width, quad_height) < 20:
        return None
    if not 0.2 <= quad_width / quad_height <= 5:
        return None
    contrast = _boundary_contrast(quad.points, gray)
    if contrast < MIN_BOUNDARY_CONTRAST:
        return None
    score = ratio * min(contrast / 30.0, 2.0) * METHOD_WEIGHTS.get(method, 0.5)
    return score, quad


def _collect_edge_candidates(
    gray: np.ndarray,
    canny_low: int,
    canny_high: int,
) -> list[tuple[float, DocumentQuad]]:
    height, width = gray.shape[:2]
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    passes = (
        (max(1, canny_low), max(2, canny_high)),
        (max(1, canny_low * 2 // 3), max(2, canny_high * 2 // 3)),
        (max(1, canny_low * 3 // 2), max(3, canny_high * 4 // 3)),
    )
    kernel = np.ones((5, 5), dtype=np.uint8)
    candidates: list[tuple[float, DocumentQuad]] = []

    for low, high in passes:
        edges = cv2.Canny(blurred, low, high)
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(
            closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
            area = float(cv2.contourArea(contour)) / float(width * height)
            if area < MIN_CONFIDENCE_AREA:
                break
            if area > 0.98:
                continue
            perimeter = float(cv2.arcLength(contour, True))
            if perimeter <= 0:
                continue
            circularity = (
                4.0
                * float(np.pi)
                * float(cv2.contourArea(contour))
                / (perimeter * perimeter)
            )
            if circularity > 0.87:
                continue
            for epsilon in (0.02, 0.03, 0.05):
                approx = cv2.approxPolyDP(contour, epsilon * perimeter, True)
                if len(approx) != 4 or not cv2.isContourConvex(approx):
                    continue
                candidate = _build_candidate(
                    approx.reshape(4, 2).astype(np.float32), gray, "edge"
                )
                if candidate is not None:
                    candidates.append(candidate)
    return candidates


def _collect_mask_candidates(gray: np.ndarray) -> list[tuple[float, DocumentQuad]]:
    height, width = gray.shape[:2]
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    candidates: list[tuple[float, DocumentQuad]] = []

    for threshold_type in (
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    ):
        _, mask = cv2.threshold(blurred, 0, 255, threshold_type)
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2
        )
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8), iterations=1
        )
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
            area = float(cv2.contourArea(contour)) / float(width * height)
            if area < MIN_CONFIDENCE_AREA:
                break
            if area > 0.98:
                continue

            perimeter = float(cv2.arcLength(contour, True))
            if perimeter > 0:
                approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
                if len(approx) == 4 and cv2.isContourConvex(approx):
                    candidate = _build_candidate(
                        approx.reshape(4, 2).astype(np.float32), gray, "mask_quad"
                    )
                    if candidate is not None:
                        candidates.append(candidate)

            (center_x, center_y), (rect_width, rect_height), _ = cv2.minAreaRect(contour)
            if rect_width < 1 or rect_height < 1:
                continue
            rectangularity = float(cv2.contourArea(contour)) / (rect_width * rect_height)
            if rectangularity < 0.82:
                continue
            box = cv2.boxPoints(((center_x, center_y), (rect_width, rect_height), 0))
            candidate = _build_candidate(
                np.asarray(box, dtype=np.float32), gray, "mask_rect"
            )
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def _to_gray(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 2:
        return array
    if array.ndim == 3 and array.shape[2] >= 3:
        return cv2.cvtColor(array[:, :, :3], cv2.COLOR_BGR2GRAY)
    raise RectifyError(f"不支持的图像维度: {array.shape}")


def detect_document(
    image: np.ndarray,
    *,
    canny_low: int = 50,
    canny_high: int = 150,
    min_area_ratio: float = 0.15,
    max_area_ratio: float = 0.98,
) -> DocumentQuad | None:
    """检测画面中的文档四边形。

    Args:
        image: BGR 或灰度数组。
        canny_low: Canny 低阈值基准。
        canny_high: Canny 高阈值基准。
        min_area_ratio: 接受候选的面积比例下限。
        max_area_ratio: 接受候选的面积比例上限。

    Returns:
        DocumentQuad；未检出可信四边形时返回 None。

    Raises:
        RectifyError: 输入图像维度不受支持，或面积比例参数不合法。
    """
    if not 0 < min_area_ratio < max_area_ratio <= 1:
        raise RectifyError("面积比例参数不合法")

    gray = _to_gray(image)
    height, width = gray.shape[:2]
    if height < 32 or width < 32:
        return None

    candidates = _collect_edge_candidates(gray, canny_low, canny_high)
    candidates.extend(_collect_mask_candidates(gray))
    if not candidates:
        return None

    admissible = [
        (score, quad)
        for score, quad in candidates
        if min_area_ratio <= quad.area_ratio <= max_area_ratio
    ]
    if not admissible:
        return None
    return max(admissible, key=lambda item: item[0])[1]
