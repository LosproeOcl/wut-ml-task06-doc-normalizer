"""数据划分的单元测试：分组不泄漏、完整性、确定性。"""

from __future__ import annotations

from docnorm.data.manifest import Manifest, ManifestRow
from docnorm.data.split import make_split, validate_split


def _row(sample_id, label, page, shooter="zyz"):
    return ManifestRow(
        sample_id=sample_id,
        file=f"{label}/{sample_id}.jpg",
        label=label,
        doc_page_id=page,
        shooter=shooter,
        device="iPhone Air",
        scene="classroom",
        angle_deg=30,
        lighting="ceiling",
        resolution="4032x3024",
        shot_at="2026-11-25",
        notes="",
        privacy_masked=False,
        privacy_regions=0,
        release_file="",
    )


def _manifest():
    # 12 个页面：6 个文字、6 个公式；文字页由 zyz 拍摄，公式页由 wkw 拍摄。
    rows = []
    for i in range(6):
        rows.append(_row(f"t{i}a", "ppt_text", f"PT-{i}", shooter="zyz"))
        rows.append(_row(f"t{i}b", "ppt_text", f"PT-{i}", shooter="zyz"))
    for i in range(6):
        rows.append(_row(f"f{i}a", "ppt_formula", f"PF-{i}", shooter="wkw"))
        rows.append(_row(f"f{i}b", "ppt_formula", f"PF-{i}", shooter="wkw"))
    return Manifest(rows)


def test_no_page_leaks_across_splits():
    split = make_split(_manifest())
    groups = split["groups"]
    train, val, test = set(groups["train"]), set(groups["val"]), set(groups["test"])
    assert train.isdisjoint(val)
    assert train.isdisjoint(test)
    assert val.isdisjoint(test)


def test_all_pages_assigned_exactly_once():
    manifest = _manifest()
    split = make_split(manifest)
    assigned = (
        split["groups"]["train"] + split["groups"]["val"] + split["groups"]["test"]
    )
    assert sorted(assigned) == sorted(manifest.page_ids())


def test_deterministic_with_same_seed():
    assert make_split(_manifest(), seed=42) == make_split(_manifest(), seed=42)


def test_validate_split_reports_nothing_for_clean_split():
    manifest = _manifest()
    split = make_split(manifest)
    assert validate_split(split, manifest) == []


def test_excluded_samples_not_assigned():
    manifest = _manifest()
    manifest.rows.append(
        ManifestRow(
            sample_id="ex",
            file="99_unlabeled/ex.jpg",
            label="",
            doc_page_id="",
            shooter="",
            device="",
            scene="",
            angle_deg=0,
            lighting="",
            resolution="",
            shot_at="",
            notes="排除：内容存疑待裁定",
            privacy_masked=False,
            privacy_regions=0,
            release_file="",
        )
    )
    split = make_split(manifest)
    assert split["excluded_samples"] == 1
    assert split["counts"]["train"] + split["counts"]["val"] + split["counts"]["test"] == 24


def test_validate_split_detects_leak():
    manifest = _manifest()
    split = make_split(manifest)
    # 人为制造泄漏：把 train 的一个页面也塞进 test。
    split["groups"]["test"].append(split["groups"]["train"][0])
    problems = validate_split(split, manifest)
    assert any("多个集合" in p for p in problems)
