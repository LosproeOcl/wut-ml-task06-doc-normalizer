# 投影幕布检测验证记录

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-26 |
| 数据 | SCB-Dataset 教师子集 `screen` 类框；自采 `split_v3` 验证集 51 张 |
| 任务 | 自动四角失败时，用屏幕检测器裁出幕布，再分类 |
| 测试集 | 未参与 |

## 1. 数据来源

- `Projection Screen Detection`（Research Square preprint）收集约 2,093 帧投影幕布数据，但 Data availability 声明不共享数据，无法直接下载。
- `SCB-Dataset`：GitHub `Whiffe/SCB-dataset`，HuggingFace `wintonYF/SCB-Dataset`；教师子集包含 `screen` 类边界框，论文报告 screen 类 mAP@0.5 约 97.9%。
- 实际提取：12,224 张教师子集图像中，6,704 张含 `screen` 框（train 4,834 / val 1,870），清单 `data/manifests/scb_screen.csv`。

## 2. 检测器

- MobileNetV3-Small，输入 224/160，输出归一化幕布框。
- 损失：SmoothL1 + `1 - IoU`。
- 训练：SCB screen 框；验证 IoU 早停。
- 产出：`runs/screen-detector-01/`。

## 3. 集成与评估

`scripts/eval_screen_fallback.py`：

- baseline：自动四角；失败保留原图；
- fallback：自动四角失败 → 屏幕框裁剪 → 裁剪图内四角检测/拉正 → 分类；
- 只替换失败分支，避免影响已成功样本。

## 4. 结果

`screen-detector-01`：800 张训练 / 400 张验证，160 输入，12 轮。

- 验证 IoU 0.5232，IoU@0.5 召回 0.60，中心误差 0.097；
- 自采验证集 baseline 80.39%，screen fallback 80.39%，净变化 0；
- 具体变化：修复 `IMG_6206`（公式→正确），但把 `f3ddcd7b...` 从正确改错，二者抵消。

`screen-detector-02`：1,600 张训练 / 600 张验证，224 输入，20 轮。

- 验证 IoU 0.6551，IoU@0.5 召回 0.7983，中心误差 0.0476；
- 自采验证集 baseline 80.39%，screen fallback 78.43%，净下降 1 张；
- 变化：把 `f3ddcd7b...`（纸质公式页）从正确改错，`IMG_6206` 未被修复。

结论：屏幕检测器定位精度已明显提高，但只在自动四角失败时使用仍会误裁纸质页，当前 fallback 为负收益。需要增加“是否为投影幕布”的存在性分类器或置信门控后再启用；否则保留检测器作为诊断工具，不进入分类主链路。

## 5. 屏幕存在性门控

在 bbox 检测器前增加二分类门控（`screen-gate-01`）：MobileNetV3-Small，输入 160，正类为 SCB screen + 自采 train 的 `ppt_*`，负类为 SCB 无 screen 框 + 自采 train 的 `paper_*`；自采 val 不参与训练。

- 门控训练：2,236 张训练 / 1,000 张 SCB 验证；SCB 验证准确率 91.3%，宏 F1 91.29%，混淆矩阵 `[[440, 60], [27, 473]]`。
- 评估：自动四角失败时，只有门控概率 ≥ 阈值才使用屏幕裁剪；同时使用 `screen-detector-01/02` 两个 bbox，按分类置信度选最佳裁剪。
- 结果：阈值 0.2–0.9 下均为 **82.35% / 81.32%**，只修复 `IMG_6206`，没有新增错误；比 baseline 80.39% 多对 1 张。

结论：门控有效抑制了纸质页误裁剪，使 fallback 从 78.43% 回到 82.35%；但 +1 张仍属小样本波动，暂作为可选分支，不默认进入主链路。
