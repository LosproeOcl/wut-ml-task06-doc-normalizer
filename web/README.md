# 网页交互层

本目录用于本机单用户演示，规划见 `docs/03-架构设计.md` 第 13 节与 `docs/adr/0010-前端技术方案.md`。当前仅为结构说明，代码在阶段一实施。

## 计划结构

```text
web/
├── app.py          FastAPI 应用、路由与静态文件挂载
├── schemas.py      请求与响应模型
├── services.py     调用 pipeline 与临时结果管理
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

## 约束

- 默认绑定 `127.0.0.1:8000`，不对外网开放。
- 上传限制 15 MB，按内容校验格式。
- 结果只写临时目录，1 小时过期，不进入数据集与版本控制。
- 前端使用原生 JavaScript 与 Canvas，不引入 Node 构建链与外部 CDN。

## 启动方式

```bash
docnorm serve --host 127.0.0.1 --port 8000
```

容器内映射端口：

```bash
docker run --rm -p 127.0.0.1:8000:8000 docnorm:cpu-arm64 \
  docnorm serve --host 0.0.0.0 --port 8000
```
