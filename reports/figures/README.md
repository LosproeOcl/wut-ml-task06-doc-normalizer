# 图表索引

本目录图表由 `scripts/make_report_figures.py` 生成，数据来自 `runs/*/metrics.json` 与 `predictions_val*.csv`。

| 文件 | 内容 |
|---|---|
| `model_comparison.png` | 传统 ML、CNN、特征融合、CNN+BiLSTM、GA 在 `split_v3` 验证集上的准确率与宏 F1 对比 |
| `corner_policy_comparison.png` | 人工四角三种训练策略（none / fallback / always）对 SVM 与 CNN 的影响 |
| `confusion_matrices.png` | SVM、最佳 CNN、特征融合、CNN+BiLSTM 的混淆矩阵 |
| `training_curves.png` | 各 CNN 实验的验证准确率与验证损失曲线 |
| `lstm_comparison.png` | CNN+BiLSTM 的种子方差、3 种子平均、5 折 CV 与验证集选权重的对比 |

说明：

1. 验证集 51 张，单张样本约影响 2 个百分点；图中差异需结合 McNemar 检验解读。
2. 测试集未参与任何训练、调参或图表选择。
3. 所有实验均使用自采数据，未引入 `data/raw_samples/external-assets/`。
4. CNN+BiLSTM 的 84.3% 是单次种子结果；换种子与 5 折集成都回到 80.4% 以下，图中只作探索记录。
