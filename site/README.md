# GitHub Pages 静态演示

本目录是部署到 GitHub Pages 的静态演示站，入口：

`https://losproeocl.github.io/wut-ml-task06-doc-normalizer/`

## 与完整 webapp 的差异

- 只保留“在线演示 / 评估结果 / 项目仓库”三个入口；
- **隐藏**“训练集标签”“训练集四角”“标注检查”和标注人筛选；
- 不运行 FastAPI、不加载模型，上传分析、PDF、标注功能仅保留在本机 webapp；
- 演示数据为 6 个预计算样张（原图/四角、矫正图、扫描件、载体、分支、概率）。

本机完整版仍为 `web/static/index.html`，未删除任何标注入口。

## 数据来源

- 样张来自本机运行中的 webapp `/api/analyze`；
- 只选择无个人信息的课程样张；
- 图像压缩到长边 1080、JPEG 质量 86；
- 不包含样本清单路径、原始文件名或标注文件。

重新生成：

```bash
# 先启动本机 webapp
PYTHONPATH=src uvicorn web.app:app --host 127.0.0.1 --port 54312

# 再生成静态演示数据
python3 scripts/build_pages_demo.py
```

`site/figures/` 来自 `reports/figures/` 的两张评估图。

## 部署

`.github/workflows/pages.yml` 在 `site/` 变更时上传静态产物并部署到 GitHub Pages。无需 Node 构建链。
