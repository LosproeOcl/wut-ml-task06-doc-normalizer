"""生成 GitHub Pages 静态演示数据。

从本机运行中的 webapp 取预计算样张，压缩为适合 Pages 的尺寸。
只选择无个人信息的课程样张；不包含标注接口与原始清单路径。

用法：
    python3 scripts/build_pages_demo.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DEMO = SITE / "demo"
API = "http://127.0.0.1:54312"

SAMPLES = [
    ("formula_14", "纸质公式页 A", "paper"),
    ("formula_12", "纸质公式页 B", "paper"),
    ("formula_11", "纸质公式页 C", "paper"),
    ("IMG_20261126_021834", "纸质文字页 A", "paper"),
    ("IMG_20261126_021846", "纸质文字页 B", "paper"),
    ("IMG_4598", "PPT 公式页 A", "ppt"),
]

STAGES = ("original", "quad", "rectified", "scan")


def save_resized(source: Path, target: Path, max_edge: int = 1080, quality: int = 86) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGB")
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        image.save(target, "JPEG", quality=quality, optimize=True)


def main() -> int:
    if DEMO.exists():
        shutil.rmtree(DEMO)
    DEMO.mkdir(parents=True, exist_ok=True)
    items = []
    for sample_id, display, kind in SAMPLES:
        response = requests.post(
            f"{API}/api/analyze",
            data={"sample_id": sample_id, "rectify": "true", "enhance": "false"},
            timeout=120,
        )
        response.raise_for_status()
        result = response.json()
        slug = f"{kind}-{len(items) + 1:02d}"
        source_dir = ROOT / "web/results" / result["result_id"]
        target_dir = DEMO / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        for stage in STAGES:
            save_resized(source_dir / f"{stage}.png", target_dir / f"{stage}.jpg")
        meta = {
            "slug": slug,
            "display": display,
            "kind": kind,
            "label": result.get("label"),
            "carrier": result.get("carrier"),
            "branch": result.get("branch"),
            "probabilities": result.get("probabilities"),
            "carrier_probabilities": result.get("carrier_probabilities"),
            "runtime_ms": result.get("runtime_ms"),
            "status": result.get("status"),
            "images": {stage: f"demo/{slug}/{stage}.jpg" for stage in STAGES},
        }
        (target_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        items.append(meta)
        print(f"{slug}: {display} -> {result.get('label')} / {result.get('branch')}")

    (DEMO / "index.json").write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    figures = SITE / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    for name in ("eval_pipeline_comparison.png", "eval_confusion_matrices.png"):
        source = ROOT / "reports/figures" / name
        if source.is_file():
            shutil.copy2(source, figures / name)
    print(f"写入 {DEMO}，共 {len(items)} 个样张")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
