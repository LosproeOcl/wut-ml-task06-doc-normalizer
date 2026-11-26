"""清单解析与校验的单元测试。

预期值均为手写字面量，独立于被测代码推导。
"""
import textwrap

import pytest

from docnorm.data.manifest import ManifestError, load_manifest

HEADER = (
    "sample_id,file,label,doc_page_id,shooter,device,scene,angle_deg,"
    "lighting,resolution,shot_at,notes,privacy_masked,privacy_regions,release_file"
)


def write_csv(tmp_path, rows, name="manifest.csv"):
    p = tmp_path / name
    p.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p


ROW_A = "s1,01_ppt_text/a.jpg,ppt_text,PPT-001,yyq,iPhone Air,classroom,35,ceiling,4032x3024,2026-11-25,,false,0,"
ROW_B = "s2,04_paper_formula/b.jpg,paper_formula,PAPER-002,zsz,REDMI Turbo 5,dorm,20,side_lamp,3072x4096,2026-11-26,反光,true,1,release/04_paper_formula/b.jpg"


def test_load_valid_manifest_returns_typed_samples(tmp_path):
    # 破坏方式：字段解析错误（angle 不为 int、布尔为字符串）或行丢失
    p = write_csv(tmp_path, [ROW_A, ROW_B])
    samples = load_manifest(p)
    assert len(samples) == 2
    a = samples[0]
    assert a.sample_id == "s1"
    assert a.label == "ppt_text"
    assert a.content_label == "text"
    assert a.angle_deg == 35
    assert a.privacy_masked is False
    b = samples[1]
    assert b.content_label == "formula"
    assert b.privacy_masked is True
    assert b.privacy_regions == 1


def test_duplicate_sample_id_rejected(tmp_path):
    # 破坏方式：去掉唯一性校验后，重复标识会造成划分与评估串样
    p = write_csv(tmp_path, [ROW_A, ROW_A])
    with pytest.raises(ManifestError, match="s1"):
        load_manifest(p)


def test_missing_required_field_rejected_with_row_number(tmp_path):
    # 破坏方式：必填校验缺失会让空场景样本混入统计
    bad = ROW_A.replace(",classroom,", ",,")
    p = write_csv(tmp_path, [bad])
    with pytest.raises(ManifestError, match="2"):
        load_manifest(p)


def test_invalid_scene_enum_rejected(tmp_path):
    # 破坏方式：枚举校验缺失会放行非法场景值
    bad = ROW_A.replace(",classroom,", ",hallway,")
    p = write_csv(tmp_path, [bad])
    with pytest.raises(ManifestError, match="scene"):
        load_manifest(p)


def test_angle_out_of_range_rejected(tmp_path):
    # 破坏方式：范围校验缺失会放行 120 度这类非法倾角
    bad = ROW_A.replace(",35,", ",120,")
    p = write_csv(tmp_path, [bad])
    with pytest.raises(ManifestError, match="angle_deg"):
        load_manifest(p)


def test_empty_label_allowed_and_maps_to_none(tmp_path):
    # 破坏方式：把存疑样本的空标签当错误拒绝，或误映射成 text
    row = ROW_A.replace(",ppt_text,", ",,")
    p = write_csv(tmp_path, [row])
    samples = load_manifest(p)
    assert samples[0].label == ""
    assert samples[0].content_label is None


def test_unlabeled_marker_label_allowed_and_maps_to_none(tmp_path):
    # 破坏方式：拒绝 99_unlabeled 标记会让存疑样本无法登记（docs/04 第 3 节）
    row = ROW_A.replace(",ppt_text,", ",99_unlabeled,")
    p = write_csv(tmp_path, [row])
    samples = load_manifest(p)
    assert samples[0].label == "99_unlabeled"
    assert samples[0].content_label is None


def test_exclusions_remove_listed_samples(tmp_path):
    # 破坏方式：忽略排除表会让含个人信息样本进入训练评估（D-01）
    p = write_csv(tmp_path, [ROW_A, ROW_B])
    ex = tmp_path / "exclusions.csv"
    ex.write_text("sample_id,reason\ns2,personal_info\n", encoding="utf-8")
    samples = load_manifest(p, exclusions_path=ex)
    assert [s.sample_id for s in samples] == ["s1"]


def test_exclusion_of_unknown_id_rejected(tmp_path):
    # 破坏方式：排除表引用不存在样本时静默忽略，掩盖清单与排除表脱节
    p = write_csv(tmp_path, [ROW_A])
    ex = tmp_path / "exclusions.csv"
    ex.write_text("sample_id,reason\nghost,personal_info\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="ghost"):
        load_manifest(p, exclusions_path=ex)