"""文档四边形的几何定义与规范化。

坐标约定：图像坐标系，x 向右、y 向下；顶点顺序为左上、右上、右下、左下。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class RectifyError(ValueError):
    """四边形非法或无法完成透视变换。"""


def _polygon_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _is_convex(ordered: np.ndarray) -> bool:
    signs = []
    for index in range(4):
        a = ordered[index]
        b = ordered[(index + 1) % 4]
        c = ordered[(index + 2) % 4]
        cross = float(
            (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        )
        signs.append(cross)
    return all(value > 1e-6 for value in signs) or all(value < -1e-6 for value in signs)


def order_quad(points: np.ndarray) -> np.ndarray:
    """把四个顶点规范为左上、右上、右下、左下。

    Raises:
        RectifyError: 顶点数量、重复点、面积或凸性不合法。
    """
    array = np.asarray(points, dtype=np.float32)
    if array.shape != (4, 2):
        raise RectifyError(f"需要 4 个二维顶点，实际为 {array.shape}")

    for first in range(4):
        for second in range(first + 1, 4):
            if float(np.linalg.norm(array[first] - array[second])) < 1.0:
                raise RectifyError("存在重复顶点")

    if _polygon_area(array) < 1.0:
        raise RectifyError("四边形面积过小或顶点共线")

    # 任一相邻三点共线都会使四边形退化为三角形，直接拒绝。
    for index in range(4):
        a = array[index]
        b = array[(index + 1) % 4]
        c = array[(index + 2) % 4]
        cross = float(
            (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        )
        if abs(cross) < 1e-6:
            raise RectifyError("存在共线顶点")

    total = array.sum(axis=1)
    diff = array[:, 1] - array[:, 0]
    ordered = np.array(
        [
            array[int(np.argmin(total))],
            array[int(np.argmin(diff))],
            array[int(np.argmax(total))],
            array[int(np.argmax(diff))],
        ],
        dtype=np.float32,
    )

    if not _is_convex(ordered):
        raise RectifyError("四边形不是凸多边形")

    first = ordered[1] - ordered[0]
    second = ordered[2] - ordered[1]
    cross = float(first[0] * second[1] - first[1] * second[0])
    if cross < 0:
        ordered = ordered[[0, 3, 2, 1]]
    return ordered


@dataclass(frozen=True)
class DocumentQuad:
    """文档四边形。构造时自动规范顶点顺序。

    Attributes:
        points: 规范化后的四个顶点，顺序为左上、右上、右下、左下。
        area_ratio: 四边形面积占画面比例。
        method: 检出方式，取值为 edge、mask_quad 或 mask_rect，便于统计失败类型。
    """

    points: np.ndarray
    area_ratio: float = 0.0
    method: str = "edge"

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", order_quad(self.points))


def quad_dimensions(points: np.ndarray) -> tuple[float, float]:
    """按对边最大长度估计文档的宽度与高度。"""
    array = np.asarray(points, dtype=np.float32)
    width = max(
        float(np.linalg.norm(array[1] - array[0])),
        float(np.linalg.norm(array[2] - array[3])),
    )
    height = max(
        float(np.linalg.norm(array[3] - array[0])),
        float(np.linalg.norm(array[2] - array[1])),
    )
    return width, height
