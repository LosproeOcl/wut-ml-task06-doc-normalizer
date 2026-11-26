# 报告产物目录说明

本目录存放实验报告、汇报材料与图表。图表源文件须可重新生成。

## 目录结构

```text
reports/
├── figures/                    图表输出
├── run_index.csv               全部实验运行索引
├── algorithm_tuning.md         传统基线、CNN、融合与外部预训练对照
├── screen_detection.md         投影幕布检测与 fallback 评估
├── carrier_routing.md          PPT/纸质稿载体门控与纸质稿专用模型
├── pretrained_zero_shot.md     外部预训练权重零样本评估
├── pretrained_zero_shot.json   零样本评估机器可读结果
├── baseline_classic.md         传统基线
├── cnn_validation.md           CNN 验证与错例
├── rectify_detection.md        四角检出评估
├── enhance_validation.md       增强评估
├── env_validation.md           环境验证
├── annotation_audit.md         标注审计
├── privacy_audit.csv           隐私复核审计记录
└── experiments/                逐实验记录（按需创建）
```

## 报告索引

| 报告 | 内容 | 关键产物 |
|---|---|---|
| `algorithm_tuning.md` | 传统基线、CNN、融合、LSTM、外部预训练与屏幕检测分支 | `runs/exp-*` |
| `baseline_classic.md` | 传统特征与 SVM/RF 基线 | `runs/exp-20261126-*` |
| `cnn_validation.md` | MobileNetV3 验证、错例与调参 | `runs/exp-cnn-*` |
| `screen_detection.md` | SCB 幕布检测、屏幕存在性门控与 fallback | `runs/screen-detector-*`、`runs/screen-gate-*` |
| `carrier_routing.md` | 载体门控与纸质稿专用模型 | `runs/carrier-gate-01`、`runs/paper-cnn-01` |
| `pretrained_zero_shot.md` | 外部预训练权重在 340 张真实数据上的零样本评估 | `reports/pretrained_zero_shot.json` |
| `run_index.csv` | 全部运行的一行摘要，供报告引用 | `scripts/index_runs.py` |

## 图表规范

1. 分辨率 300 dpi，白色背景。
2. 使用支持中文的字体，字号不小于 9 磅。
3. 图注须包含数据来源与样本量。
4. 每幅图须保留生成脚本，脚本存放于 `src/docnorm/viz/` 或 `scripts/`。
5. 图表编号与 `docs/06-评估与验收方案.md` 第 7 节一致。

## 实验记录

专题分析报告直接放在 `reports/` 顶层，按主题命名；需要逐实验留档时，在 `reports/experiments/` 下建立独立文件，命名格式为 `exp-YYYYMMDD-NN.md`，内容依据 `docs/templates/实验记录模板.md`。无论采用哪种形式，数值必须能追溯到 `metrics.json`、`run_index.csv` 或可重跑的脚本。

## 数值追溯

报告中的每项数值须满足以下条件之一。

1. 直接引用 `metrics.json`、`run_index.csv`、`pretrained_zero_shot.json` 等运行产物中的字段。
2. 由 `src/` 或 `scripts/` 下的脚本重新计算得到。

不满足上述条件的数值不得写入报告。
