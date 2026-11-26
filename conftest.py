"""pytest 配置：把 src/ 加入导入路径，使测试可直接 import docnorm。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
