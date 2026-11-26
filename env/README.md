# 环境依赖说明

本目录存放依赖声明。完整的环境策略见 `docs/08-跨平台环境与复现方案.md`。

## 文件

| 文件 | 内容 | 说明 |
|---|---|---|
| `requirements-base.txt` | 基础科学计算与图像处理依赖 | 必装 |
| `requirements-dl.txt` | PyTorch 与 torchvision | 深度学习实验需要 |
| `requirements-web.txt` | FastAPI、Uvicorn 与 multipart 解析 | 网页演示需要 |

## 安装方式

基础依赖：

```bash
pip install -r env/requirements-base.txt
```

深度学习依赖须指定中央处理器版本索引：

```bash
pip install --index-url https://download.pytorch.org/whl/cpu -r env/requirements-dl.txt
```

网页依赖：

```bash
pip install -r env/requirements-web.txt
```

## 版本策略

当前文件声明版本区间。M1 结束时生成锁定文件，记录精确版本及哈希。锁定后仅接受安全修复。

## 架构说明

两种架构分别构建容器，不使用指令集模拟。ARM 设备构建 `linux/arm64` 镜像，x86 设备构建 `linux/amd64` 镜像。

## Python 版本

统一使用 Python 3.11。不使用 3.13 及以上版本，原因是部分科学计算包尚未提供对应预编译包。
