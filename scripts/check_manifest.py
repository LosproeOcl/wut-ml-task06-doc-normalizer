#!/usr/bin/env python
"""校验样本清单字段、唯一性与类别分布。

用法：
    python scripts/check_manifest.py data/manifests/sample_manifest.csv
    python scripts/check_manifest.py data/manifests/sample_manifest.csv --json

失败（存在阻断错误）时返回非零退出码。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许直接从仓库根目录运行脚本时导入 src 下的包（尚未打包安装）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docnorm.data.manifest import parse_manifest, validate  # noqa: E402


def _report_to_dict(report) -> dict:
    return {
        "ok": report.ok,
        "n_rows": report.n_rows,
        "n_included": report.n_included,
        "n_excluded": report.n_excluded,
        "errors": report.errors,
        "warnings": report.warnings,
        "content_counts": report.content_counts,
        "carrier_counts": report.carrier_counts,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="校验样本清单")
    parser.add_argument("manifest", help="样本清单 CSV 路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)

    manifest = parse_manifest(args.manifest)
    report = validate(manifest)

    if args.json:
        print(json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2))
    else:
        print(f"样本总数：{report.n_rows}（纳入 {report.n_included}，排除 {report.n_excluded}）")
        print(f"内容分布：文字 {report.content_counts.get('text', 0)}，"
              f"公式 {report.content_counts.get('formula', 0)}")
        print(f"载体分布：幕布 {report.carrier_counts.get('ppt', 0)}，"
              f"纸质/板书 {report.carrier_counts.get('paper', 0)}")
        for e in report.errors:
            print(f"[错误] {e}")
        for w in report.warnings:
            print(f"[警告] {w}")
        print(f"\n结论：{'通过' if report.ok else f'存在 {len(report.errors)} 个阻断错误'}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
