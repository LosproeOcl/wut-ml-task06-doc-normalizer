"""传统分类器与轻量卷积网络。"""
from docnorm.classify.classic import ClassicClassifier, ClassifierError
from docnorm.classify.cnn import CLASSES, CnnClassifier, CnnError, build_model

__all__ = [
    "CLASSES",
    "ClassicClassifier",
    "ClassifierError",
    "CnnClassifier",
    "CnnError",
    "build_model",
]
