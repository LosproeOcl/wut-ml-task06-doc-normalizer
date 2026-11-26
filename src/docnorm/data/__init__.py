"""数据层：样本清单解析与校验、按文档页分组划分、图像读取。

模块职责与输入输出以 `docs/03-架构设计.md` 第 4 节为准。
"""

from .manifest import (
    Manifest,
    ManifestReport,
    ManifestRow,
    parse_manifest,
    validate,
)
from .split import (
    load_split,
    make_split,
    sha256_file,
    validate_split,
    write_split,
)

__all__ = [
    "Manifest",
    "ManifestReport",
    "ManifestRow",
    "parse_manifest",
    "validate",
    "make_split",
    "validate_split",
    "load_split",
    "write_split",
    "sha256_file",
]
