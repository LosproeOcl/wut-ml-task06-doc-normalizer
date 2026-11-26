"""传统手工特征：版面密度、边缘方向直方图与方向梯度直方图。

特征维度固定为 1836：密度 64、方向 8、HOG 1764。
契约见 ADR-0002 与 docs/03-架构设计.md。
"""
from __future__ import annotations

import cv2
import numpy as np
from skimage.feature import hog

GRID_SIZE = 8
ORIENTATION_BINS = 8
HOG_SIZE = 256
HOG_CELL = 32
HOG_DIM = 1764
FEATURE_DIM = GRID_SIZE * GRID_SIZE + ORIENTATION_BINS + HOG_DIM


class FeatureError(ValueError):
    """图像不满足特征提取约定。"""


def _to_gray(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.dtype != np.uint8:
        raise FeatureError(f"仅支持 uint8 图像，实际为 {array.dtype}")
    if array.size == 0:
        raise FeatureError("图像为空")
    if array.ndim == 2:
        gray = array
    elif array.ndim == 3 and array.shape[2] >= 3:
        gray = cv2.cvtColor(array[:, :, :3], cv2.COLOR_BGR2GRAY)
    else:
        raise FeatureError(f"不支持的图像维度: {array.shape}")
    if gray.shape[0] < 32 or gray.shape[1] < 32:
        raise FeatureError(f"图像尺寸过小: {gray.shape}")
    return gray


def _density_features(gray: np.ndarray) -> np.ndarray:
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    density = cv2.resize(
        binary, (GRID_SIZE, GRID_SIZE), interpolation=cv2.INTER_AREA
    ).astype(np.float32) / 255.0
    return density.reshape(-1)


def _orientation_features(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    gradient_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gradient_x, gradient_y)
    angle = np.mod(np.arctan2(gradient_y, gradient_x), np.pi)
    histogram, _ = np.histogram(
        angle,
        bins=ORIENTATION_BINS,
        range=(0.0, np.pi),
        weights=magnitude,
    )
    total = float(histogram.sum())
    if total <= 0:
        return np.zeros(ORIENTATION_BINS, dtype=np.float32)
    return (histogram / total).astype(np.float32)


def _hog_features(gray: np.ndarray) -> np.ndarray:
    resized = cv2.resize(gray, (HOG_SIZE, HOG_SIZE), interpolation=cv2.INTER_AREA)
    vector = hog(
        resized,
        orientations=9,
        pixels_per_cell=(HOG_CELL, HOG_CELL),
        cells_per_block=(2, 2),
        block_norm="L2-Hys",
        feature_vector=True,
    )
    if vector.shape != (HOG_DIM,):
        raise FeatureError(f"HOG 维度异常: {vector.shape}")
    return vector.astype(np.float32)


def extract_features(image: np.ndarray) -> np.ndarray:
    """提取 1836 维特征向量。

    Args:
        image: BGR 或灰度 uint8 图像，短边不小于 32。

    Returns:
        形状为 (1836,) 的 float32 向量。

    Raises:
        FeatureError: 图像类型、尺寸或维度不符合约定。
    """
    gray = _to_gray(image)
    vector = np.concatenate(
        [
            _density_features(gray),
            _orientation_features(gray),
            _hog_features(gray),
        ]
    ).astype(np.float32)
    if vector.shape != (FEATURE_DIM,):
        raise FeatureError(f"特征维度异常: {vector.shape}")
    return vector
