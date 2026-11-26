"""图像读取：校正 EXIF 方向并限制最大尺寸。

训练与评估使用本地原始样本；对外展示一律使用 ``data/release/`` 中的打码副本，
见 ``docs/04-数据采集与标注规范.md`` 第 10 节。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageOps


def load_image(
    path: str | Path,
    max_side: Optional[int] = None,
) -> np.ndarray:
    """读取单张图像，返回 HxWxC 的 RGB uint8 数组。

    读取时自动校正 EXIF 方向（手机竖拍常见旋转 90/270 度）。``max_side``
    不为 None 时，将最长边缩放到该值，用于限制内存占用。
    """
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        if max_side is not None and max_side > 0:
            img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        return np.asarray(img, dtype=np.uint8)
