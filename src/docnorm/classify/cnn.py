"""MobileNetV3 迁移学习分类器。"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import models, transforms

SUPPORTED_BACKBONES = (
    "mobilenet_v3_small",
    "mobilenet_v3_large",
    "efficientnet_b0",
)
CLASSES = ("text", "formula")
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class CnnError(ValueError):
    """CNN 配置或调用不合法。"""


def _weights(backbone: str, pretrained: bool):
    if not pretrained:
        return None
    if backbone == "mobilenet_v3_small":
        return models.MobileNet_V3_Small_Weights.IMAGENET1K_V1
    if backbone == "mobilenet_v3_large":
        return models.MobileNet_V3_Large_Weights.IMAGENET1K_V1
    return models.EfficientNet_B0_Weights.IMAGENET1K_V1


def build_model(
    backbone: str = "mobilenet_v3_small",
    *,
    num_classes: int = 2,
    pretrained: bool = True,
) -> nn.Module:
    """构建 MobileNetV3 分类模型。

    Raises:
        CnnError: 骨干名称不受支持。
    """
    if backbone not in SUPPORTED_BACKBONES:
        raise CnnError(f"不支持的骨干网络: {backbone}")
    if backbone == "mobilenet_v3_small":
        model = models.mobilenet_v3_small(weights=_weights(backbone, pretrained))
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, num_classes)
    elif backbone == "mobilenet_v3_large":
        model = models.mobilenet_v3_large(weights=_weights(backbone, pretrained))
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, num_classes)
    else:
        model = models.efficientnet_b0(weights=_weights(backbone, pretrained))
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)
    return model


class CnnClassifier:
    """小样本迁移学习封装，正式评估固定使用中央处理器。"""

    def __init__(
        self,
        backbone: str = "mobilenet_v3_small",
        *,
        pretrained: bool = True,
        device: str = "cpu",
        random_state: int = 42,
        input_size: int = 224,
    ) -> None:
        if input_size < 96:
            raise CnnError(f"输入尺寸过小: {input_size}")
        self.backbone = backbone
        self.device = torch.device(device)
        self.random_state = random_state
        self.input_size = input_size
        self.model = build_model(
            backbone, num_classes=len(CLASSES), pretrained=pretrained
        ).to(self.device)
        resize = int(round(input_size * 256 / 224))
        self.transform = transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.Resize(resize),
                transforms.CenterCrop(input_size),
                transforms.ToTensor(),
                transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            ]
        )

    def _prepare(self, image: np.ndarray) -> torch.Tensor:
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return self.transform(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    def fit(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        *,
        epochs: int = 20,
        freeze_epochs: int = 3,
        lr_head: float = 1e-3,
        lr_finetune: float = 1e-4,
        class_weights: Sequence[float] | None = None,
        patience: int = 5,
        label_smoothing: float = 0.0,
        on_epoch: Callable[[int, dict[str, float]], None] | None = None,
    ) -> dict[str, list[float]]:
        """两阶段训练：先冻结骨干训分类头，再整体微调。"""
        if epochs < 1:
            raise CnnError(f"epochs 必须为正整数: {epochs}")
        torch.manual_seed(self.random_state)
        weights = (
            torch.tensor(class_weights, dtype=torch.float32, device=self.device)
            if class_weights is not None
            else None
        )
        criterion = nn.CrossEntropyLoss(
            weight=weights, label_smoothing=label_smoothing
        )
        optimizer = torch.optim.AdamW(
            self.model.classifier.parameters(), lr=lr_head, weight_decay=1e-4
        )
        for parameter in self.model.features.parameters():
            parameter.requires_grad = False

        history = {"train_loss": [], "val_loss": [], "val_accuracy": []}
        best_accuracy = -1.0
        best_state = copy.deepcopy(self.model.state_dict())
        stale = 0

        for epoch in range(epochs):
            if epoch == freeze_epochs:
                for parameter in self.model.features.parameters():
                    parameter.requires_grad = True
                optimizer = torch.optim.AdamW(
                    self.model.parameters(), lr=lr_finetune, weight_decay=1e-4
                )

            self.model.train()
            running = 0.0
            grad_norm_total = 0.0
            grad_batches = 0
            for images, labels in train_loader:
                images = images.to(self.device)
                labels = labels.to(self.device)
                optimizer.zero_grad(set_to_none=True)
                logits = self.model(images)
                loss = criterion(logits, labels)
                loss.backward()
                grad_sq = 0.0
                for parameter in self.model.parameters():
                    if parameter.grad is not None:
                        grad_sq += float(parameter.grad.detach().pow(2).sum().item())
                grad_norm_total += grad_sq ** 0.5
                grad_batches += 1
                optimizer.step()
                running += float(loss.item()) * len(labels)

            train_loss = running / max(len(train_loader.dataset), 1)
            grad_norm = grad_norm_total / max(grad_batches, 1)
            lr = float(optimizer.param_groups[0]["lr"])
            param_sq = sum(
                float(parameter.detach().pow(2).sum().item())
                for parameter in self.model.parameters()
            )
            param_norm = param_sq ** 0.5
            val_loss, val_accuracy = self.evaluate(val_loader, criterion)
            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)
            history["val_accuracy"].append(val_accuracy)
            if on_epoch is not None:
                on_epoch(
                    epoch + 1,
                    train_loss=train_loss,
                    val_loss=val_loss,
                    val_accuracy=val_accuracy,
                    lr=lr,
                    grad_norm=grad_norm,
                    param_norm=param_norm,
                )

            if val_accuracy > best_accuracy:
                best_accuracy = val_accuracy
                best_state = copy.deepcopy(self.model.state_dict())
                stale = 0
            else:
                stale += 1
                if stale >= patience:
                    break

        self.model.load_state_dict(best_state)
        return history

    @torch.no_grad()
    def evaluate(self, loader: DataLoader, criterion: nn.Module | None = None) -> tuple[float, float]:
        criteria = criterion or nn.CrossEntropyLoss()
        self.model.eval()
        loss_total = 0.0
        correct = 0
        total = 0
        for images, labels in loader:
            images = images.to(self.device)
            labels = labels.to(self.device)
            logits = self.model(images)
            loss_total += float(criteria(logits, labels).item()) * len(labels)
            correct += int((logits.argmax(dim=1) == labels).sum().item())
            total += len(labels)
        return loss_total / max(total, 1), correct / max(total, 1)

    @torch.no_grad()
    def predict_proba(self, images: Sequence[np.ndarray]) -> np.ndarray:
        """对 BGR 图像列表输出两类概率。"""
        if len(images) == 0:
            raise CnnError("图像列表为空")
        batch = torch.stack([self._prepare(image) for image in images]).to(self.device)
        self.model.eval()
        probabilities = torch.softmax(self.model(batch), dim=1).cpu().numpy()
        return probabilities

    def predict(self, images: Sequence[np.ndarray]) -> np.ndarray:
        probabilities = self.predict_proba(images)
        return np.asarray([CLASSES[index] for index in probabilities.argmax(axis=1)])

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "backbone": self.backbone,
                "input_size": self.input_size,
                "state_dict": self.model.state_dict(),
                "classes": CLASSES,
            },
            path,
        )

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        device: str = "cpu",
        pretrained: bool = False,
    ) -> "CnnClassifier":
        payload = torch.load(path, map_location=device)
        instance = cls(
            backbone=payload["backbone"],
            pretrained=pretrained,
            device=device,
            input_size=int(payload.get("input_size", 224)),
        )
        instance.model.load_state_dict(payload["state_dict"])
        instance.model.eval()
        return instance
