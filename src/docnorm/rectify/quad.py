"""按载体训练的四角回归模型：加载、推理与合法性检查。

模型输出归一化四角坐标 (x1,y1,...,x4,y4)，推理后按原图像素返回
DocumentQuad；面积比例过小/过大的预测视为不可用，交给调用方回退。
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import models

from docnorm.rectify.geometry import DocumentQuad, RectifyError

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class QuadNet(nn.Module):
    """MobileNetV3-Small + 8 维 sigmoid 回归头。"""

    def __init__(self) -> None:
        super().__init__()
        base = models.mobilenet_v3_small(weights=None)
        self.features = base.features
        self.avgpool = base.avgpool
        self.head = nn.Sequential(
            nn.Linear(576, 256),
            nn.Hardswish(),
            nn.Dropout(0.2),
            nn.Linear(256, 8),
            nn.Sigmoid(),
        )

    def forward(self, images):
        return self.head(torch.flatten(self.avgpool(self.features(images)), 1))


class QuadRegressor:
    """CPU 推理封装，输入 BGR 图像，输出 DocumentQuad。"""

    def __init__(self, model: QuadNet, input_size: int, path: Path | None = None) -> None:
        self.model = model.eval()
        self.input_size = int(input_size)
        self.path = path

    @classmethod
    def from_checkpoint(cls, path: Path) -> "QuadRegressor":
        payload = torch.load(path, map_location="cpu", weights_only=True)
        model = QuadNet()
        model.load_state_dict(payload["state_dict"])
        return cls(model, int(payload.get("input_size", 224)), Path(path))

    def _prepare(self, image: np.ndarray) -> torch.Tensor:
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        resized = cv2.resize(
            image, (self.input_size, self.input_size), interpolation=cv2.INTER_AREA
        )
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        mean = torch.tensor(MEAN).view(3, 1, 1)
        std = torch.tensor(STD).view(3, 1, 1)
        return ((tensor - mean) / std).unsqueeze(0)

    @torch.no_grad()
    def predict(
        self,
        image: np.ndarray,
        *,
        min_area_ratio: float = 0.10,
        max_area_ratio: float = 0.99,
    ) -> DocumentQuad | None:
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        height, width = image.shape[:2]
        if height < 32 or width < 32:
            return None
        prediction = self.model(self._prepare(image)).numpy()[0]
        points = prediction.reshape(4, 2) * np.array([width, height], dtype=np.float32)
        try:
            quad = DocumentQuad(points)
        except (RectifyError, ValueError):
            return None
        if not min_area_ratio <= quad_area_ratio(quad.points, width, height) <= max_area_ratio:
            return None
        return quad


def quad_area_ratio(points: np.ndarray, width: int, height: int) -> float:
    x = points[:, 0]
    y = points[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    return area / float(width * height) if width and height else 0.0
