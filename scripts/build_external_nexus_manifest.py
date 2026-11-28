"""登记 SmartDoc 2015 Challenge 1 的 03-captured-nexus 外部测试样本。

这 30 张图只进入 split_v5 测试集，不参与训练。标签按项目类别规则判定：
页面以文字、表格、工程图为主，数学公式/推导占版面不足 5%，统一记为
paper_text。scene、lighting 与角度为估计值，清单 notes 中已注明。

用法：
    python scripts/build_external_nexus_manifest.py
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "data/raw_samples/external-assets/smartdoc2015-ch1/03-captured-nexus"
)
DEFAULT_OUT = ROOT / "data/manifests/external_nexus_test.csv"
FIELDS = (
    "sample_id", "file", "label", "doc_page_id", "shooter", "device", "scene",
    "angle_deg", "lighting", "resolution", "shot_at", "notes",
    "privacy_masked", "privacy_regions", "release_file",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = sorted(args.source.glob("*.jpg"))
    if not files:
        raise SystemExit(f"未找到外部测试图: {args.source}")

    rows = []
    for index, path in enumerate(files, start=1):
        with Image.open(path) as image:
            width, height = image.size
        rows.append(
            {
                "sample_id": f"EXT-NEXUS-{path.stem.upper()}",
                "file": str(path.relative_to(ROOT / "data/raw_samples")),
                "label": "paper_text",
                "doc_page_id": f"EXT-NEXUS-G{index:03d}",
                "shooter": "external",
                "device": "unknown",
                "scene": "dorm",
                "angle_deg": "15",
                "lighting": "ceiling",
                "resolution": f"{width}x{height}",
                "shot_at": "2014-07-09",
                "notes": (
                    "SmartDoc 2015 Challenge 1 / 03-captured-nexus；"
                    "外部测试样本；页面以文字、表格、工程图为主，"
                    "数学公式占比不足 5%，判为 paper_text；"
                    "scene/lighting/angle 为估计值"
                ),
                "privacy_masked": "false",
                "privacy_regions": "0",
                "release_file": "",
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"写入 {args.out}，共 {len(rows)} 张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
