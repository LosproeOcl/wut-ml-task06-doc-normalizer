"""跨载体评估：纸质模型在 PPT 样本上的表现。

使用 5 折 CV 的纸质模型，在对应折的 PPT 验证样本上预测；另外用
paper-cnn-extctl 集成在原始 21 张 PPT 验证集上做部署式对照。
测试集不参与。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from docnorm.classify.cnn import CLASSES, CnnClassifier  # noqa: E402
from docnorm.data.loader import load_image  # noqa: E402
from docnorm.data.manifest import load_manifest  # noqa: E402
from docnorm.data.split import assign_samples, load_split  # noqa: E402
from web import services  # noqa: E402


def predict(models, image):
    """返回 3 个纸质模型平均后的 [P(text), P(formula)]。"""
    probs = []
    for model in models:
        tensor = model._prepare(image).unsqueeze(0)
        with torch.no_grad():
            probs.append(torch.softmax(model.model(tensor), dim=1)[0].cpu().numpy())
    return np.mean(probs, axis=0)


def load_models(paths):
    models = []
    for path in paths:
        if path.is_file():
            models.append(CnnClassifier.load(path, device="cpu"))
    return models


def metrics(labels, probs):
    pred = [CLASSES[int(np.argmax(p))] for p in probs]
    return {
        "n": len(labels),
        "accuracy": float(accuracy_score(labels, pred)),
        "macro_f1": float(f1_score(labels, pred, average="macro")),
        "confusion_matrix": confusion_matrix(labels, pred, labels=list(CLASSES)).tolist(),
        "predictions": pred,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "reports/cross_carrier.json")
    args = parser.parse_args()

    samples = load_manifest(
        ROOT / "data/manifests/sample_manifest.csv",
        exclusions_path=ROOT / "data/manifests/exclusions.csv",
    )
    split = load_split(ROOT / "data/splits/split_v4.json")
    assignment = assign_samples(split, samples)
    by_id = {s.sample_id: s for s in samples}

    # 1) 5 折纸质模型 -> PPT 折内验证样本
    cv_probs = {}
    cv_labels = {}
    for fold in range(1, 6):
        fold_doc = json.loads(
            (ROOT / f"data/splits/cv/fold_{fold}.json").read_text(encoding="utf-8")
        )
        val_groups = set(fold_doc["groups"]["val"])
        ppt_samples = [
            s
            for s in samples
            if assignment.get(s.sample_id) == "train"
            and s.doc_page_id in val_groups
            and (s.label or "").startswith("ppt_")
        ]
        if not ppt_samples:
            continue
        models = load_models(
            [
                ROOT / f"runs/cv-paper-f{fold}-s{seed}/paper_cnn.pt"
                for seed in (42, 43, 44)
            ]
        )
        if not models:
            continue
        for sample in ppt_samples:
            loaded = load_image(
                ROOT / "data/raw_samples" / sample.file, max_long_edge=1280
            )
            original = services._limit_long_edge(loaded.image, 2000)
            rectified, _quad, _status = services._apply_rectify(original, "paper")
            cv_probs[sample.sample_id] = predict(models, rectified)
            cv_labels[sample.sample_id] = sample.content_label

    cv_result = metrics(
        [cv_labels[sid] for sid in cv_probs],
        [cv_probs[sid] for sid in cv_probs],
    )

    # 2) 部署式纸质集成 -> 原始 PPT 验证集 21 张
    val_ppt = [
        s
        for s in samples
        if assignment.get(s.sample_id) == "val"
        and (s.label or "").startswith("ppt_")
    ]
    full_models = load_models(
        [
            ROOT / f"runs/paper-cnn-extctl-{suffix}/paper_cnn.pt"
            for suffix in ("01", "43", "44")
        ]
    )
    full_probs = []
    full_labels = []
    full_rows = []
    for sample in val_ppt:
        loaded = load_image(
            ROOT / "data/raw_samples" / sample.file, max_long_edge=1280
        )
        original = services._limit_long_edge(loaded.image, 2000)
        rectified, _quad, status = services._apply_rectify(original, "paper")
        prob = predict(full_models, rectified)
        full_probs.append(prob)
        full_labels.append(sample.content_label)
        full_rows.append(
            {
                "sample_id": sample.sample_id,
                "true": sample.content_label,
                "p_text": float(prob[0]),
                "p_formula": float(prob[1]),
                "pred": CLASSES[int(np.argmax(prob))],
                "status": status,
            }
        )
    full_result = metrics(full_labels, full_probs)

    payload = {
        "cv_paper_on_ppt": cv_result,
        "full_paper_on_val_ppt": full_result,
        "full_rows": full_rows,
        "comparison": {
            "ppt_branch_cv": "70.44% ± 8.24（5 折 × 3 种子）",
            "ppt_branch_oof": "71.71%",
            "ppt_branch_val": "95.24%（单点，偏乐观）",
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CV paper model on PPT:", {k: cv_result[k] for k in ("n", "accuracy", "macro_f1", "confusion_matrix")})
    print("Full paper ensemble on val PPT:", {k: full_result[k] for k in ("n", "accuracy", "macro_f1", "confusion_matrix")})
    print(f"保存 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
