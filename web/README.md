# 网页交互层

本目录用于本机单用户演示，设计见 `docs/03-架构设计.md` 第 13 节与 `docs/adr/0010-前端技术方案.md`。当前已实现上传、批量队列、四阶段展示、四角校准、标注与 PDF 导出。

## 计划结构

```text
web/
├── app.py          FastAPI 应用、路由与静态文件挂载
├── schemas.py      请求与响应模型
├── services.py     处理链路、临时结果与标注存储
└── static/
    ├── index.html
    ├── app.js
    ├── style.css
    └── favicon.svg
```

## 功能范围

1. 两个入口添加图片：拍照上传与“从相册或文件选择”（手机合并为一个系统选择器；电脑端为“从文件选择”），支持拖拽与多选。无摄像头时禁用拍照入口。
2. 展示原图、四角标注、矫正图、扫描件。扫描件自动区分深色黑板与浅色纸面：黑板反相去噪后二值化，纸面锐化后二值化；CLAHE 增强保留在离线评估与兼容接口中，不再作为页面并列预览。
2.1 主链路先跑载体门控，再按分支分类：纸质稿 → 3 个种子的 CNN 集成；PPT → exp-cnn-05；门控或分支缺失 → SVM 兜底。结果卡显示“载体 / 分支”徽标。
3. 四角或整体框体拖拽后点击“应用四角”重新计算；自动检出成功时可直接拖动，手动四点需先应用一次再微调。
4. 矫正开关与 PDF 模式选择；分类模型由后端按验证集表现自动选择。矫正图与扫描件可点击放大。
5. 显示类别概率、处理耗时与检测方式。
6. 训练集标签校正：逐张选择文字或公式，写入独立标注文件，显示进度。
7. 训练集四角：自动建议四角，拖动控制点后确认保存；训练时自动检测失败才回退使用，见 ADR-0015。
8. 顶部标注人下拉框：按分配筛选个人队列，显示已分配、已保存四角与已校正标签数量。
9. 标注检查：按成员与状态查看全部四角记录，叠加轮廓逐条发回重标；退回原因回到成员队列，见 ADR-0014。
10. 批量队列：横向滑动缩略图，逐张分析、切换校准与失败状态。
11. PDF 导出：支持当前单张、选中项（复选框/区间/离散）与全部队列一起导出，可选扫描件、矫正图或原图。

## 模型加载与分支

| 用途 | 默认路径 | 环境变量 |
|---|---|---|
| 载体门控 | `runs/carrier-gate-01/screen_gate.pt` | `DOCNORM_CARRIER_GATE` |
| 纸质稿集成 | `runs/paper-cnn-extctl-01/43/44/paper_cnn.pt` | `DOCNORM_PAPER_MODELS`（`:` 分隔） |
| PPT 分类 | `runs/exp-cnn-05/cnn.pt` | `DOCNORM_PPT_MODEL` |
| SVM 兜底 | `runs/exp-*/svm.joblib` 中验证集最佳 | `DOCNORM_CLASSIC_MODEL` |

模型权重不进入版本控制。门控/分支缺失或加载失败时自动回退 SVM，不阻断分析；`/api/health` 的 `routing` 字段报告模型路径与 `routing_ready`。

分析响应在原有字段上新增：

```text
carrier: ppt | paper | unknown
carrier_probabilities: {paper: float, ppt: float} | null
branch: paper-cnn-ensemble-N | ppt-cnn-exp-cnn-05 | classic-svm
```

## 主要接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/annotators` | 成员、分配数与完成数 |
| `GET` | `/api/annotations` | 训练集标签队列（`assignee` 可选） |
| `POST` | `/api/annotations` | 保存标签校正 |
| `GET` | `/api/corners` | 训练集四角队列（`assignee` 可选） |
| `POST` | `/api/corners` | 保存四角，成功后清除退回记录 |
| `GET` | `/api/review/corners` | 全部记录，按 `assignee` / `status` 筛选并分页 |
| `POST` | `/api/review/corners/{sample_id}/redo` | 发回重标，原坐标写入审计文件 |
| `GET` | `/api/health` | 服务状态、分类模型、双分支 `routing`、标注统计 |
| `GET` | `/api/pdf/{result_id}` | 单页 PDF，`mode=scan|rectified|original` |
| `POST` | `/api/pdf` | 多页 PDF，提交 `result_ids` 与 `mode` |

标注文件默认在 `data/annotations/`；测试可用 `DOCNORM_ANNOTATION_PATH`、`DOCNORM_CORNER_PATH`、`DOCNORM_REDO_PATH` 指向临时文件。

## 约束

- 默认绑定 `127.0.0.1:54312`，不对外网开放。
- 上传限制 15 MB，按内容校验格式；上传解码先按 EXIF 方向转正，再限制长边 2000 像素，减少电脑原图与手机转码图的方向差异；扫描件最多 1600 像素，批量缩略图 240 像素，避免大图导致浏览器或容器内存飙升。
- 结果只写临时目录，1 小时过期，不进入数据集与版本控制。
- 前端使用原生 JavaScript 与 Canvas，不引入 Node 构建链与外部 CDN。
- 模型文件在 `runs/`，部署时需挂载仓库目录；缺失时回退 SVM，`branch` 显示 `classic-svm`。
- 完整 `tests/unit/test_web.py` 需要本地 `data/raw_samples` 图像；CI 使用 `-m "not requires_dataset"` 跳过 4 个数据依赖用例，本地有数据时运行全量。

## 启动方式

```bash
PYTHONPATH=src uvicorn web.app:app --host 127.0.0.1 --port 54312
```

容器内映射端口：

```bash
docker run --rm -p 127.0.0.1:54312:54312 docnorm:cpu-arm64 \
  uvicorn web.app:app --host 0.0.0.0 --port 54312
```

原型阶段直接使用 Uvicorn，命令行 `docnorm serve` 在后续版本补充。模型从 `runs/` 下最新的 `svm.joblib` 加载；缺失时只展示预处理结果。
