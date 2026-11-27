"""网页接口的契约测试。

使用 FastAPI TestClient，不启动真实服务器。标注写入临时文件。
"""
from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from web import services
from web.app import app

client = TestClient(app)


def make_png() -> bytes:
    image = Image.new("RGB", (480, 360), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 30, 440, 330), outline=(20, 20, 20), width=6)
    draw.text((80, 80), "test document", fill=(20, 20, 20))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_health_and_samples():
    # 破坏方式：服务启动但样本索引或模型状态不可读，前端无法初始化
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    routing = health.json()["routing"]
    assert "gate_threshold" in routing
    assert "gate_tta" in routing

    samples = client.get("/api/samples?limit=3")
    assert samples.status_code == 200
    payload = samples.json()
    assert payload["total"] > 0
    assert len(payload["items"]) == 3


@pytest.mark.requires_dataset
def test_sample_image_endpoint():
    # 破坏方式：样本标识未校验会暴露任意路径
    sample = client.get("/api/samples?limit=1").json()["items"][0]
    response = client.get(f"/api/samples/{sample['sample_id']}/image")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_analyze_upload_returns_stages():
    # 破坏方式：上传链路返回结构与前端契约不一致，页面无法展示
    response = client.post(
        "/api/analyze",
        files={"file": ("test.png", make_png(), "image/png")},
        data={"rectify": "true", "enhance": "false"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["result_id"]
    assert result["status"] in {"ok", "rectify_failed"}
    assert "carrier" in result and "branch" in result
    for stage in ("original", "quad", "rectified", "enhanced", "scan"):
        assert client.get(f"/api/results/{result['result_id']}/{stage}").status_code == 200
        assert client.get(f"/api/results/{result['result_id']}/{stage}.png").status_code == 200

    pdf = client.get(f"/api/pdf/{result['result_id']}?mode=scan")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")

    multi = client.post(
        "/api/pdf",
        json={"result_ids": [result["result_id"], result["result_id"]], "mode": "scan"},
    )
    assert multi.status_code == 200
    assert multi.content.startswith(b"%PDF")


def test_corner_update_accepts_manual_points():
    # 破坏方式：四角重算未接线会让交互兜底失效
    result = client.post(
        "/api/analyze",
        files={"file": ("test.png", make_png(), "image/png")},
        data={"rectify": "true", "enhance": "false"},
    ).json()
    points = [[40, 30], [440, 30], [440, 330], [40, 330]]
    response = client.post(
        f"/api/analyze/{result['result_id']}/corners", json={"points": points}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["quad"] == points


def test_upload_applies_exif_orientation():
    # 破坏方式：电脑原图带 EXIF 旋转，后端按未转正像素处理，方向与手机不一致
    image = Image.new("RGB", (480, 360), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 30, 440, 330), outline=(20, 20, 20), width=6)
    exif = Image.Exif()
    exif[274] = 6
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    response = client.post(
        "/api/analyze",
        files={"file": ("rotated.jpg", buffer.getvalue(), "image/jpeg")},
        data={"rectify": "false", "enhance": "false"},
    )
    assert response.status_code == 200
    result = response.json()
    assert (result["width"], result["height"]) == (360, 480)


def test_rectify_uses_carrier_specific_canny(monkeypatch):
    # 破坏方式：PPT 与纸质共用一组阈值，弱边缘纸质稿或强边缘幕布检出率下降
    calls = {}

    def fake_detect(image, **kwargs):
        calls.update(kwargs)
        return None

    monkeypatch.setattr(services, "detect_document", fake_detect)
    services._apply_rectify(np.zeros((64, 64, 3), dtype=np.uint8), "ppt")
    assert calls["canny_low"] == int(services.CONFIG["rectify"]["ppt_canny_low"])
    assert calls["canny_high"] == int(services.CONFIG["rectify"]["ppt_canny_high"])
    services._apply_rectify(np.zeros((64, 64, 3), dtype=np.uint8), "paper")
    assert calls["canny_low"] == int(services.CONFIG["rectify"]["paper_canny_low"])
    assert calls["canny_high"] == int(services.CONFIG["rectify"]["paper_canny_high"])


def test_rectify_quad_primary_skips_opencv(monkeypatch):
    # 破坏方式：quad_policy=primary 时仍先走 OpenCV，学习四角永远不生效
    from docnorm.rectify.geometry import DocumentQuad

    calls = {}

    def fake_predict(self, image):
        return DocumentQuad(
            np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype=np.float32),
            area_ratio=0.64,
            method="quad",
        )

    monkeypatch.setattr(services.QuadRegressor, "predict", fake_predict)
    monkeypatch.setattr(services, "_quad_policy", lambda: "primary")
    monkeypatch.setattr(
        services, "_quad_model", lambda carrier: services.QuadRegressor.__new__(services.QuadRegressor)
    )
    monkeypatch.setattr(
        services, "detect_document", lambda *a, **k: calls.setdefault("detect", True)
    )
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    _rectified, quad, status = services._apply_rectify(image, "ppt")
    assert status == "ok" and quad is not None and quad.method == "quad"
    assert "detect" not in calls


def test_rectify_quad_fallback_after_opencv_failure(monkeypatch):
    # 破坏方式：OpenCV 失败后没有学习四角兜底，页面仍显示 rectify_failed
    from docnorm.rectify.geometry import DocumentQuad

    monkeypatch.setattr(
        services.QuadRegressor,
        "predict",
        lambda self, image: DocumentQuad(
            np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype=np.float32),
            area_ratio=0.64,
            method="quad",
        ),
    )
    monkeypatch.setattr(services, "_quad_policy", lambda: "fallback")
    monkeypatch.setattr(
        services, "_quad_model", lambda carrier: services.QuadRegressor.__new__(services.QuadRegressor)
    )
    monkeypatch.setattr(services, "detect_document", lambda *a, **k: None)
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    _rectified, quad, status = services._apply_rectify(image, "ppt")
    assert status == "ok" and quad is not None and quad.method == "quad"


def test_pipeline_marks_uncertain_routing(monkeypatch):
    # 破坏方式：门控阈值附近仍显示为确定结果，用户无法发现潜在误判
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    monkeypatch.setattr(
        services, "_carrier_info", lambda original: ("ppt", {"ppt": 0.32, "paper": 0.68})
    )
    monkeypatch.setattr(
        services, "_apply_rectify", lambda array, carrier=None: (array, None, "ok")
    )
    monkeypatch.setattr(services, "_apply_scan", lambda array: array)
    monkeypatch.setattr(
        services,
        "_classify",
        lambda original, array, info=None: (
            "text",
            {"text": 0.4, "formula": 0.6},
            {"carrier": "ppt", "branch": "ppt-cnn", "carrier_probabilities": {"ppt": 0.32, "paper": 0.68}},
        ),
    )
    result = services.analyze_pipeline(image, rectify=True, enhance=False)
    assert result["routing"]["uncertain"] is True
    assert result["routing"]["gate_margin"] < 0.15


def test_pipeline_carrier_override(monkeypatch):
    # 破坏方式：手动“按 PPT 重试”仍被门控改回 paper
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    calls = {}
    monkeypatch.setattr(
        services, "_carrier_info", lambda original: ("paper", {"ppt": 0.05, "paper": 0.95})
    )

    def fake_rectify(array, carrier=None):
        calls["carrier"] = carrier
        return array, None, "ok"

    monkeypatch.setattr(services, "_apply_rectify", fake_rectify)
    monkeypatch.setattr(services, "_apply_scan", lambda array: array)
    monkeypatch.setattr(
        services,
        "_classify",
        lambda original, array, info=None: (
            "text",
            {"text": 0.9, "formula": 0.1},
            {"carrier": info[0] if info else "unknown", "branch": "ppt-cnn", "carrier_probabilities": {"ppt": 0.05, "paper": 0.95}},
        ),
    )
    result = services.analyze_pipeline(
        image, rectify=True, enhance=False, carrier_override="ppt"
    )
    assert calls["carrier"] == "ppt"
    assert result["routing"]["carrier"] == "ppt"
    assert result["routing"]["carrier_override"] is True


def test_oversized_pixels_rejected(monkeypatch):
    # 破坏方式：超大像素图进入完整解码会瞬间吃光内存，拖死整机
    monkeypatch.setattr(services, "MAX_DECODE_PIXELS", 1000)
    response = client.post(
        "/api/analyze",
        files={"file": ("huge.png", make_png(), "image/png")},
        data={"rectify": "true", "enhance": "false"},
    )
    assert response.status_code == 413


def test_invalid_upload_rejected():
    # 破坏方式：非图像内容进入解码链路会返回 500
    response = client.post(
        "/api/analyze",
        files={"file": ("bad.png", b"not an image", "image/png")},
        data={"rectify": "true", "enhance": "false"},
    )
    assert response.status_code == 400


def test_annotation_only_train_and_persists(tmp_path, monkeypatch):
    # 破坏方式：允许写验证集或用错标签会污染冻结划分与评估口径
    path = tmp_path / "manual_labels.csv"
    monkeypatch.setenv("DOCNORM_ANNOTATION_PATH", str(path))

    train = client.get("/api/annotations?limit=1").json()["items"][0]
    response = client.post(
        "/api/annotations",
        json={"sample_id": train["sample_id"], "label": "formula", "annotator": "test"},
    )
    assert response.status_code == 200
    assert response.json()["annotated"] >= 1
    assert path.is_file()
    assert "formula" in path.read_text(encoding="utf-8")

    val = client.get("/api/samples?split=val&limit=1").json()["items"][0]
    rejected = client.post(
        "/api/annotations",
        json={"sample_id": val["sample_id"], "label": "text", "annotator": "test"},
    )
    assert rejected.status_code == 403


def test_invalid_result_id_rejected():
    # 破坏方式：结果标识未做格式校验会带来目录穿越风险
    response = client.get("/api/results/../../etc/passwd/original")
    assert response.status_code in {404, 405}


@pytest.mark.requires_dataset
def test_corner_annotation_persists_only_for_train(tmp_path, monkeypatch):
    # 破坏方式：四角覆盖写入验证集会污染冻结评估；未接线则拖拽工具无效
    path = tmp_path / "manual_corners.csv"
    monkeypatch.setenv("DOCNORM_CORNER_PATH", str(path))

    payload = client.get("/api/corners?limit=1").json()
    item = payload["items"][0]
    assert item["sample_id"]
    points = [[40, 30], [440, 30], [440, 330], [40, 330]]
    response = client.post(
        "/api/corners",
        json={"sample_id": item["sample_id"], "points": points, "annotator": "test"},
    )
    assert response.status_code == 200
    assert response.json()["annotated"] >= 1
    assert path.is_file()

    val = client.get("/api/samples?split=val&limit=1").json()["items"][0]
    rejected = client.post(
        "/api/corners",
        json={
            "sample_id": val["sample_id"],
            "points": points,
            "annotator": "test",
        },
    )
    assert rejected.status_code == 403


@pytest.mark.requires_dataset
def test_assignee_filter_and_write_enforcement(tmp_path, monkeypatch):
    # 破坏方式：不按人筛选会让所有人面对全部样本；不校验会让任务分配失效
    monkeypatch.setenv("DOCNORM_CORNER_PATH", str(tmp_path / "manual_corners.csv"))
    members = client.get("/api/annotators").json()["members"]
    assert len(members) == 8
    first, second = members[0]["name"], members[1]["name"]

    payload = client.get(
        "/api/corners",
        params={"limit": 3, "only_unannotated": "false", "assignee": first},
    ).json()
    assert payload["items"]
    assert all(item["assignee"] == first for item in payload["items"])

    item = payload["items"][0]
    points = [[10, 10], [100, 10], [100, 80], [10, 80]]
    rejected = client.post(
        "/api/corners",
        json={"sample_id": item["sample_id"], "points": points, "annotator": second},
    )
    assert rejected.status_code == 403


@pytest.mark.requires_dataset
def test_review_send_back_and_resubmit(tmp_path, monkeypatch):
    # 破坏方式：退回后样本不进入重标队列，或不清理退回标记
    monkeypatch.setenv("DOCNORM_CORNER_PATH", str(tmp_path / "manual_corners.csv"))
    monkeypatch.setenv("DOCNORM_REDO_PATH", str(tmp_path / "redo_corners.csv"))
    item = client.get("/api/corners?limit=1").json()["items"][0]
    points = [[20, 20], [200, 20], [200, 160], [20, 160]]
    saved = client.post(
        "/api/corners",
        json={"sample_id": item["sample_id"], "points": points, "annotator": "test"},
    )
    assert saved.status_code == 200

    rejected = client.post(
        f"/api/review/corners/{item['sample_id']}/redo",
        json={"reason": "测试退回"},
    )
    assert rejected.status_code == 200
    listed = client.get("/api/review/corners", params={"status": "redo"}).json()
    assert any(entry["sample_id"] == item["sample_id"] for entry in listed["items"])

    resubmitted = client.post(
        "/api/corners",
        json={"sample_id": item["sample_id"], "points": points, "annotator": "test"},
    )
    assert resubmitted.status_code == 200
    again = client.get("/api/review/corners", params={"status": "redo"}).json()
    assert all(entry["sample_id"] != item["sample_id"] for entry in again["items"])
