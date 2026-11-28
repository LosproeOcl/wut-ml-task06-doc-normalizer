# 训练集手动四角背景合成 PPT 示例

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-28 |
| 背景 | 自采 **train** PPT 照片，四角来自 `data/annotations/manual_corners.csv`（人工标注） |
| 示例 | 16 组（文字 8 / 公式 8） |
| 分辨率 | 1280×960 |
| 模板 | 深紫 / 米白 / 白底绿条 / 深青，每个模板×类别 2 张 |
| 定位 | 直接使用人工四角，不做估计；只外扩约 1.4% 覆盖旧课件边缘 |
| 状态 | 仅示例，不进入训练/验证/测试 |

## 产物

| 文件 | 内容 |
|---|---|
| `reports/manual_synth_preview.jpg` | 16 组合成预览 |
| `reports/manual_synth_pairs.jpg` | 4 组“原场景 / 合成”对照 |
| `reports/manual_synth_layouts.jpg` | 16 张课件页版式 |
| `data/synthetic/manual_demo_v2/gallery.html` | 本地逐组对照 |
| `data/synthetic/manual_demo_v2/manifest.csv` | 路径、标签、模板、背景 ID |
| `data/manifests/synth_backgrounds_manual_demo2.csv` | 16 个训练集背景及人工四角 |

## 定位方式

1. 背景四角直接取 `data/annotations/manual_corners.csv` 中对应训练 PPT 照片的人工标注；
2. 四角按原图尺寸归一化，写入背景清单；
3. 生成时按四角做单应变换，把 1280×960 课件贴入幕布；
4. 只对四角做 1.4% 外扩；底板向下多扩到 1.12 倍，专门盖住屏幕底部的旧课件页脚；不做随机透视/位置抖动；
5. 贴图后再裁 4:3 近景，保留教室上下文。

## 说明

- 这批背景全部来自 `split_v4` 训练集，val/test 不参与；
- 之前用用户新照片估计四角的示例定位不准，已删除；
- 当前示例只用于检查“人工四角 + 课件替换”的定位效果，不进入训练；
- 之前用用户新照片估计四角的示例已删除，避免把不准的定位带进训练；
- 若定位确认可用，再把这 16 个背景加入 v3 训练背景池，并按 `doc_page_id` 在 CV 中跳过验证组。
