"""透视变换：把四边形区域拉正为矩形图。"""
from __future__ import annotations

import cv2
import numpy as np

from docnorm.rectify.geometry import (
    DocumentQuad,
    RectifyError,
    quad_dimensions,
)


def warp_document(
    image: np.ndarray,
    quad: DocumentQuad | np.ndarray,
    *,
    output_long_edge: int | None = None,
) -> np.ndarray:
    """按四边形执行透视变换。

    Args:
        image: 原始图像，灰度或 BGR。
        quad: DocumentQuad 或 4 个顶点。
        output_long_edge: 输出长边上限；为 None 时保持估计尺寸。

    Returns:
        矫正后的图像。

    Raises:
        RectifyError: 图像维度不支持、四边形非法或输出尺寸非法。
    """
    array = np.asarray(image)
    if array.ndim not in (2, 3):
        raise RectifyError(f"不支持的图像维度: {array.shape}")

    document = quad if isinstance(quad, DocumentQuad) else DocumentQuad(quad)
    width, height = quad_dimensions(document.points)
    if width < 1 or height < 1:
        raise RectifyError("四边形尺寸过小")

    source = document.points.astype(np.float32)
    target = np.array(
        [
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(source, target)
    warped = cv2.warpPerspective(
        array,
        matrix,
        (int(round(width)), int(round(height))),
        flags=cv2.INTER_CUBIC,
    )

    if output_long_edge is not None:
        if output_long_edge <= 0:
            raise RectifyError(f"output_long_edge 必须为正整数: {output_long_edge}")
        longest = max(warped.shape[:2])
        if longest > output_long_edge:
            scale = output_long_edge / longest
            warped = cv2.resize(
                warped,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_AREA,
            )
    return warped
