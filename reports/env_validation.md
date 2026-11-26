# 环境验证记录

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-26 |
| 对应风险 | R-03：ARM 与 x86 依赖不可用或行为不一致 |
| 结论 | arm64 原生环境通过；x86 待组员机器或共用虚拟机复核 |
| 代码版本 | `7e63178` 之后的本地工作区 |

## 1. 验证环境

| 项目 | 值 |
|---|---|
| 宿主机 | macOS，Apple Silicon（arm64） |
| 容器运行时 | Colima 0.10.3，Docker 27.3.1 |
| 容器架构 | linux/arm64 |
| 基础镜像 | python:3.11-slim |
| 镜像标签 | docnorm:cpu-arm64 |
| 镜像体积 | 2.18 GB |

## 2. 构建

```bash
docker build --platform linux/arm64 \
  --build-arg INSTALL_CJK_FONTS=0 \
  -f env/Dockerfile -t docnorm:cpu-arm64 .
```

结果：构建成功。中文字体包体积约 57 MB，在本次网络条件下下载停滞，因此以 `INSTALL_CJK_FONTS=0` 关闭。字体不影响依赖与架构验证，出图前须重建完整镜像或在容器内补装。

## 3. 环境自检

```bash
docker run --rm docnorm:cpu-arm64 python scripts/env_smoke.py --json
```

| 组件 | 版本 |
|---|---|
| Python | 3.11.18 |
| NumPy | 2.2.6 |
| OpenCV | 4.14.0 |
| Pillow | 11.3.0 |
| scikit-learn | 1.9.1 |
| scikit-image | 0.26.0 |
| PyTorch | 2.15.0+cpu |
| torchvision | 0.29.2+cpu |

运行平台为 `Linux-6.8.0-aarch64-with-glibc2.41`，依赖缺失列表为空，退出码 0。PyTorch 为中央处理器版本，符合 ADR-0004。

## 4. 测试

```bash
docker run --rm -v "$PWD/data:/app/data:ro" docnorm:cpu-arm64 \
  python -m pytest tests -q
```

结果：26 项测试全部通过。其中集成测试校验真实清单、排除表、`split_v2` 与磁盘文件的一致性，确认 344 张合格样本、训练 240、验证 51、测试 53。

镜像重建后追加验证：镜像内单元测试 38 项通过（含矫正模块 13 项）；集成测试需挂载 `data/` 运行。

## 5. 未覆盖项

1. **x86 架构未验证。** 本机为 ARM，无法原生验证 `linux/amd64`。须由组内 Windows 或 Linux 成员构建同名镜像并执行同一自检，或在共用虚拟机上执行。
2. **中文字体未安装。** 当前镜像出图时中文会显示为方块。正式出图前须以默认参数重建镜像。
3. **图形界面未验证。** 容器不包含 OpenCV 图形界面依赖，符合命令行设计；本地调试需要显示窗口时使用宿主机环境。

## 6. 后续动作

| 动作 | 负责人 | 期限 |
|---|---|---|
| 在 x86 机器构建镜像并执行 `env_smoke.py`，回填本记录 | 李念 | 11 月 27 日 |
| 以默认参数重建含中文字体的镜像，验证图表中文 | 孔泽宇 | 首次出图前 |
| 将本记录纳入 M0 门禁材料 | 余青阳 | 11 月 26 日 |
