"""传统分类器的单元测试。

使用二维合成特征，不依赖图像与真实数据集。
"""
import numpy as np
import pytest

from docnorm.classify.classic import ClassicClassifier, ClassifierError


def make_blobs(seed=42, n=120):
    rng = np.random.default_rng(seed)
    first = rng.normal(loc=(-1.0, -1.0), scale=0.5, size=(n // 2, 2))
    second = rng.normal(loc=(1.0, 1.0), scale=0.5, size=(n // 2, 2))
    X = np.vstack([first, second]).astype(np.float32)
    y = np.array(["text"] * (n // 2) + ["formula"] * (n // 2))
    return X, y


@pytest.mark.parametrize("model", ["svm", "rf"])
def test_fit_and_predict_separable_data(model):
    # 破坏方式：标签与特征错位会让准确率跌到随机水平
    X, y = make_blobs()
    classifier = ClassicClassifier(model=model).fit(X, y)
    predictions = classifier.predict(X)
    assert (predictions == y).mean() > 0.95


@pytest.mark.parametrize("model", ["svm", "rf"])
def test_probabilities_sum_to_one(model):
    # 破坏方式：概率未归一化会让置信度展示与阈值判断失真
    X, y = make_blobs()
    classifier = ClassicClassifier(model=model).fit(X, y)
    probabilities = classifier.predict_proba(X)
    assert probabilities.shape == (len(X), 2)
    assert np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-6)
    assert set(classifier.classes_) == {"text", "formula"}


def test_random_forest_is_deterministic():
    # 破坏方式：未固定随机种子会让两次训练结果不可复现
    X, y = make_blobs()
    first = ClassicClassifier(model="rf").fit(X, y).predict_proba(X)
    second = ClassicClassifier(model="rf").fit(X, y).predict_proba(X)
    assert np.allclose(first, second)


def test_predict_before_fit_rejected():
    # 破坏方式：未训练直接预测会抛出难以定位的底层异常
    with pytest.raises(ClassifierError, match="未训练"):
        ClassicClassifier().predict(np.zeros((2, 2)))


def test_invalid_model_name_rejected():
    # 破坏方式：拼写错误静默回退到默认模型，实验配置失真
    with pytest.raises(ClassifierError, match="model"):
        ClassicClassifier(model="xgboost")


def test_custom_hyperparameters_override_defaults():
    # 破坏方式：默认参数与自定义参数重复传入会导致训练直接报错
    X, y = make_blobs()
    classifier = ClassicClassifier(model="svm", C=0.5).fit(X, y)
    assert classifier._pipeline.named_steps["model"].C == 0.5


def test_save_and_load_roundtrip(tmp_path):
    # 破坏方式：序列化丢失标准化器会让加载后的预测与训练时不一致
    X, y = make_blobs()
    classifier = ClassicClassifier(model="svm").fit(X, y)
    path = tmp_path / "classic.joblib"
    classifier.save(path)
    loaded = ClassicClassifier.load(path)
    assert np.array_equal(classifier.predict(X), loaded.predict(X))
    assert np.allclose(classifier.predict_proba(X), loaded.predict_proba(X))


def test_single_class_training_rejected():
    # 破坏方式：单一类别训练会让概率输出与指标失去意义
    X, _ = make_blobs()
    with pytest.raises(ClassifierError, match="类别"):
        ClassicClassifier().fit(X, np.array(["text"] * len(X)))
