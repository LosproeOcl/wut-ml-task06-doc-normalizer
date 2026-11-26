"""图像读取模块的单元测试。

预期形状与像素值均为手写字面量，独立于被测代码推导。
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from docnorm.data.loader import LoaderError, load_image


def make_rgb(path: Path, size=(40, 20), color=(255, 0, 0)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def test_reads_rgb_and_returns_bgr(tmp_path):
    # 破坏方式：通道顺序写反会让红色样本读成蓝色，影响后续颜色特征
    path = make_rgb(tmp_path / "red.png")
    loaded = load_image(path)
    assert loaded.image.shape == (20, 40, 3)
    assert loaded.image.dtype == np.uint8
    assert loaded.image[0, 0].tolist() == [0, 0, 255]


def test_applies_exif_orientation(tmp_path):
    # 破坏方式：忽略 EXIF 方向会让手机竖拍样本横躺，四角定位随之失效
    path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6  # 顺时针旋转 90 度
    Image.new("RGB", (40, 20), (10, 20, 30)).save(path, exif=exif)
    loaded = load_image(path)
    assert loaded.image.shape[:2] == (40, 20)


def test_resizes_long_edge_keeping_ratio(tmp_path):
    # 破坏方式：不限制尺寸会让大图直接进入训练，内存与耗时不可控（NFR-01）
    path = make_rgb(tmp_path / "wide.jpg", size=(200, 100))
    loaded = load_image(path, max_long_edge=64)
    assert loaded.image.shape[:2] == (32, 64)
    assert loaded.original_size == (200, 100)


def test_keeps_small_image_untouched(tmp_path):
    # 破坏方式：无条件缩放会放大小图，引入插值伪影
    path = make_rgb(tmp_path / "small.png", size=(30, 20))
    loaded = load_image(path, max_long_edge=64)
    assert loaded.image.shape[:2] == (20, 30)
    assert loaded.scale == 1.0


def test_grayscale_converted_to_three_channels(tmp_path):
    # 破坏方式：灰度图保持单通道会让依赖三通道的模型与绘图失败
    path = tmp_path / "gray.png"
    Image.new("L", (10, 10), 128).save(path)
    loaded = load_image(path)
    assert loaded.image.shape == (10, 10, 3)
    assert loaded.image[0, 0].tolist() == [128, 128, 128]


def test_rgba_converted_without_alpha(tmp_path):
    # 破坏方式：保留 alpha 会让数组维度与契约不符
    path = tmp_path / "alpha.png"
    Image.new("RGBA", (10, 10), (1, 2, 3, 255)).save(path)
    loaded = load_image(path)
    assert loaded.image.shape == (10, 10, 3)
    assert loaded.image[0, 0].tolist() == [3, 2, 1]


def test_supports_unicode_path(tmp_path):
    # 破坏方式：字符串路径拼接在 Windows 与中文目录下易失败
    path = make_rgb(tmp_path / "课堂 照片.jpg")
    assert load_image(path).image.shape[0] == 20


def test_missing_file_raises_loader_error(tmp_path):
    # 破坏方式：文件缺失返回空数组会让失败样本静默进入统计
    with pytest.raises(LoaderError, match="不存在"):
        load_image(tmp_path / "absent.jpg")


def test_corrupt_file_raises_loader_error(tmp_path):
    # 破坏方式：损坏文件抛裸异常会中断批处理且难以定位
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"not an image")
    with pytest.raises(LoaderError, match="无法解码"):
        load_image(path)
