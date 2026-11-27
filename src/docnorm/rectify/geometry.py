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


def _convex_hull(points: np.ndarray) -> np.ndarray:
    """返回点集的凸包顶点（逆时针，图像坐标下视觉为顺时针）。"""
    unique = sorted({(float(x), float(y)) for x, y in points})
    if len(unique) <= 2:
        return np.asarray(unique, dtype=np.float32)

    def cross(origin, first, second) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (
            first[1] - origin[1]
        ) * (second[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    return np.asarray(hull, dtype=np.float32)


def order_quad(points: np.ndarray) -> np.ndarray:
    """把四个顶点规范为左上、右上、右下、左下。

    手工点击可能不按边缘顺序，先取凸包再规范化；任意顺序点四个角都能
    得到同一结果。若有点落在其余三点内部或三点共线，凸包不足四个顶点，
    仍会拒绝。

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

    # 任意三点共线都会使四边形退化为三角形，直接拒绝。
    for first in range(4):
        for second in range(first + 1, 4):
            for third in range(second + 1, 4):
                a, b, c = array[first], array[second], array[third]
                cross = float(
                    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                )
                if abs(cross) < 1e-6:
                    raise RectifyError("存在共线顶点")

    hull = _convex_hull(array)
    if hull.shape[0] < 3:
        raise RectifyError("存在共线顶点")
    if hull.shape[0] != 4:
        raise RectifyError("四个顶点不能构成凸四边形（有点落在内部）")
    if _polygon_area(hull) < 1.0:
        raise RectifyError("四边形面积过小或顶点共线")

    total = hull.sum(axis=1)
    diff = hull[:, 1] - hull[:, 0]
    top_left = int(np.argmin(total))
    bottom_right = int(np.argmax(total))
    if top_left == bottom_right:
        raise RectifyError("四边形不是凸多边形")
    remaining = [index for index in range(4) if index not in {top_left, bottom_right}]
    top_right = min(remaining, key=lambda index: diff[index])
    bottom_left = max(remaining, key=lambda index: diff[index])
    ordered = hull[[top_left, top_right, bottom_right, bottom_left]]

    if not _is_convex(ordered):
        # 极端旋转下角点命名可能交叉，退回凸包的环状顺序。
        ordered = np.roll(hull, -top_left, axis=0)
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
