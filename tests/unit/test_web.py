"""网页接口的契约测试。

使用 FastAPI TestClient，不启动真实服务器。标注写入临时文件。
"""
from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

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

    samples = client.get("/api/samples?limit=3")
    assert samples.status_code == 200
    payload = samples.json()
    assert payload["total"] > 0
    assert len(payload["items"]) == 3


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
    for stage in ("original", "quad", "rectified", "enhanced"):
        assert client.get(f"/api/results/{result['result_id']}/{stage}").status_code == 200
        assert client.get(f"/api/results/{result['result_id']}/{stage}.png").status_code == 200


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
