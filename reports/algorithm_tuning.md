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
