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
├── external_control.md         外部文本对照（SmartDoc + Tobacco Scientific）
├── web_integration.md          网页双分支接入与验证集路由评估
├── ppt_quad.md                 人工四角标签训练的 PPT 四角回归与检测对比
├── routed_pipeline.json        双分支路由机器可读结果
├── spatial_skew*.json          空间偏度压力测试与门控阈值/TTA 结果
├── gate_skew*.json             载体门控偏度评估结果
├── eval_paper/                 纸质验证逐样本预测 CSV
├── baseline_classic.md         传统基线
├── cnn_validation.md           CNN 验证与错例
├── rectify_detection.md        四角检出评估
├── enhance_validation.md       增强评估
├── env_validation.md           环境验证
├── annotation_audit.md         标注审计
├── privacy_audit.csv           隐私复核审计记录
├── synth_ppt_pilot.md          合成投影 PPT 试点示例与重训门槛
├── synth_ppt_preview.jpg       24 组合成投影预览
├── synth_ppt_layouts.jpg       24 张课件页版式
├── synth_ppt_pairs.jpg         4 组“课件原图 / 投影合成”对照
├── synth_ppt_v2_preview.jpg    v2 160 组训练集合成预览
├── synth_ppt_v2_layouts.jpg    v2 课件页版式
├── manual_4x3_sample.md         只用 4:3 人工四角的合成示例说明
├── manual_4x3_preview.jpg       16 组 4:3 人工四角合成预览
├── manual_4x3_pairs.jpg         4 组“原场景 / 合成”对照
├── manual_4x3_layouts.jpg       16 张 4:3 示例版式
├── synth_ppt_v3_training.md     严格 4:3 背景的 v3 训练对照
├── synth_ppt_v3_cv.json         v3 15 次运行、逐折与 OOF 指标
├── synth_ppt_test.md            合成模型测试集复验（负迁移）
├── synth_test_eval.json         测试集复验机器可读结果
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
| `external_control.md` | 外部文本对照：仅 SmartDoc + Tobacco Scientific | `runs/paper-cnn-extctl-*` |
| `web_integration.md` | 网页载体门控 + 双分支分类接入与评估 | `reports/routed_pipeline.json`、`reports/figures/eval_*` |
| `final_test.md` | v4 测试集一次性评估、95% CI、McNemar 与错误分析（v4 历史，M3 未通过） | `reports/final_test.json`、`reports/final_test_predictions.csv` |
| `test_failure_analysis.md` | 测试失败根因：分格退化、PPT 过拟合、标签边界与门控/拉正影响 | `reports/final_test.json` |
| `hard_cases_val.csv` | 验证集错误与低置信样本清单，用于定向补采/复核（不使用测试集） | `reports/eval_paper/routed_val.csv` |
| `cv_oof.md` | 5 折分组 CV、3 种子、OOF 校准/阈值/融合与验证集检查 | `reports/cv_oof.json`、`reports/cv_oof_predictions.csv` |
| `cross_carrier.md` | 纸质模型直接验证 PPT 样本的跨载体评估 | `reports/cross_carrier.json` |
| `test_set_paths.csv/.md/.txt` | 53 张测试集样本的绝对路径清单（只读） | `data/splits/split_v4.json` |
| `test_set_links.md` / `test_set_gallery.html` | 测试集 53 张的可点击相对路径与缩略图画廊 | `reports/test_set_paths.csv` |
| `test_quality_analysis.md` | 测试集清晰度/分辨率与错误关系核查 | `reports/final_test.json` |
| `synth_ppt_pilot.md` | 合成投影 PPT 24 组示例、版式/投影核查与重训门槛 | `reports/synth_ppt_*.jpg`、`data/synthetic/ppt_projection_v1/manifest.csv` |
| `synth_ppt_training.md` | 合成 v2 训练试点：160 组、5 折 CV 与 fold1 结果 | `reports/synth_ppt_cv.json`、`runs/exp-cnn-ppt-synth-v2-*` |
| `manual_4x3_sample.md` | 只用 4:3 人工四角标注的 16 组合成示例 | `reports/manual_4x3_*.jpg`、`data/synthetic/manual_4x3_demo/manifest.csv` |
| `synth_ppt_v3_training.md` | 严格 4:3 背景的 v3 160 组、5 折结果与 v2 对照 | `reports/synth_ppt_v3_cv.json`、`runs/exp-cnn-ppt-synth-v3-*` |
| `synth_ppt_test.md` | 合成模型测试集复验：CV 增益未迁移，v2/v3 不接入 | `reports/synth_test_eval.json`、`reports/synth_test_eval.csv` |
| `repro_check.md` | v4 冻结提交上的测试复现核验（v4 历史，结果一致，指标未达标） | `reports/final_test_repro.json` |
| `ppt_quad.md` | 人工四角标签训练的 PPT 四角回归与 OpenCV 对比 | `runs/quad-ppt-01/quad_ppt.pt` |
| `quad_localization.md` | PPT/纸质分载体四角模型、端到端接入评估与门控审计 | `runs/quad-ppt-02`、`runs/quad-paper-01`、`reports/quad_routing_eval.json` |
| `stage_audit.md` | v5 最终阶段门禁审计（M1–M4 通过）与 v4 历史审计、文档/数据/模型一致性核查 | `reports/model_manifest.csv`、`reports/stage_audit.md` |
| `model_manifest.csv` | 线上模型路径、大小、SHA-256 与验证指标 | `runs/` 权重 |
| `docs/15-空间偏度优化调研.md` | 不新增样本的合成偏度压力测试与门控优化 | `reports/spatial_skew*.json`、`reports/figures/spatial_skew_*` |
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
