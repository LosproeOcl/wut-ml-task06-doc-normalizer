> 本文件为 v4 历史复现记录。v5 复现见 `reports/repro_check_v5.md`。

# 复现核验记录

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-27 |
| 冻结提交 | `ec5e3af`（tag `m3-eval-20261127`） |
| 环境 | Docker `docnorm:cpu-arm64`；Linux arm64；CPU；Python 3.11；PyTorch 2.15 CPU |
| 模型 | `carrier-gate-01`、`exp-cnn-ppt-dedup-fw`、`paper-cnn-extctl-01/43/44`、`exp-20261126-08` SVM |
| 配置 | `quad_policy=off`、`quad_display=true`；分类拉正 PPT/纸质 50/150 |
| 命令 | `DOCNORM_*` 指定上述权重后运行 `python scripts/eval_final_test.py` |
| 首次结果 | `reports/final_test.json`：67.92% / F1 67.92%，混淆 `[[18,10],[7,18]]` |
| 复跑结果 | `reports/final_test_repro.json`：67.92% / F1 67.92%，混淆 `[[18,10],[7,18]]` |
| 差异 | 准确率 0.00 pp；宏 F1 0.00 pp；逐样本预测与概率完全一致 |
| 结论 | 复现一致；但测试指标未达 85%，M3 失败、M4 阻塞 |

## 说明

1. 复跑使用与首次完全相同的工作区内容和环境变量，未修改模型、配置或测试标签。
2. 本次复跑只用于核验确定性，不作为模型选择依据；测试集仍不得用于调参。
3. 复跑耗时约 60 秒；逐样本 CSV 见 `reports/final_test_predictions.csv` 与 `reports/final_test_repro_predictions.csv`。
4. 复现结果不改变 M3/M4 审计结论：当前链路 67.92% 低于 85% 验收线。
