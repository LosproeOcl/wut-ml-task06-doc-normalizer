# 图表索引

本目录图表由 `scripts/make_report_figures.py` 生成，数据来自 `runs/*/metrics.json` 与 `predictions_val*.csv`。

| 文件 | 内容 |
|---|---|
| `model_comparison.png` | 传统 ML、CNN、特征融合、CNN+BiLSTM、GA 在 `split_v3` 验证集上的准确率与宏 F1 对比 |
| `corner_policy_comparison.png` | 人工四角三种训练策略（none / fallback / always）对 SVM 与 CNN 的影响 |
| `confusion_matrices.png` | SVM、最佳 CNN、特征融合、CNN+BiLSTM 的混淆矩阵 |
| `training_curves.png` | 各 CNN 实验的验证准确率与验证损失曲线 |
| `lstm_comparison.png` | CNN+BiLSTM 的种子方差、3 种子平均、5 折 CV 与验证集选权重的对比 |
| `external_comparison.png` | 外部预训练 2,400 / 600 张与无外部对照的种子方差对比 |
| `screen_detector_curves.png` | 屏幕检测器的损失、验证 IoU、学习率与梯度范数曲线 |
| `screen_gate_curves.png` | 屏幕存在性门控的损失、验证准确率、学习率与梯度范数曲线 |
| `carrier_gate_curves.png` | PPT/幕布 vs A4 纸质稿场景门控（carrier-gate-01）的训练诊断，对应 F12 |
| `paper_model_curves.png` | 纸质稿专用内容模型（paper-cnn-01）的训练诊断，对应 F13 |

说明：

1. 验证集 51 张，单张样本约影响 2 个百分点；图中差异需结合 McNemar 检验解读。
2. 容器默认未安装中文字体。生成时把系统字体挂载到 `/fonts/cjk.ttc`，或设置 `CJK_FONT` 指向字体文件，否则中文会显示为方块。
3. 测试集未参与任何训练、调参或图表选择。
4. 外部预训练对照 `exp-cnn-ext-01`（2,400 张）与 `exp-cnn-ext-02`（600 张）只用于初始化，不进入自采验证/测试；主实验仍使用自采数据，来源见 `data/manifests/external_aux*.csv`。
5. CNN+BiLSTM 的 84.3% 是单次种子结果；换种子与 5 折集成都回到 80.4% 以下，图中只作探索记录。
