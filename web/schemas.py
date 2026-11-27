"""网页层请求模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CornersRequest(BaseModel):
    points: list[tuple[float, float]] = Field(min_length=4, max_length=4)


class AnnotationRequest(BaseModel):
    sample_id: str = Field(min_length=1)
    label: str = Field(pattern="^(text|formula)$")
    annotator: str = Field(default="web", max_length=40)


class CornerAnnotationRequest(BaseModel):
    sample_id: str = Field(min_length=1)
    points: list[tuple[float, float]] = Field(min_length=4, max_length=4)
    annotator: str = Field(default="web", max_length=40)


class RedoRequest(BaseModel):
    reason: str = Field(default="审查退回：四角范围不符合整页口径", max_length=200)



class PdfRequest(BaseModel):
    result_ids: list[str] = Field(min_length=1, max_length=50)
    mode: Literal["scan", "rectified", "original"] = "scan"
    view: Literal["quad", "opencv"] = "quad"
