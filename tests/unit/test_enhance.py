"""增强模块的单元测试。

覆盖通道保持、对比度提升、色彩保持、光照校正、确定性与参数校验。
依赖 OpenCV；未安装时整体跳过。
"""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from docnorm.enhance.clahe import (
    EnhanceError,
    apply_clahe,
    correct_illumination,
    enhance_document,
)


def make_text_image(width=200, height=120):
    """浅灰背景加深色横条，模拟低对比度文字页。"""
    image = np.full((height, width, 3), 130, dtype=np.uint8)
    for y in range(20, height - 20, 20):
        cv2.line(image, (20, y), (width - 20, y), (105, 105, 105), 3)
    return image


def test_output_shape_and_dtype_preserved():
    # 破坏方式：转换过程改变尺寸或数据类型，会让后续模型输入契约失效
    image = make_text_image()
    result = apply_clahe(image)
    assert result.shape == image.shape
    assert result.dtype == np.uint8


def test_clahe_increases_local_contrast():
    # 破坏方式：参数无效或通道处理错误会导致低对比度文字仍然发灰
    image = make_text_image()
    before = float(image.std())
    after = float(apply_clahe(image, clip_limit=5.0).std())
    assert after > before * 1.1


def test_color_patch_keeps_dominant_channel():
    # 破坏方式：直接在 BGR 三通道上做均衡会让颜色偏移
    image = np.full((80, 80, 3), 90, dtype=np.uint8)
    image[:, :40] = (0, 0, 200)  # BGR 红色
    result = apply_clahe(image)
    patch = result[:, :30].reshape(-1, 3).mean(axis=0)
    assert patch[2] > patch[0] and patch[2] > patch[1]


def test_grayscale_input_returns_grayscale():
    # 破坏方式：强行扩成三通道会改变调用方约定
    image = cv2.cvtColor(make_text_image(), cv2.COLOR_BGR2GRAY)
    result = apply_clahe(image)
    assert result.ndim == 2
    assert result.shape == image.shape


def test_illumination_correction_flattens_gradient():
    # 破坏方式：不做背景估计时，侧向光照会让同一行文字亮度差异过大
    height, width = 120, 240
    gradient = np.tile(np.linspace(70, 190, width, dtype=np.float32), (height, 1))
    image = np.dstack([gradient, gradient, gradient]).astype(np.uint8)
    cv2.line(image, (20, 60), (220, 60), (45, 45, 45), 4)

    before = float(image[:, :, 0].std())
    corrected = correct_illumination(image, kernel_size=61, strength=1.0)
    after = float(corrected[:, :, 0].std())
    assert after < before * 0.75
    assert corrected[60, 100].mean() < corrected[5, 100].mean()


def test_enhance_document_is_deterministic():
    # 破坏方式：随机噪声或未固定状态会让同一输入的两次结果不同
    image = make_text_image()
    first = enhance_document(image)
    second = enhance_document(image)
    assert np.array_equal(first, second)


def test_invalid_clip_limit_rejected():
    # 破坏方式：非正对比度限值会让 CLAHE 行为不可预测
    with pytest.raises(EnhanceError, match="clip_limit"):
        apply_clahe(make_text_image(), clip_limit=0)


def test_invalid_kernel_size_rejected():
    # 破坏方式：偶数或过小的核会让形态学背景估计失败
    with pytest.raises(EnhanceError, match="kernel_size"):
        correct_illumination(make_text_image(), kernel_size=10)


def test_enhance_document_without_shadow_correction():
    # 破坏方式：开关失效会让消融实验无法比较增强前后
    image = make_text_image()
    result = enhance_document(image, correct_shadows=False, denoise=False)
    assert result.shape == image.shape
    assert result.dtype == np.uint8
