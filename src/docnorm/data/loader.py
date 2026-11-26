"""图像读取与基础预处理。

对外契约：返回 BGR 三通道 uint8 数组；按 EXIF 方向校正；可选限制长边。
失败一律抛出 LoaderError，便于批处理隔离与定位。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


class LoaderError(RuntimeError):
    """图像不可读或不符合输入约定。"""


@dataclass(frozen=True)
class LoadedImage:
    """读取结果。

    Attributes:
        image: BGR 三通道 uint8 数组，形状为 (高, 宽, 3)。
        original_size: 原始像素尺寸 (宽, 高)，已按 EXIF 方向校正。
        scale: 缩放比例，未缩放时为 1.0。
    """

    image: np.ndarray
    original_size: tuple[int, int]
    scale: float


def load_image(path: Path, max_long_edge: int | None = None) -> LoadedImage:
    """读取图像并转换为 BGR 数组。

    Args:
        path: 图像路径，可为中文与含空格路径。
        max_long_edge: 限制长边像素数；为 None 时保持原始尺寸。

    Returns:
        LoadedImage 实例。

    Raises:
        LoaderError: 文件不存在、无法解码或长边限制非法。
    """
    path = Path(path)
    if not path.is_file():
        raise LoaderError(f"文件不存在: {path}")
    if max_long_edge is not None and max_long_edge <= 0:
        raise LoaderError(f"max_long_edge 必须为正整数: {max_long_edge}")

    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            width, height = image.size
            if max_long_edge is not None and max(width, height) > max_long_edge:
                image.thumbnail((max_long_edge, max_long_edge), Image.LANCZOS)
            new_width, new_height = image.size
            rgb = np.asarray(image, dtype=np.uint8)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise LoaderError(f"无法解码图像: {path}") from exc

    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    return LoadedImage(
        image=bgr,
        original_size=(width, height),
        scale=new_width / width,
    )
