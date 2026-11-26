"""人工标签存储的单元测试。"""
import pytest

from docnorm.data.annotations import AnnotationError, ManualCornerStore, ManualLabelStore


def test_missing_file_returns_empty(tmp_path):
    store = ManualLabelStore(tmp_path / "labels.csv")
    assert store.load() == {}


def test_set_and_load_roundtrip(tmp_path):
    store = ManualLabelStore(tmp_path / "labels.csv")
    store.set("s1", "formula", annotator="tester")
    store.set("s2", "text", annotator="tester")
    assert store.load() == {"s1": "formula", "s2": "text"}
    text = (tmp_path / "labels.csv").read_text(encoding="utf-8")
    assert "annotator" in text
    assert "tester" in text


def test_invalid_label_rejected(tmp_path):
    store = ManualLabelStore(tmp_path / "labels.csv")
    with pytest.raises(AnnotationError, match="标签"):
        store.set("s1", "table", annotator="tester")


def test_corner_store_roundtrip_and_validation(tmp_path):
    store = ManualCornerStore(tmp_path / "corners.csv")
    points = [[10, 10], [100, 10], [100, 80], [10, 80]]
    store.set("s1", points, annotator="tester")
    assert store.load()["s1"] == points

    with pytest.raises(AnnotationError, match="4 个顶点"):
        store.set("s1", [[10, 10], [100, 10]], annotator="tester")
    with pytest.raises(AnnotationError, match="面积"):
        store.set(
            "s1",
            [[0, 0], [10, 0], [20, 0], [30, 0]],
            annotator="tester",
        )
