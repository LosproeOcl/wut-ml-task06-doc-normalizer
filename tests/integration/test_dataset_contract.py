"""真实数据集契约的集成测试。

校验清单、排除表、冻结划分与磁盘文件四者一致。该测试用于阻止
"清单登记但文件缺失" 一类的缺陷进入训练阶段。
"""
from pathlib import Path

from docnorm.data.manifest import find_missing_files, load_manifest
from docnorm.data.split import assign_samples, check_manifest_hash, load_split

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/manifests/sample_manifest.csv"
EXCLUSIONS = ROOT / "data/manifests/exclusions.csv"
SPLIT = ROOT / "data/splits/split_v2.json"
RAW = ROOT / "data/raw_samples"


def test_frozen_dataset_contract():
    samples = load_manifest(MANIFEST, exclusions_path=EXCLUSIONS)
    split = load_split(SPLIT)

    assert len(samples) == 344
    assert split.counts == {"train": 240, "val": 51, "test": 53}
    assert check_manifest_hash(split, MANIFEST)
    assert find_missing_files(samples, RAW) == []

    mapping = assign_samples(split, samples)
    actual = {
        name: sum(1 for value in mapping.values() if value == name)
        for name in ("train", "val", "test")
    }
    assert actual == split.counts
