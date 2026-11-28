# 合成投影 PPT 试点数据

本目录存放**合成训练候选**，不属于自采样本，不进入 `sample_manifest.csv`、`split_v4.json`、验证集或测试集。

## 版本 v1

| 项目 | 内容 |
|---|---|
| 生成日期 | 2026-11-28 |
| 数量 | 24 组（文字 12 / 公式 12） |
| 分辨率 | 1280×960（项目统一 4:3） |
| 输出 | `projected/` 投影合成图、`slides/` 课件原图、`manifest.csv`、`gallery.html` |
| 背景 | SCB-Dataset 教师子集 10 张教室图，screen 框来自 `data/manifests/scb_screen.csv` |
| 标签 | 由版式生成器确定，`text` / `formula` |
| 脚本 | `scripts/build_synth_ppt_pages.py` |
| 说明 | 本版本只用于观察合成效果，**尚未进入任何训练或评估** |

重新生成：

```bash
python3 scripts/build_synth_ppt_pages.py \
  --out data/synthetic/ppt_projection_v1 --n-per-class 12
```

打开 `data/synthetic/ppt_projection_v1/gallery.html` 可逐组对照“课件原图 / 投影合成”。

## 边界

1. 合成图只允许进入训练集，且必须在报告中披露生成方式、数量、模板与背景来源。
2. 不得进入自采验证集或测试集，不得用合成图报告最终指标。
3. SCB 原图不复制、不再分发；本目录图像只在本机生成，已被 `.gitignore` 排除，仓库只保留清单与说明。
4. 当前背景是 K12 教室，且只有 10 张，不能代表大学教室的光照、投影距离与遮挡；扩大训练前必须补充背景与遮挡多样性。
5. 模板与类别尚不完全均衡（纸质模板只有 1 张公式页），训练前需做模板×类别交叉平衡，避免模型学习背景色/模板而不是内容。

详细方法与评审记录见 [`docs/17-合成投影PPT试点.md`](../../docs/17-合成投影PPT试点.md)。
