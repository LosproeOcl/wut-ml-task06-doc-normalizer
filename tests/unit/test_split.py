"""划分加载与校验的单元测试。

预期值均为手写字面量，独立于被测代码推导。
"""
import hashlib
import json

import pytest

from docnorm.data.split import SplitError, assign_samples, check_manifest_hash, load_split

SPLIT_DOC = {
    "version": "v1",
    "seed": 42,
    "group_key": "doc_page_id",
    "ratio": {"train": 0.7, "val": 0.15, "test": 0.15},
    "groups": {"train": ["G1", "G2"], "val": ["G3"], "test": ["G4"]},
    "counts": {"train": 3, "val": 1, "test": 1},
    "frozen_at": "2026-11-26",
    "manifest_sha256": "0" * 64,
}


def write_split(tmp_path, doc=None):
    p = tmp_path / "split_v1.json"
    p.write_text(json.dumps(doc or SPLIT_DOC), encoding="utf-8")
    return p


class FakeSample:
    def __init__(self, sample_id, group):
        self.sample_id = sample_id
        self.doc_page_id = group


def test_load_split_returns_groups(tmp_path):
    # 破坏方式：解析丢组或串组会让样本进入错误集合
    sp = load_split(write_split(tmp_path))
    assert sp.groups["train"] == ["G1", "G2"]
    assert sp.groups["test"] == ["G4"]
    assert sp.seed == 42


def test_overlapping_groups_rejected(tmp_path):
    # 破坏方式：去掉互斥校验后同一文档页跨集合，指标虚高（R-02）
    doc = json.loads(json.dumps(SPLIT_DOC))
    doc["groups"]["val"] = ["G1"]
    with pytest.raises(SplitError, match="G1"):
        load_split(write_split(tmp_path, doc))


def test_manifest_hash_match_passes(tmp_path):
    # 破坏方式：哈希比对写反会让一致清单被拒
    mf = tmp_path / "m.csv"
    mf.write_bytes(b"sample_id,file\ns1,a.jpg\n")
    doc = json.loads(json.dumps(SPLIT_DOC))
    doc["manifest_sha256"] = hashlib.sha256(mf.read_bytes()).hexdigest()
    sp = load_split(write_split(tmp_path, doc))
    assert check_manifest_hash(sp, mf) is True


def test_manifest_hash_mismatch_rejected(tmp_path):
    # 破坏方式：跳过哈希校验会让改动后的清单沿用旧划分（R-10）
    mf = tmp_path / "m.csv"
    mf.write_bytes(b"changed\n")
    sp = load_split(write_split(tmp_path))
    with pytest.raises(SplitError, match="sha256"):
        check_manifest_hash(sp, mf)


def test_assign_samples_maps_group_to_set(tmp_path):
    # 破坏方式：按 sample_id 而非分组键映射会拆散同页样本
    sp = load_split(write_split(tmp_path))
    samples = [FakeSample("a", "G1"), FakeSample("b", "G1"), FakeSample("c", "G4")]
    mapping = assign_samples(sp, samples)
    assert mapping == {"a": "train", "b": "train", "c": "test"}


def test_assign_unknown_group_rejected(tmp_path):
    # 破坏方式：未知分组静默跳过会让新增样本漏出统计
    sp = load_split(write_split(tmp_path))
    with pytest.raises(SplitError, match="G9"):
        assign_samples(sp, [FakeSample("x", "G9")])