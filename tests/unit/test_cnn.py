"""MobileNetV3 分类器的单元测试。

使用 pretrained=False，避免测试依赖网络与权重下载。
"""
import numpy as np
import pytest
import torch
from torch.utils.data import DataLoader, TensorDataset

from docnorm.classify.cnn import CLASSES, CnnClassifier, CnnError, build_model


def make_images(count=3, size=64):
    rng = np.random.default_rng(0)
    return [rng.integers(0, 255, (size, size, 3), dtype=np.uint8) for _ in range(count)]


def test_build_model_outputs_two_logits():
    # 破坏方式：分类头未替换时输出仍是 1000 类
    model = build_model(pretrained=False)
    logits = model(torch.zeros(2, 3, 224, 224))
    assert logits.shape == (2, 2)


def test_predict_proba_shape_and_normalization():
    # 破坏方式：未做 softmax 或通道转换错误会让概率不可用
    classifier = CnnClassifier(pretrained=False)
    probabilities = classifier.predict_proba(make_images(3))
    assert probabilities.shape == (3, len(CLASSES))
    assert np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-5)


def test_predict_returns_class_names():
    # 破坏方式：返回索引而非类别名会破坏预测结果表
    classifier = CnnClassifier(pretrained=False)
    predictions = classifier.predict(make_images(2))
    assert set(predictions).issubset(set(CLASSES))


def test_save_and_load_roundtrip(tmp_path):
    # 破坏方式：只保存骨干而丢失分类头会让加载后的输出维度错误
    classifier = CnnClassifier(pretrained=False)
    path = tmp_path / "cnn.pt"
    classifier.save(path)
    loaded = CnnClassifier.load(path)
    images = make_images(2)
    assert np.allclose(
        classifier.predict_proba(images), loaded.predict_proba(images), atol=1e-5
    )


def test_invalid_backbone_rejected():
    # 破坏方式：拼写错误静默替换骨干会让实验记录失真
    with pytest.raises(CnnError, match="骨干"):
        build_model("resnet50")


def test_fit_runs_one_epoch_on_tiny_dataset():
    # 破坏方式：训练循环接口错误会在真实训练前无法发现
    classifier = CnnClassifier(pretrained=False)
    images = torch.rand(8, 3, 224, 224)
    labels = torch.tensor([0, 1, 0, 1, 0, 1, 0, 1])
    loader = DataLoader(TensorDataset(images, labels), batch_size=4)
    history = classifier.fit(loader, loader, epochs=1, freeze_epochs=1)
    assert len(history["val_accuracy"]) == 1
    assert 0.0 <= history["val_accuracy"][0] <= 1.0


def test_empty_prediction_rejected():
    # 破坏方式：空批次进入模型会产生难以定位的张量错误
    classifier = CnnClassifier(pretrained=False)
    with pytest.raises(CnnError, match="为空"):
        classifier.predict_proba([])
