"""图像增强：光照校正与限制对比度自适应直方图均衡。

处理顺序为：可选的背景光照校正、CLAHE、可选的双边滤波去噪。
所有函数保持输入尺寸与通道数，输出为 uint8。
"""
from __future__ import annotations

import cv2
import numpy as np


class EnhanceError(ValueError):
    """输入图像或参数不符合增强模块约定。"""


def _validate_image(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.dtype != np.uint8:
        raise EnhanceError(f"仅支持 uint8 图像，实际为 {array.dtype}")
    if array.ndim not in (2, 3):
        raise EnhanceError(f"不支持的图像维度: {array.shape}")
    if array.ndim == 3 and array.shape[2] not in (1, 3, 4):
        raise EnhanceError(f"不支持的通道数: {array.shape[2]}")
    return array


def apply_clahe(
    image: np.ndarray,
    *,
    clip_limit: float = 2.0,
    tile_grid_size: int = 8,
) -> np.ndarray:
    """对亮度通道执行 CLAHE，保持色彩通道不变。

    Args:
        image: BGR 或灰度 uint8 图像。
        clip_limit: 对比度限值，必须大于 0。
        tile_grid_size: 分块大小，必须为正整数。

    Returns:
        增强后的图像，尺寸与通道数同输入。

    Raises:
        EnhanceError: 参数非法或图像类型不支持。
    """
    if clip_limit <= 0:
        raise EnhanceError(f"clip_limit 必须大于 0: {clip_limit}")
    if tile_grid_size < 1:
        raise EnhanceError(f"tile_grid_size 必须为正整数: {tile_grid_size}")

    array = _validate_image(image)
    if array.ndim == 3 and array.shape[2] == 1:
        array = array[:, :, 0]

    clahe = cv2.createCLAHE(
        clipLimit=float(clip_limit),
        tileGridSize=(int(tile_grid_size), int(tile_grid_size)),
    )
    if array.ndim == 2:
        return clahe.apply(array)

    bgr = array[:, :, :3]
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lightness, a_channel, b_channel = cv2.split(lab)
    lab = cv2.merge([clahe.apply(lightness), a_channel, b_channel])
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if array.shape[2] == 4:
        enhanced = np.dstack([enhanced, array[:, :, 3]])
    return enhanced


def correct_illumination(
    image: np.ndarray,
    *,
    kernel_size: int = 61,
    strength: float = 0.8,
    target_level: float = 220.0,
) -> np.ndarray:
    """用大尺度背景估计削弱侧向阴影与光照不均。

    以灰度图的低频背景为基准，对每个通道按比例缩放，使背景趋向统一亮度。
    强度用于在原始图与校正图之间做线性混合，避免过度拉平。

    Args:
        image: BGR 或灰度 uint8 图像。
        kernel_size: 背景估计的等效核大小，必须为大于等于 3 的奇数。
        strength: 混合强度，取值 0 至 1。
        target_level: 校正后的背景目标亮度。

    Returns:
        光照校正后的图像。

    Raises:
        EnhanceError: 参数非法或图像类型不支持。
    """
    if kernel_size < 3 or kernel_size % 2 == 0:
        raise EnhanceError(f"kernel_size 必须为大于等于 3 的奇数: {kernel_size}")
    if not 0.0 <= strength <= 1.0:
        raise EnhanceError(f"strength 必须在 0 至 1 之间: {strength}")
    if target_level <= 0:
        raise EnhanceError(f"target_level 必须大于 0: {target_level}")

    array = _validate_image(image).astype(np.float32)
    gray = array if array.ndim == 2 else cv2.cvtColor(array[:, :, :3], cv2.COLOR_BGR2GRAY)
    sigma = float(kernel_size) / 6.0
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma)
    background = np.maximum(background, 1.0)
    scale = target_level / background

    if array.ndim == 2:
        corrected = np.clip(array * scale, 0, 255)
    else:
        corrected = np.clip(array[:, :, :3] * scale[:, :, None], 0, 255)
        if array.shape[2] == 4:
            corrected = np.dstack([corrected, array[:, :, 3]])

    blended = array * (1.0 - strength) + corrected * strength
    return np.clip(blended, 0, 255).astype(np.uint8)


def enhance_document(
    image: np.ndarray,
    *,
    clip_limit: float = 2.0,
    tile_grid_size: int = 8,
    correct_shadows: bool = True,
    shadow_kernel: int = 61,
    shadow_strength: float = 0.8,
    denoise: bool = True,
) -> np.ndarray:
    """串联光照校正、CLAHE 与去噪。

    Args:
        image: BGR 或灰度 uint8 图像。
        clip_limit: CLAHE 对比度限值。
        tile_grid_size: CLAHE 分块大小。
        correct_shadows: 是否执行光照校正。
        shadow_kernel: 背景估计核大小。
        shadow_strength: 光照校正混合强度。
        denoise: 是否执行双边滤波去噪。

    Returns:
        增强后的图像，尺寸与通道数同输入。

    Raises:
        EnhanceError: 参数非法或图像类型不支持。
    """
    array = _validate_image(image)
    result = array
    if correct_shadows:
        result = correct_illumination(
            result,
            kernel_size=shadow_kernel,
            strength=shadow_strength,
        )
    result = apply_clahe(
        result,
        clip_limit=clip_limit,
        tile_grid_size=tile_grid_size,
    )
    if denoise:
        if result.ndim == 2:
            result = cv2.medianBlur(result, 3)
        else:
            result = cv2.bilateralFilter(result[:, :, :3], 5, 25, 25)
            if array.shape[2] == 4:
                result = np.dstack([result, array[:, :, 3]])
    return result
