"""传统分类器：支持向量机与随机森林。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

SUPPORTED_MODELS = ("svm", "rf")


class ClassifierError(ValueError):
    """分类器配置或调用顺序不合法。"""


class ClassicClassifier:
    """统一封装支持向量机与随机森林。

    Args:
        model: `svm` 或 `rf`。
        random_state: 随机种子。
        **params: 透传给底层估计器的参数。
    """

    def __init__(self, model: str = "svm", random_state: int = 42, **params: Any) -> None:
        if model not in SUPPORTED_MODELS:
            raise ClassifierError(f"model 必须为 {SUPPORTED_MODELS} 之一: {model}")
        self.model = model
        self.random_state = random_state
        self.params = params
        self._pipeline: Pipeline | None = None

    def _build(self) -> Pipeline:
        if self.model == "svm":
            defaults = {
                "C": 1.0,
                "gamma": 0.001,
                "probability": True,
                "class_weight": "balanced",
                "random_state": self.random_state,
            }
            defaults.update(self.params)
            estimator = SVC(**defaults)
        else:
            defaults = {
                "n_estimators": 300,
                "class_weight": "balanced_subsample",
                "random_state": self.random_state,
                "n_jobs": -1,
                "min_samples_leaf": 2,
                "max_features": "sqrt",
            }
            defaults.update(self.params)
            estimator = RandomForestClassifier(**defaults)
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                ("model", estimator),
            ]
        )

    def fit(self, features: np.ndarray, labels: np.ndarray) -> "ClassicClassifier":
        """训练分类器。

        Raises:
            ClassifierError: 特征维度、标签长度或类别数不合法。
        """
        matrix = np.asarray(features)
        target = np.asarray(labels)
        if matrix.ndim != 2:
            raise ClassifierError(f"特征必须为二维矩阵: {matrix.shape}")
        if len(matrix) != len(target):
            raise ClassifierError("特征数与标签数不一致")
        if len(np.unique(target)) < 2:
            raise ClassifierError("训练集至少需要两个类别")
        self._pipeline = self._build()
        self._pipeline.fit(matrix, target)
        return self

    def _require_fitted(self) -> Pipeline:
        if self._pipeline is None:
            raise ClassifierError("分类器尚未训练")
        return self._pipeline

    def predict(self, features: np.ndarray) -> np.ndarray:
        return self._require_fitted().predict(np.asarray(features))

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        return self._require_fitted().predict_proba(np.asarray(features))

    @property
    def classes_(self) -> np.ndarray:
        return self._require_fitted().classes_

    def save(self, path: Path) -> None:
        pipeline = self._require_fitted()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, path)

    @classmethod
    def load(cls, path: Path) -> "ClassicClassifier":
        pipeline = joblib.load(path)
        final = pipeline.named_steps["model"]
        instance = cls(model="svm" if isinstance(final, SVC) else "rf")
        instance._pipeline = pipeline
        return instance
