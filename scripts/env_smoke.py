"""环境自检：核对解释器版本、依赖版本与处理器架构。

用法：
    python scripts/env_smoke.py
    python scripts/env_smoke.py --json
"""
from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys


def _version(module: str, attribute: str = "__version__") -> str | None:
    try:
        return getattr(importlib.import_module(module), attribute, None)
    except ImportError:
        return None


def collect() -> dict[str, object]:
    report: dict[str, object] = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": _version("numpy"),
        "opencv": _version("cv2"),
        "pillow": _version("PIL"),
        "scikit_learn": _version("sklearn"),
        "scikit_image": _version("skimage"),
        "torch": _version("torch"),
        "torchvision": _version("torchvision"),
        "device": "cpu",
    }
    report["missing"] = [
        name
        for name in (
            "numpy",
            "opencv",
            "pillow",
            "scikit_learn",
            "scikit_image",
            "torch",
            "torchvision",
        )
        if report[name] is None
    ]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    report = collect()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")

    failed = False
    if not str(report["python"]).startswith("3.11"):
        print("错误：Python 版本不是 3.11", file=sys.stderr)
        failed = True
    if report["missing"]:
        print(f"错误：缺少依赖 {report['missing']}", file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
