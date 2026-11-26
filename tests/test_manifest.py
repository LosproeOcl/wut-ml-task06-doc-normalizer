"""样本清单解析与校验的单元测试。"""

from __future__ import annotations

import pytest

from docnorm.data.manifest import (
    Manifest,
    ManifestRow,
    parse_manifest,
    validate,
)


def _row(sample_id, label="ppt_text", page="P1", **overrides):
    defaults = dict(
        sample_id=sample_id,
        file=f"01_ppt_text/{sample_id}.jpg",
        label=label,
        doc_page_id=page,
        shooter="zyz",
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
    defaults.update(overrides)
    return ManifestRow(**defaults)


def _write_csv(tmp_path, rows):
    import csv

    path = tmp_path / "manifest.csv"
    columns = [
        "sample_id", "file", "label", "doc_page_id", "shooter", "device",
        "scene", "angle_deg", "lighting", "resolution", "shot_at", "notes",
        "privacy_masked", "privacy_regions", "release_file",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for r in rows:
            writer.writerow([
                r.sample_id, r.file, r.label, r.doc_page_id, r.shooter,
                r.device, r.scene, r.angle_deg, r.lighting, r.resolution,
                r.shot_at, r.notes, r.privacy_masked, r.privacy_regions,
                r.release_file,
            ])
    return path


def test_parse_and_validate_ok(tmp_path):
    rows = [
        _row("a", label="ppt_text", page="PT-1"),
        _row("b", label="paper_formula", page="AF-1"),
    ]
    manifest = parse_manifest(_write_csv(tmp_path, rows))
    report = validate(manifest)
    assert report.ok, report.errors
    assert report.n_included == 2


def test_duplicate_sample_id_is_error(tmp_path):
    rows = [_row("a"), _row("a")]
    report = validate(parse_manifest(_write_csv(tmp_path, rows)))
    assert any("sample_id 重复" in e for e in report.errors)
    assert not report.ok


def test_missing_doc_page_id_is_error(tmp_path):
    rows = [_row("a", page="")]
    report = validate(parse_manifest(_write_csv(tmp_path, rows)))
    assert any("doc_page_id 为空" in e for e in report.errors)


def test_invalid_enum_values(tmp_path):
    rows = [
        _row("a", label="bad_label"),
        _row("b", scene="beach"),
        _row("c", lighting="neon"),
    ]
    report = validate(parse_manifest(_write_csv(tmp_path, rows)))
    assert any("label" in e for e in report.errors)
    assert any("scene" in e for e in report.errors)
    assert any("lighting" in e for e in report.errors)


def test_excluded_by_marker(tmp_path):
    rows = [
        _row("a", page="PT-1"),
        _row("b", page="", notes="排除：含个人信息"),
    ]
    manifest = parse_manifest(_write_csv(tmp_path, rows))
    report = validate(manifest)
    assert report.n_included == 1
    assert report.n_excluded == 1
    # 被排除样本缺 doc_page_id 不应报错。
    assert report.ok


def test_quota_warning_when_unbalanced(tmp_path):
    # 9 张文字、1 张公式，明显失衡。
    rows = [_row(f"t{i}", label="ppt_text", page=f"PT-{i}") for i in range(9)]
    rows.append(_row("f0", label="ppt_formula", page="PF-0"))
    report = validate(parse_manifest(_write_csv(tmp_path, rows)))
    assert any("占比" in w for w in report.warnings)


def test_index_by_page_id():
    m = Manifest([_row("a", page="P1"), _row("b", page="P1"), _row("c", page="P2")])
    assert len(m.by_page_id("P1")) == 2
    assert m.by_sample_id("b").sample_id == "b"
