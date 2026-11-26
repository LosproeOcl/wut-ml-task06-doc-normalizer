"""构建外部辅助预训练清单。

只生成清单，不复制图片。外部图片仅用于预训练，不进入自采训练/验证/测试集。
许可与来源写入每一行，报告中必须披露。

用法：
    PYTHONPATH=src python scripts/build_external_dataset.py --formula 1200 --text 1200
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data/raw_samples/external-assets"
OUT = ROOT / "data/manifests/external_aux.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formula", type=int, default=1200)
    parser.add_argument("--text", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    rows = []

    formula_files = sorted((ASSETS / "im2latex-100k/images").glob("*.png"))
    if not formula_files:
        raise SystemExit("找不到 im2latex 公式图")
    for path in rng.sample(formula_files, min(args.formula, len(formula_files))):
        rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "label": "formula",
                "source": "im2latex-100k",
                "license": "CC0-1.0",
                "usage": "pretrain",
            }
        )

    tobacco = sorted((ASSETS / "tobacco3482/images").glob("*/*.jpg"))
    iam = sorted((ASSETS / "iam-handwriting-finevision/images").glob("*.png"))
    smartdoc = sorted((ASSETS / "smartdoc2015-ch1").glob("background*/*/frame_*.jpeg"))

    pools = [
        (tobacco, "tobacco3482", "research use; mirror Apache-2.0", 0.75),
        (iam, "iam-handwriting-finevision", "non-commercial research", 0.15),
        (smartdoc, "smartdoc2015-ch1", "CC BY 4.0", 0.10),
    ]
    for files, source, license_name, ratio in pools:
        if not files:
            continue
        count = int(round(args.text * ratio))
        for path in rng.sample(files, min(count, len(files))):
            rows.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "label": "text",
                    "source": source,
                    "license": license_name,
                    "usage": "pretrain",
                }
            )

    rng.shuffle(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["path", "label", "source", "license", "usage"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"写入 {args.out}，共 {len(rows)} 张")
    print("来源:", Counter(row["source"] for row in rows))
    print("标签:", Counter(row["label"] for row in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
