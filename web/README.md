# 网页交互层

本目录用于本机单用户演示，规划见 `docs/03-架构设计.md` 第 13 节与 `docs/adr/0010-前端技术方案.md`。当前仅为结构说明，代码在阶段一实施。

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

1. 上传图片或从本地样本库选择。
2. 展示原图、四角标注、矫正图、增强图。
3. 四角拖拽后重新计算。
4. 矫正开关、增强开关与模型选择。
5. 显示类别概率、处理耗时与检测方式。
6. 训练集标签校正：逐张选择文字或公式，写入独立标注文件，显示进度。
7. 训练集四角：自动建议四角，拖动控制点后确认保存；训练时自动检测失败才回退使用，见 ADR-0015。
8. 顶部标注人下拉框：按分配筛选个人队列，显示已分配、已保存四角与已校正标签数量。
9. 标注检查：按成员与状态查看全部四角记录，叠加轮廓逐条发回重标；退回原因回到成员队列，见 ADR-0014。

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

标注文件默认在 `data/annotations/`；测试可用 `DOCNORM_ANNOTATION_PATH`、`DOCNORM_CORNER_PATH`、`DOCNORM_REDO_PATH` 指向临时文件。

## 约束

- 默认绑定 `127.0.0.1:54312`，不对外网开放。
- 上传限制 15 MB，按内容校验格式。
- 结果只写临时目录，1 小时过期，不进入数据集与版本控制。
- 前端使用原生 JavaScript 与 Canvas，不引入 Node 构建链与外部 CDN。

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
