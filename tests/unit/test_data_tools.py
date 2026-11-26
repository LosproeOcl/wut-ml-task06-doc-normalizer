"""数据层校验脚本的单元测试。"""
from __future__ import annotations

import csv

from docnorm.data.manifest import FIELDS
from scripts.check_dataset import check_dataset
from scripts.check_manifest import validate_manifest


def write_manifest(tmp_path, rows):
    path = tmp_path / "manifest.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    return path


def row(sample_id, label="ppt_text", page="P1", file=None):
    return {
        "sample_id": sample_id,
        "file": file or f"01_ppt_text/{sample_id}.jpg",
        "label": label,
        "doc_page_id": page,
        "shooter": "yqy",
        "device": "iPhone",
        "scene": "classroom",
        "angle_deg": "30",
        "lighting": "ceiling",
        "resolution": "1920x1080",
        "shot_at": "2026-11-27",
        "notes": "",
        "privacy_masked": "false",
        "privacy_regions": "0",
        "release_file": "",
    }


def test_validate_manifest_accepts_valid_rows(tmp_path):
    path = write_manifest(
        tmp_path,
        [row("s1", "ppt_text", "P1"), row("s2", "paper_formula", "P2")],
    )
    report = validate_manifest(path, check_files=False)
    assert report["ok"]
    assert report["n_rows"] == 2
    assert report["content_counts"] == {"text": 1, "formula": 1}


def test_validate_manifest_reports_duplicate_and_mixed_page(tmp_path):
    path = write_manifest(
        tmp_path,
        [
            row("s1", "ppt_text", "P1"),
            row("s1", "paper_formula", "P1"),
        ],
    )
    report = validate_manifest(path, check_files=False)
    assert not report["ok"]
    assert any("sample_id 重复" in error for error in report["errors"])
    assert any("多种内容标签" in error for error in report["errors"])


def test_validate_manifest_reports_unknown_exclusion(tmp_path):
    path = write_manifest(tmp_path, [row("s1")])
    exclusions = tmp_path / "exclusions.csv"
    exclusions.write_text("sample_id,reason\nmissing,personal_info\n", encoding="utf-8")
    report = validate_manifest(path, exclusions_path=exclusions, check_files=False)
    assert not report["ok"]
    assert any("排除表引用未知样本" in error for error in report["errors"])


def test_check_dataset_reports_missing_and_untracked(tmp_path):
    manifest = write_manifest(tmp_path, [row("s1")])
    root = tmp_path / "raw"
    target = root / "01_ppt_text" / "s1.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"image")
    extra = root / "01_ppt_text" / "extra.jpg"
    extra.write_bytes(b"extra")

    report = check_dataset(manifest, root=root, exclusions_path=None)
    assert report["ok"]
    assert report["untracked_files"] == ["01_ppt_text/extra.jpg"]

    target.unlink()
    missing = check_dataset(manifest, root=root, exclusions_path=None)
    assert not missing["ok"]
    assert missing["missing_files"] == ["01_ppt_text/s1.jpg"]
