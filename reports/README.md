# 报告产物目录说明

本目录存放实验报告、汇报材料与图表。图表源文件须可重新生成。

## 目录结构

```text
reports/
├── figures/           图表输出
├── experiments/       实验记录
├── experiments.csv    实验汇总表
├── metrics.json       最终指标
├── privacy_audit.csv  隐私复核审计记录
└── repro_check.md     复现核验记录
```

## 图表规范

1. 分辨率 300 dpi，白色背景。
2. 使用支持中文的字体，字号不小于 9 磅。
3. 图注须包含数据来源与样本量。
4. 每幅图须保留生成脚本，脚本存放于 `src/docnorm/viz/` 或 `scripts/`。
5. 图表编号与 `docs/06-评估与验收方案.md` 第 7 节一致。

## 实验记录

每次实验在 `experiments/` 下建立独立文件，命名格式为 `exp-YYYYMMDD-NN.md`，内容依据 `docs/templates/实验记录模板.md`。

## 数值追溯

报告中的每项数值须满足以下条件之一。

1. 直接引用 `metrics.json` 或 `experiments.csv` 中的字段。
2. 由 `src/` 或 `scripts/` 下的脚本重新计算得到。

不满足上述条件的数值不得写入报告。
