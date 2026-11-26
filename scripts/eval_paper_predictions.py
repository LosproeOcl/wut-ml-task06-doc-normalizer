"""导出纸质稿验证集逐样本预测，供评估图与错误分析使用。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from scripts.train_cnn import build_transform  # noqa: E402
from scripts.train_paper_classifier import PaperDataset  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--input-size", type=int, default=224)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import yaml

    config = yaml.safe_load((ROOT / "configs/default.yaml").read_text(encoding="utf-8"))
    rows = [
        row
        for row in csv.DictReader((ROOT / args.manifest).open(encoding="utf-8"))
        if row["split"] == "val"
    ]
    models = [
        CnnClassifier.load(ROOT / path, device="cpu")
        for path in args.checkpoint
    ]
    dataset = PaperDataset(
        rows, config, build_transform(False, input_size=args.input_size), train=False
    )
    loader = DataLoader(dataset, batch_size=16, shuffle=False)
    probabilities = []
    labels = []
    with torch.no_grad():
        for images, targets in loader:
            batch = torch.zeros(len(images), len(CLASSES))
            for model in models:
                batch += torch.softmax(model.model(images), dim=1)
            probabilities.extend((batch / len(models)).numpy())
            labels.extend(targets.tolist())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "label", "pred", "prob_formula", "correct"])
        for row, probs, target in zip(rows, probabilities, labels):
            label = CLASSES[target]
            pred = CLASSES[int(probs.argmax())]
            writer.writerow(
                [
                    row.get("sample_id", ""),
                    label,
                    pred,
                    f"{float(probs[1]):.6f}",
                    int(pred == label),
                ]
            )
    print(f"写入 {args.out}，{len(rows)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
