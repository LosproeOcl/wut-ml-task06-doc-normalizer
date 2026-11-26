"""屏幕/载体门控网络：整图判断是否为投影幕布或 PPT 载体。"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import models

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
CLASSES = ("other", "screen")


class ScreenGate(nn.Module):
    """MobileNetV3-Small 二分类门控，输出 other / screen。"""

    def __init__(self, pretrained: bool = False) -> None:
        super().__init__()
        weights = models.MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
        base = models.mobilenet_v3_small(weights=weights)
        self.features = base.features
        self.avgpool = base.avgpool
        self.head = nn.Sequential(
            nn.Linear(576, 256),
            nn.Hardswish(),
            nn.Dropout(0.2),
            nn.Linear(256, 2),
        )

    def forward(self, images):
        features = self.features(images)
        pooled = self.avgpool(features)
        return self.head(torch.flatten(pooled, 1))

    @classmethod
    def from_checkpoint(cls, path: Path, *, device: str = "cpu") -> "ScreenGate":
        payload = torch.load(path, map_location=device)
        state = payload.get("state_dict", payload) if isinstance(payload, dict) else payload
        model = cls(pretrained=False).to(device)
        model.load_state_dict(state)
        model.eval()
        model.input_size = int(payload.get("input_size", 160)) if isinstance(payload, dict) else 160
        return model

    @torch.no_grad()
    def predict_proba(self, image: np.ndarray) -> np.ndarray:
        """输入 BGR 图像，返回 [P(other), P(screen)]。"""
        size = int(getattr(self, "input_size", 160))
        resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        mean = torch.tensor(MEAN).view(3, 1, 1)
        std = torch.tensor(STD).view(3, 1, 1)
        tensor = ((tensor - mean) / std).unsqueeze(0)
        return torch.softmax(self(tensor), dim=1)[0].cpu().numpy()

    def predict(self, image: np.ndarray) -> float:
        """输入 BGR 图像，返回 screen 概率，供旧评估脚本兼容。"""
        return float(self.predict_proba(image)[1])
