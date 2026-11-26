"""图像增强：光照校正与对比度增强。"""
from docnorm.enhance.clahe import (
    EnhanceError,
    apply_clahe,
    correct_illumination,
    enhance_document,
)

__all__ = [
    "EnhanceError",
    "apply_clahe",
    "correct_illumination",
    "enhance_document",
]
