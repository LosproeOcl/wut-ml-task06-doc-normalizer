#!/usr/bin/env python
"""校验样本清单字段、唯一性、分组与类别分布。

在 PR #1「实现数据层」的清单校验思路基础上，按当前数据契约重写；
只读取清单与排除表，不修改任何数据。

用法：
    python scripts/check_manifest.py
    python scripts/check_manifest.py data/manifests/sample_manifest.csv --json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docnorm.data.manifest import (  # noqa: E402
    FIELDS,
    LABEL_TO_CONTENT,
    LIGHTINGS,
    REQUIRED,
    SCENES,
    find_missing_files,
    load_manifest,
)

RESOLUTION_RE = re.compile(r"^(\d+)x(\d+)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CARRIER_MIN_RATIO = 0.25
CONTENT_RATIO_RANGE = (0.4, 0.6)
CONTENT_MIN_COUNT = 80
MAX_VIEWS_PER_PAGE = 6


def _read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(FIELDS):
                errors.append(f"表头与契约不一致: {reader.fieldnames}")
            rows = list(reader)
    except OSError as exc:
        errors.append(f"无法读取清单: {exc}")
        return [], errors
    return rows, errors


def _excluded_ids(path: Path | None) -> tuple[set[str], list[str]]:
    if path is None or not path.is_file():
        return set(), []
    errors: list[str] = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["sample_id", "reason"]:
                errors.append(f"排除表表头应为 sample_id,reason: {reader.fieldnames}")
            return {row["sample_id"] for row in reader if row.get("sample_id")}, errors
    except OSError as exc:
        return set(), [f"无法读取排除表: {exc}"]


def validate_manifest(
    path: Path,
    *,
    exclusions_path: Path | None = None,
    root: Path | None = None,
    check_files: bool = True,
) -> dict:
    """校验清单并返回机器可读报告，不抛出首个错误。"""
    rows, errors = _read_rows(path)
    excluded, exclusion_errors = _excluded_ids(exclusions_path)
    errors.extend(exclusion_errors)
    warnings: list[str] = []
    seen: set[str] = set()
    qualified: list[dict[str, str]] = []
    page_labels: dict[str, set[str]] = defaultdict(set)

    for row_no, row in enumerate(rows, start=2):
        for field in REQUIRED:
            if not (row.get(field) or "").strip():
                errors.append(f"第 {row_no} 行必填字段为空: {field}")
        sid = row.get("sample_id", "").strip()
        if not sid:
            continue
        if sid in seen:
            errors.append(f"第 {row_no} 行 sample_id 重复: {sid}")
        seen.add(sid)
        if row.get("scene") not in SCENES:
            errors.append(f"第 {row_no} 行 scene 取值非法: {row.get('scene')}")
        if row.get("lighting") not in LIGHTINGS:
            errors.append(f"第 {row_no} 行 lighting 取值非法: {row.get('lighting')}")
        try:
            angle = int(row.get("angle_deg", ""))
            if not 0 <= angle <= 90:
                errors.append(f"第 {row_no} 行 angle_deg 超出 0 至 90: {angle}")
        except ValueError:
            errors.append(f"第 {row_no} 行 angle_deg 非整数: {row.get('angle_deg')!r}")
        label = row.get("label", "")
        if label and label not in LABEL_TO_CONTENT and label != "99_unlabeled":
            errors.append(f"第 {row_no} 行 label 取值非法: {label}")
        if row.get("privacy_masked") not in {"true", "false"}:
            errors.append(f"第 {row_no} 行 privacy_masked 取值非法: {row.get('privacy_masked')!r}")
        try:
            int(row.get("privacy_regions", ""))
        except ValueError:
            errors.append(f"第 {row_no} 行 privacy_regions 非整数")
        if not RESOLUTION_RE.fullmatch(row.get("resolution", "")):
            errors.append(f"第 {row_no} 行 resolution 格式非法: {row.get('resolution')!r}")
        if not DATE_RE.fullmatch(row.get("shot_at", "")):
            errors.append(f"第 {row_no} 行 shot_at 格式非法: {row.get('shot_at')!r}")
        if sid in excluded:
            continue
        if label == "99_unlabeled" or not label:
            warnings.append(f"第 {row_no} 行标签待裁定: {sid}")
        if "排除" in (row.get("notes") or ""):
            warnings.append(f"第 {row_no} 行 notes 含排除标记: {sid}")
        qualified.append(row)
        if row.get("doc_page_id"):
            page_labels[row["doc_page_id"]].add(label)

    unknown_excluded = sorted(excluded - seen)
    if unknown_excluded:
        errors.append(f"排除表引用未知样本: {unknown_excluded}")

    for page_id, labels in sorted(page_labels.items()):
        labels = {label for label in labels if label}
        if len(labels) > 1:
            errors.append(f"同一文档页存在多种内容标签: {page_id} -> {sorted(labels)}")
    page_counts = Counter(row.get("doc_page_id", "") for row in qualified)
    for page_id, count in sorted(page_counts.items()):
        if count > MAX_VIEWS_PER_PAGE:
            warnings.append(f"同一文档页拍摄角度超过 {MAX_VIEWS_PER_PAGE} 个: {page_id} ({count})")

    content_counts = Counter(
        LABEL_TO_CONTENT[row.get("label", "")] for row in qualified if row.get("label") in LABEL_TO_CONTENT
    )
    carrier_counts = Counter(
        row.get("label", "").split("_")[0]
        for row in qualified
        if row.get("label", "").startswith(("ppt_", "paper_"))
    )
    total = sum(content_counts.values())
    if total:
        for name in ("text", "formula"):
            count = content_counts.get(name, 0)
            ratio = count / total
            if count < CONTENT_MIN_COUNT:
                warnings.append(f"{name} 类样本不足 {CONTENT_MIN_COUNT} 张: {count}")
            if not CONTENT_RATIO_RANGE[0] <= ratio <= CONTENT_RATIO_RANGE[1]:
                warnings.append(f"{name} 类占比 {ratio:.1%} 超出 40%–60%")
        paper_ratio = carrier_counts.get("paper", 0) / max(1, sum(carrier_counts.values()))
        if paper_ratio < CARRIER_MIN_RATIO:
            warnings.append(f"纸质/板书占比 {paper_ratio:.1%} 低于 25%")

    missing: list[str] = []
    if check_files and root is not None:
        try:
            samples = load_manifest(path, exclusions_path=exclusions_path)
            missing = find_missing_files(samples, root)
        except (OSError, ValueError) as exc:
            errors.append(f"文件核验失败: {exc}")
        if missing:
            errors.append(f"清单记录但文件缺失: {len(missing)} 个")

    return {
        "ok": not errors,
        "manifest": str(path),
        "exclusions": str(exclusions_path) if exclusions_path else None,
        "n_rows": len(rows),
        "n_qualified": len(qualified),
        "n_excluded": len(rows) - len(qualified),
        "content_counts": dict(content_counts),
        "carrier_counts": dict(carrier_counts),
        "missing_files": missing[:50],
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验样本清单字段、唯一性、分组与分布")
    parser.add_argument("manifest", nargs="?", default=str(ROOT / "data/manifests/sample_manifest.csv"))
    parser.add_argument(
        "--exclusions", default=str(ROOT / "data/manifests/exclusions.csv")
    )
    parser.add_argument("--root", default=str(ROOT / "data/raw_samples"))
    parser.add_argument("--no-files", action="store_true", help="不检查磁盘文件是否存在")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    exclusions = Path(args.exclusions) if args.exclusions else None
    report = validate_manifest(
        Path(args.manifest),
        exclusions_path=exclusions,
        root=Path(args.root),
        check_files=not args.no_files,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"清单：{report['manifest']}")
        print(
            f"记录 {report['n_rows']} 条，纳入 {report['n_qualified']}，"
            f"排除 {report['n_excluded']}"
        )
        print(f"内容：{report['content_counts']}")
        print(f"载体：{report['carrier_counts']}")
        for error in report["errors"]:
            print(f"[错误] {error}")
        for warning in report["warnings"]:
            print(f"[警告] {warning}")
        print("结论：通过" if report["ok"] else f"结论：{len(report['errors'])} 个阻断错误")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
