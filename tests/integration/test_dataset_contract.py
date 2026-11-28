"""真实数据集契约的集成测试。

校验清单、排除表、冻结划分与磁盘文件四者一致。该测试用于阻止
"清单登记但文件缺失" 一类的缺陷进入训练阶段。
"""
from pathlib import Path

import pytest

from docnorm.data.manifest import find_missing_files, load_manifest
from docnorm.data.split import assign_samples, check_manifest_hash, load_split

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/manifests/sample_manifest.csv"
MANIFEST_V5 = ROOT / "data/manifests/sample_manifest_v5.csv"
EXCLUSIONS = ROOT / "data/manifests/exclusions.csv"
SPLIT = ROOT / "data/splits/split_v4.json"
SPLIT_V5 = ROOT / "data/splits/split_v5.json"
RAW = ROOT / "data/raw_samples"


def test_frozen_dataset_contract():
    samples = load_manifest(MANIFEST, exclusions_path=EXCLUSIONS)
    split = load_split(SPLIT)

    assert len(samples) == 442
    assert split.counts == {"train": 338, "val": 51, "test": 53}
    assert check_manifest_hash(split, MANIFEST)
    assert find_missing_files(samples, RAW) == []

    mapping = assign_samples(split, samples)
    actual = {
        name: sum(1 for value in mapping.values() if value == name)
        for name in ("train", "val", "test")
    }
    assert actual == split.counts


@pytest.mark.requires_dataset
def test_v5_dataset_contract():
    samples = load_manifest(MANIFEST_V5, exclusions_path=EXCLUSIONS)
    split = load_split(SPLIT_V5)

    assert len(samples) == 472
    assert split.version == "v5"
    assert split.manifest == "data/manifests/sample_manifest_v5.csv"
    assert split.counts == {"train": 349, "val": 51, "test": 72}
    assert check_manifest_hash(split, MANIFEST_V5)
    missing = find_missing_files(samples, RAW)
    # 外部测试图不随提交包分发（只保留清单与来源），文件存在性只要求自采部分
    assert [path for path in missing if not path.startswith("external-assets/")] == []

    mapping = assign_samples(split, samples)
    actual = {
        name: sum(1 for value in mapping.values() if value == name)
        for name in ("train", "val", "test")
    }
    assert actual == split.counts

    external = [sample for sample in samples if sample.shooter == "external"]
    assert len(external) == 30
    assert all(mapping[sample.sample_id] == "test" for sample in external)
    assert all(sample.content_label == "text" for sample in external)
