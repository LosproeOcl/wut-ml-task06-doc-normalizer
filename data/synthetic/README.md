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

## 版本 v2（训练用试点）

| 项目 | 内容 |
|---|---|
| 数量 | 160 组（文字 80 / 公式 80） |
| 分辨率 | 1280×960 |
| 背景 | 57 个：47 张自采 train PPT（人工四角，按 doc_page_id 去重）+ 10 张 SCB 教室图 |
| 模板 | 深紫 / 米白 / 白底绿条 / 深青；每个模板×类别 20 张，完全平衡 |
| 标签 | 由版式生成器确定，`text` / `formula` |
| 训练清单 | `data/manifests/synth_ppt_v2_train.csv`（含背景组，CV 时用于跳过验证组） |
| 背景清单 | `data/manifests/synth_backgrounds_v1.csv` |
| 说明 | 只作为**训练候选**，不进入验证/测试；5 折 CV 结果见 `reports/synth_ppt_training.md` |

重新生成：

```bash
PYTHONPATH=src python scripts/build_synth_backgrounds.py   --out data/manifests/synth_backgrounds_v1.csv --per-class 24

python3 scripts/build_synth_ppt_pages.py   --out data/synthetic/ppt_projection_v2 --n-per-class 80   --background-manifest data/manifests/synth_backgrounds_v1.csv   --id-prefix syn-ppt-v2

python3 scripts/build_synth_train_manifest.py   --manifest data/synthetic/ppt_projection_v2/manifest.csv   --out data/manifests/synth_ppt_v2_train.csv
```

`train_cnn.py` 通过 `--extra-train-manifest` 把合成样本追加到训练集；若合成背景所属 `doc_page_id` 在当前 CV 折的验证组内，会自动跳过，避免背景场景泄漏。合成图 `rectify=0`，训练时不再重复拉正。

5 折 × 3 种子结果：准确率 **70.44% → 78.25%（+7.81pp）**，宏 F1 **67.25% → 76.07%**，OOF **71.71% → 77.56%**；测试集未使用。fold5 仅 +0.81pp，fold3 种子波动仍大，详见 `reports/synth_ppt_training.md`。

## 版本 v3（严格 4:3 定位）

- 160 组（80/80），只用 19 个与 4:3 相差 ≤0.05 的人工四角背景；
- 课件直接贴到标注框，不外扩、不抖动，避免整块幕布/白边错位；
- 5 折 × 3 种子：**76.50% ± 6.85**，宏 F1 **74.74%**，OOF **78.05%**，公式召回 **81.0%**；折均值低于 v2，但定位更准、公式召回更高；
- 清单 `synth_ppt_v3_train.csv`，说明见 `reports/synth_ppt_v3_training.md`。

## 边界

1. 合成图只允许进入训练集，且必须在报告中披露生成方式、数量、模板与背景来源。
2. 不得进入自采验证集或测试集，不得用合成图报告最终指标。
3. SCB 原图不复制、不再分发；本目录图像只在本机生成，已被 `.gitignore` 排除，仓库只保留清单与说明。
4. v1 背景是 K12 教室、只有 10 张；v2 已换用自采 train PPT + 少量 SCB，但仍只有 57 个背景，遮挡/强光/运动模糊仍不足。
5. v1 模板与类别不均衡；v2 已按每个模板×类别 20 张平衡。训练时仍应检查模型是否把模板颜色当作捷径。

详细方法与评审记录见 [`docs/17-合成投影PPT试点.md`](../../docs/17-合成投影PPT试点.md)。
