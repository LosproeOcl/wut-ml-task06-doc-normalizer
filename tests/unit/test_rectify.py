"""文档四边形检测、顶点排序与透视变换的单元测试。

依赖 OpenCV；在未安装 OpenCV 的环境中整体跳过。
"""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from docnorm.rectify.detector import detect_document
from docnorm.rectify.geometry import DocumentQuad, RectifyError, order_quad
from docnorm.rectify.warp import warp_document

POINTS = np.array(
    [[40, 30], [200, 50], [190, 150], [20, 140]],
    dtype=np.float32,
)
SIZE = (240, 180)  # 宽, 高


def make_canvas(size=SIZE, color=30):
    width, height = size
    return np.full((height, width, 3), color, dtype=np.uint8)


def draw_document(points=POINTS, size=SIZE):
    image = make_canvas(size)
    cv2.fillPoly(image, [points.astype(np.int32)], (245, 245, 245))
    return image


def test_order_quad_normalizes_corner_order():
    # 破坏方式：不排序会让透视变换把图像翻转或拉伸
    shuffled = POINTS[[2, 0, 3, 1]]
    ordered = order_quad(shuffled)
    assert np.allclose(ordered, POINTS)


def test_order_quad_accepts_non_cyclic_click_order():
    # 破坏方式：手工按“左上→右下→右上→左下”点击会被误判为凹四边形
    bowtie = POINTS[[0, 2, 1, 3]]
    ordered = order_quad(bowtie)
    assert np.allclose(ordered, POINTS)


def test_order_quad_rejects_duplicate_points():
    # 破坏方式：重复顶点会让变换矩阵奇异，输出全黑
    bad = np.array([[10, 10], [10, 10], [100, 10], [100, 100]], dtype=np.float32)
    with pytest.raises(RectifyError, match="重复"):
        order_quad(bad)


def test_order_quad_rejects_collinear_points():
    # 破坏方式：面积为零或含共线顶点的四边形无法定义透视关系
    bad = np.array([[10, 10], [50, 10], [90, 10], [50, 20]], dtype=np.float32)
    with pytest.raises(RectifyError, match="共线"):
        order_quad(bad)


def test_order_quad_rejects_concave_quad():
    # 破坏方式：凹四边形不是文档轮廓，直接变换会折叠图像
    bad = np.array([[10, 10], [100, 10], [40, 40], [10, 100]], dtype=np.float32)
    with pytest.raises(RectifyError, match="凸"):
        order_quad(bad)


def test_detects_document_and_orders_corners():
    # 破坏方式：漏检、错检或顶点乱序都会使 FR-02 与 FR-03 不成立
    quad = detect_document(draw_document())
    assert quad is not None
    assert np.allclose(quad.points, POINTS, atol=4)
    expected_ratio = cv2.contourArea(POINTS.astype(np.int32)) / (SIZE[0] * SIZE[1])
    assert quad.area_ratio == pytest.approx(expected_ratio, abs=0.02)


def test_blank_image_returns_none():
    # 破坏方式：无文档时返回随机四边形会让批量处理产生假阳性
    assert detect_document(make_canvas()) is None


def test_too_small_quad_rejected():
    # 破坏方式：不对面积下限设限会把噪点当文档
    small = np.array([[100, 80], [130, 80], [130, 105], [100, 105]], dtype=np.float32)
    assert detect_document(draw_document(small)) is None


def test_full_frame_quad_rejected():
    # 破坏方式：整幅画面被当作文档会掩盖定位失败（面积上限 98%）
    image = np.full((SIZE[1], SIZE[0], 3), 245, dtype=np.uint8)
    assert detect_document(image) is None


def test_circle_is_not_a_quad():
    # 破坏方式：把任意轮廓近似成四边形会产生错误矫正
    image = make_canvas()
    cv2.circle(image, (120, 90), 60, (245, 245, 245), -1)
    assert detect_document(image) is None


def test_low_contrast_region_rejected():
    # 破坏方式：去掉边界对比度门槛会把墙面、桌面等弱边界区域当成文档
    image = np.full((SIZE[1], SIZE[0], 3), 120, dtype=np.uint8)
    cv2.rectangle(image, (60, 40), (180, 140), (126, 126, 126), -1)
    assert detect_document(image) is None


def test_warp_output_size_follows_quad():
    # 破坏方式：宽高取反会让矫正图旋转 90 度
    warped = warp_document(draw_document(), DocumentQuad(POINTS))
    expected_width = 170
    expected_height = 112
    assert abs(warped.shape[1] - expected_width) <= 2
    assert abs(warped.shape[0] - expected_height) <= 2


def test_warp_limits_long_edge():
    # 破坏方式：不限制输出尺寸会让大图占用过多内存
    warped = warp_document(draw_document(), DocumentQuad(POINTS), output_long_edge=100)
    assert max(warped.shape[:2]) == 100


def test_warp_preserves_corner_orientation():
    # 破坏方式：顶点顺序错误会让内容上下颠倒或左右镜像
    image = draw_document()
    colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0)]  # 左上红、右上绿、右下蓝
    for (x, y), color in zip(POINTS[:3], colors):
        cv2.rectangle(
            image,
            (int(x) - 8, int(y) - 8),
            (int(x) + 8, int(y) + 8),
            color,
            -1,
        )
    warped = warp_document(image, DocumentQuad(POINTS))
    height, width = warped.shape[:2]
    assert int(np.argmax(warped[8, 8])) == 2
    assert int(np.argmax(warped[8, width - 9])) == 1
    assert int(np.argmax(warped[height - 9, width - 9])) == 0
