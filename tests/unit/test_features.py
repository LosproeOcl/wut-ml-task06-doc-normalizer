"""传统特征的单元测试。

特征维度由契约固定，测试使用手写字面量，避免从实现反推。
"""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from docnorm.features.classic import FeatureError, extract_features

EXPECTED_DIM = 64 + 8 + 1764


def make_page(with_text=True):
    image = np.full((320, 240, 3), 240, dtype=np.uint8)
    if with_text:
        for y in range(30, 290, 24):
            cv2.line(image, (20, y), (220, y), (30, 30, 30), 4)
    return image


def test_feature_dimension_is_fixed():
    # 破坏方式：维度变化会让已训练模型与评估脚本失配
    vector = extract_features(make_page())
    assert vector.shape == (EXPECTED_DIM,)
    assert vector.dtype == np.float32


def test_text_page_has_higher_density_than_blank():
    # 破坏方式：密度特征未按网格统计时，文字页与空白页无法区分
    text = extract_features(make_page(True))[:64]
    blank = extract_features(make_page(False))[:64]
    assert text.mean() > blank.mean()
    assert blank.max() == 0.0


def test_edge_histogram_is_normalized():
    # 破坏方式：不归一化会让不同分辨率样本的幅值不可比
    vector = extract_features(make_page(True))
    histogram = vector[64:72]
    assert histogram.sum() == pytest.approx(1.0, abs=1e-5)


def test_different_pages_produce_different_vectors():
    # 破坏方式：特征退化为常量会让分类器无法学习
    first = extract_features(make_page(True))
    second = extract_features(make_page(False))
    assert not np.allclose(first, second)


def test_grayscale_input_supported():
    # 破坏方式：只接受三通道会让已灰度化的流程无法复用
    gray = cv2.cvtColor(make_page(True), cv2.COLOR_BGR2GRAY)
    assert extract_features(gray).shape == (EXPECTED_DIM,)


def test_deterministic_output():
    # 破坏方式：引入随机采样会让同一输入产生不同特征
    image = make_page(True)
    assert np.array_equal(extract_features(image), extract_features(image))


def test_invalid_image_rejected():
    # 破坏方式：空数组或非 uint8 输入进入特征提取会产生无意义结果
    with pytest.raises(FeatureError):
        extract_features(np.zeros((0, 0, 3), dtype=np.uint8))
    with pytest.raises(FeatureError):
        extract_features(np.full((20, 20, 3), 0.5, dtype=np.float32))
