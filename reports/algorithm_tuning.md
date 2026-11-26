# 算法优化记录

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-26 |
| 数据 | 校内自采 `split_v3`：训练 236、验证 51、测试 53 |
| 外部数据 | 未使用；`data/raw_samples/external-assets/` 未进入任何训练或评估 |
| 测试集 | 未参与训练、调参、TTA 或模型选择 |
| 运行日志 | 每个新实验在 `runs/<exp_id>/` 生成 `run.json`、`train.log`、`epochs.csv` |

## 1. 必做 ML 与 DL 对比

| 类别 | 方法 | 验证准确率 | 宏 F1 |
|---|---|---:|---:|
| ML | 传统特征 + SVM | 76.5% | 75.7% |
| ML | 传统特征 + RF | 72.5% | 71.2% |
| DL | MobileNetV3-Small，224，人工四角 fallback | **80.4%** | 79.0% |
| DL | MobileNetV3-Small，320，减弱增强 | 78.4% | 77.2% |
| DL | MobileNetV3-Large，224 | 78.4% | 77.9% |
| DL | MobileNetV3-Large，正则化 | 80.4% | **79.8%** |
| DL | EfficientNet-B0，224 | 74.5% | 73.5% |

结论：当前 236 张训练样本下，MobileNetV3-Small + 224 是性价比最高的 DL 基线；更大模型和更高分辨率没有稳定收益。

## 2. 复合算法尝试

| 方法 | 验证准确率 | 宏 F1 | 判断 |
|---|---:|---:|---|
| CNN + SVM 概率平均 | ≤80.4% | ≤79.0% | 无提升 |
| CNN 不确定时路由到 SVM | ≤80.4% | ≤79.0% | 无提升 |
| 传统 1836 维 + CNN 576 维，融合 SVM | **80.4%** | **79.4%** | 稳定，准确率持平，F1 略高 |
| 传统特征 + CNN 嵌入 + PCA128 + SVM | 80.4% | 79.4% | 同融合 SVM |
| CNN + BiLSTM（默认种子） | **84.3%** | **84.3%** | 单次结果，方差大 |
| CNN + BiLSTM（种子 43/44） | 80.4% | 80.2% / 80.0% | 回到基线 |
| CNN + BiLSTM（3 种子平均） | 80.4% | 80.2% | 不稳定 |
| CNN + BiLSTM（5 折集成） | 72.5% | 71.7% | 过拟合，不可用 |
| CNN + LSTM 概率融合（验证集选权重） | 86.3% | 86.2% | 验证集选择偏差，偏乐观 |
| 遗传算法特征选择 + SVM | 74.5% | 74.4% | 5 折 CV 84.3%，验证集过拟合 |

### 2.1 特征融合

传统特征 1836 维（版面密度 64、边缘方向 8、HOG 1764）与 MobileNetV3-Small 池化嵌入 576 维拼接为 2412 维，再训练 SVM。验证集 80.4% / 79.4%，与最佳 CNN 准确率相同，宏 F1 高 0.4 个百分点。它证明了 ML 与 DL 特征可以互补，但没有带来准确率突破。

### 2.2 CNN + BiLSTM

把 CNN 的 7×7×576 特征图按行展开为 49 个空间 token，经 BiLSTM 编码后做二分类。默认种子达到 84.3%，混淆矩阵 `[[23, 5], [3, 20]]`，公式召回从 14/23 提升到 20/23。

但该结果不稳定：

- 种子 43：80.4%；
- 种子 44：80.4%；
- 3 个种子概率平均：80.4%；
- 训练集 5 折集成（验证集不参与早停）：72.5%。

训练损失降到 0.001，序列头明显过拟合；84.3% 是验证集上的峰值。**不能把单次 84.3% 当作稳定结论，也不能据此宣称达到 85%。**

### 2.3 遗传算法

把 1836 维特征按来源分为 30 组，用遗传算法选择特征组，适应度为训练集 5 折 CV 准确率。第 12 代最佳 CV 为 84.3%，但验证集只有 74.5%。这是特征选择在 236 张小样本上的典型过拟合，不作为最终方案。

## 3. 无效或负收益的方向

| 尝试 | 结果 |
|---|---|
| 输入 224 → 320 | 80.4% → 78.4% |
| MobileNetV3-Small → Large | 80.4% → 78.4%（正则化后回到 80.4%） |
| EfficientNet-B0 | 74.5% |
| TTA 多尺度 / 五裁剪 | 80.4% → 74.5% |
| CNN + SVM 集成 | 无提升 |
| 置信度路由 | 无提升 |

## 4. 标签审计

5 折交叉验证的 SVM 在训练集上 OOF 准确率 81.4%，有 44 条高置信 disagreement（`reports/train_label_suspects.csv`）。目视抽查发现：

1. 部分 `paper_formula` 页面实际是文字为主的教材/讲义页；
2. 部分 `paper_text` 页面公式很多；
3. 验证集 10 张错误中 7 张属于“文字为主、少量公式”的混合页，另外 3 张是 2023 年、带印章的非课堂材料。

这说明当前瓶颈主要是**标注口径**，不是模型容量。继续换网络、加外部数据或堆融合，收益都会被标签噪声抵消。

## 5. 图表

- `reports/figures/model_comparison.png`
- `reports/figures/corner_policy_comparison.png`
- `reports/figures/confusion_matrices.png`
- `reports/figures/training_curves.png`

## 6. 结论与建议

1. 稳定最佳验证结果约 **80.4%**：CNN fallback、正则化 MobileNetV3-Large、传统+CNN 特征融合三者并列。
2. 复合算法中，**特征融合**是稳定可复现的方案；CNN+BiLSTM 的单次 84.3% 和验证集选权重的 86.3% 都不具备稳定性，不能作为最终指标。
3. 遗传算法在本数据上过拟合，不推荐。
4. 若目标是 85%，优先做标签口径审计与混合页复核，而不是继续增加模型复杂度；51 张验证集上 80.4% 的 95% Wilson 区间约 67.5%–89.0%，点估计与 85% 并不冲突，但不足以宣称达标。
5. 测试集保持冻结，最终方案确定后只评估一次。

## 7. 复现

```bash
# ML 基线
docker run --rm -v "$PWD:/app" -w /app docnorm:cpu-arm64 \
  env PYTHONPATH=/app/src python scripts/train_classic.py \
  --exp-id exp-20261126-08 --no-enhance --corners-policy none

# DL 基线
docker run --rm -v "$PWD:/app" -w /app docnorm:cpu-arm64 \
  env PYTHONPATH=/app/src python scripts/train_cnn.py \
  --exp-id exp-cnn-05 --epochs 15 --freeze-epochs 3 --no-enhance \
  --corners-policy fallback

# 特征融合
docker run --rm -v "$PWD:/app" -w /app docnorm:cpu-arm64 \
  env PYTHONPATH=/app/src python scripts/fusion_eval.py \
  --cnn-run runs/exp-cnn-05 --out runs/fusion-exp-01
```

## 8. 外部辅助预训练（已披露）

（2026-11-26 历史实验）课程要求未禁止外部数据，因此增加一组“仅预训练”的对照实验。外部数据不进入自采清单、验证集或测试集，来源与许可见 `data/manifests/external_aux.csv` 与 `docs/13-外部数据使用说明.md`。2026-11-27 的辅助训练与零样本补充见 8.2。

| 项目 | 内容 |
|---|---|
| 外部数据 | IM2LATEX-100K 1,200 张公式；Tobacco-3482 900 张、IAM 180 张、SmartDoc 120 张文字类 |
| 预训练 | MobileNetV3-Small，160 输入，2 轮，外部验证 93.3% |
| 自采微调（2,400 张预训练） | `exp-cnn-ext-01`，224 输入，15 轮，fallback 人工四角 |
| 自采验证（2,400 张预训练） | 76.5% / 74.2%，低于自采从零微调的 80.4% / 79.0% |
| 小样本预训练 | 600 张（公式 300 + 文字 300），1 轮，160 输入，外部验证 95.0% |
| 小样本自采微调 | `exp-cnn-ext-02`：82.35% / 81.32%，混淆矩阵 `[[27, 1], [8, 15]]` |

结论：

1. 2,400 张外部预训练在上没有收益，反而使初始验证损失升高、13 轮后才恢复到 76.5%；域差距是主因。
2. 降到 600 张、只预训练 1 轮后，`exp-cnn-ext-02` 比纯自采基线多对 1 张验证图（`IMG_6206`），没有新增错误；但只多 1 张，McNemar p=1.0，不能称为稳定提升。
3. 种子 43 对照：外部 600 张 `exp-cnn-ext-03` 只有 68.63% / 63.57%，无外部 `exp-cnn-10` 为 80.39% / 79.44%。82.35% 是种子 42 的峰值，换种子即崩，不能称为稳定提升。
4. 结论：外部内容预训练在本数据上不采用；没有 PPT 幕布内容数据时，小剂量预训练也不稳定。若继续用外部数据，应转向屏幕检测或合成 PPT 页面。

外部实验同样生成完整日志：`runs/pretrain-external-01/` 与 `runs/exp-cnn-ext-01/` 下均有 `run.json`、`train.log`、`epochs.csv`。

### 8.1 公开 PPT 幕布数据调研

检索范围内未找到可直接下载、带文字/公式标签的投影幕布 PPT 实拍数据集。最接近的资源是数字讲义幻灯片（LecSlides-370K、SlideVQA、LPM、SynSlide/RealSlide）和屏幕/行为检测数据（Projection Screen Detection、SCB-Dataset），前者缺少投影畸变与教室光照，后者只有屏幕框而没有课件内容标签。

因此将外部预训练从 2,400 张降到 600 张（公式 300 + 文字 300），只跑 1 轮，作为低强度初始化对照；`runs/exp-cnn-ext-02` 记录该实验。若小样本仍无收益，最终方案不使用外部预训练。

### 8.2 2026-11-27 补充：外部公式数据的两种用法

外部数据不再只做初始化，新增两条仅训练用途：

1. **纸质稿内容辅助训练**：`paper_content.csv` 混合自采 paper 与外部 A4，`paper-cnn-01` 在 30 张自采纸质验证上 70.00% / 宏 F1 69.70%，与现有 CNN 持平，未接入主链路。
2. **载体门控**：`carrier_gate.csv` 混合 SCB 屏幕、自采 PPT/paper 与外部 A4，`carrier-gate-01` 外部验证 1,000 张与自采验证 51 张均全对；作为候选分支，未接入主链路。

同时把 `pretrain-external-01` 与 `pretrain-external-small` 直接用在自采 340 张真实数据上：两者均为 54.41%，等于全判 text 的多数类基线，formula 召回 0% / 2.58%。结论：外部预训练权重不能直接部署；外部公式数据若要继续参与，应做域适配（合成整页、patch 级检测）或补充自采公式页。另做外部文本对照：外部数据只保留 SmartDoc 500 张与 Tobacco Scientific 261 张，不使用 IAM/IM2LaTeX；平衡类别权重下 `paper-cnn-extctl` 三个种子在 30 张纸质验证上为 80.00%–86.67%，均值 83.33%。但关闭类别权重后，该组与全部外部数据组的种子 42 均为 66.67%，说明增益来自公式类权重，不能归因于这两类外部数据本身。详见 `reports/external_control.md`、`reports/carrier_routing.md`、`reports/pretrained_zero_shot.md` 与 ADR-0016。

## 9. 投影幕布检测分支

针对“外部内容数据缺少 PPT 幕布”的问题，改为先定位幕布再分类。公开数据调研结论：

- `Projection Screen Detection` 论文有约 2,093 帧投影幕布框，但 Data availability 声明不共享数据，无法直接下载。
- `SCB-Dataset` 公开（GitHub `Whiffe/SCB-dataset`，HuggingFace `wintonYF/SCB-Dataset`），教师子集包含 `screen` 类框；论文报告 screen 类 mAP@0.5 约 97.9%。

当前实现：

1. `scripts/build_scb_screen_manifest.py`：从 SCB 教师子集提取 screen 框，输出 `data/manifests/scb_screen.csv`。
2. `scripts/train_screen_detector.py`：MobileNetV3-Small bbox 回归，输出归一化幕布框，损失 SmoothL1 + IoU。
3. `scripts/eval_screen_fallback.py`：只在自动四角失败时，用屏幕框裁剪幕布，再在裁剪图内做四角检测/拉正，最后分类。
4. 屏幕检测器只用 SCB 训练；自采验证/测试仍只用于分类评估。

首轮结果：`screen-detector-01`（800/400，160 输入，12 轮）验证 IoU 0.5232、IoU@0.5 召回 0.60；自采验证 baseline 80.39%，screen fallback 80.39%，修复 `IMG_6206` 但改错 `f3ddcd7b...`，净变化 0。

第二轮：`screen-detector-02`（1,600/600，224 输入，20 轮）验证 IoU 0.6551、IoU@0.5 召回 0.7983；但自采 fallback 降到 78.43%，把纸质公式页 `f3ddcd7b...` 改错。说明仅靠 bbox 回归定位不够，必须在自动四角失败时再加“是否投影幕布”的置信门控，否则会误裁纸质页。当前不进入分类主链路。

第三轮：`screen-gate-01`（SCB screen/other + 自采 train 的 ppt/paper，2,236/1,000，160 输入，5 轮）SCB 验证准确率 91.3%、F1 91.29%。在自动四角失败分支加门控，并使用 `screen-detector-01/02` 双 bbox 按分类置信度选择裁剪：阈值 0.2–0.9 下自采验证均为 **82.35% / 81.32%**，只修复 `IMG_6206`，无新增错误；相比 baseline 80.39% 多对 1 张。门控解决了纸质页误裁问题，但增益仍小，暂作为可选分支。
