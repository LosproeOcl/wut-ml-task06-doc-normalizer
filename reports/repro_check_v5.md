# 复现核验记录（v5）

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-28 |
| 冻结提交 | `22d9fb2`（tag `m3-v5-20261128`） |
| 环境 | Docker `docnorm:cpu-arm64`；macOS arm64 宿主 + Linux arm64 容器；CPU；Python 3.11；PyTorch 2.15 CPU |
| 数据 | `data/splits/split_v5.json` + `data/manifests/sample_manifest_v5.csv`（哈希校验通过，合格 472 张） |
| 模型 | `carrier-gate-v5-01`、`exp-cnn-ppt-v5`、`paper-cnn-v5-s45`/`s47`、`exp-cnn-v5`、`exp-svm-v5` |
| 配置 | `quad_policy=off`、`gate_threshold=0.3`、`gate_tta=true`；分类拉正 PPT/纸质 50/150 |
| 命令 | 与 `reports/final_test_v5.md` 第 6 节完全相同，仅输出文件名改为 `*_repro` |
| 首次结果 | `reports/final_test_v5.json`：93.06% / F1 92.65%，混淆 `[[42,0],[5,25]]` |
| 复跑结果 | `reports/final_test_v5_repro.json`：93.06% / F1 92.65%，混淆 `[[42,0],[5,25]]` |
| 差异 | 准确率 0.00 pp；宏 F1 0.00 pp；**逐样本预测与概率完全一致（72/72）** |
| 结论 | 复现一致，v5 测试集评估结果可复现；M3 指标项在 v5 口径下通过 |

## 说明

1. 复跑使用与首次完全相同的权重、清单、划分与环境变量，未修改模型、配置或测试标签。
2. 本次复跑只用于核验确定性，不作为模型选择依据；测试集仍不得用于调参。
3. 逐样本 CSV 见 `reports/final_test_v5_predictions.csv` 与 `reports/final_test_v5_repro_predictions.csv`。
4. v4 的复现记录（67.92%，tag `m3-eval-20261127`）保留在 `reports/repro_check.md`，仅作历史对照。
