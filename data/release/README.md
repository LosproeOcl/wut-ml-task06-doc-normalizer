# 发布副本目录说明

本目录存放完成隐私打码的发布副本，用于报告配图、演示文稿与公开仓库。

## 使用规则

1. 本目录中的图像由 `docnorm privacy apply` 生成，不得手工复制原始样本进来。
2. 目录结构与 `data/raw_samples/` 一致，便于按类别查找。
3. 图像文件不纳入版本控制，仅保留目录说明。
4. 对外材料只允许引用本目录中的图像。原始样本不得直接出现在报告、演示文稿与远程仓库中。
5. 发布副本仅用于展示，不得作为训练或评估输入。

## 生成方式

```bash
docnorm privacy apply --input data/raw_samples/01_ppt_text \
  --regions reports/privacy/regions.json --out data/release/01_ppt_text
```

完整的检测、复核与审计流程见 `docs/04-数据采集与标注规范.md` 第 10 节。

## 审计

发布完成后执行下列命令，生成审计记录。

```bash
docnorm privacy audit --input data/release --report reports/privacy_audit.csv
```

审计记录须包含样本标识、区域数量、打码方式、复核人、复核时间与是否通过。
