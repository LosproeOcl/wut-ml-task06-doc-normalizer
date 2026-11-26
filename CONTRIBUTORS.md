# 贡献者

## 课程项目组

项目组成员与分工见 [`README.md`](README.md) 第 7 节与 [`docs/05-项目计划与分工.md`](docs/05-项目计划与分工.md)。

## 数据层校验脚本

`scripts/check_manifest.py` 与 `scripts/check_dataset.py` 的清单校验、磁盘一致性检查思路来自 PR #1：

- 原作者：张毅卓（GitHub [@qingwu0731](https://github.com/qingwu0731)）
- 原 PR：[#1 实现数据层——样本清单校验、分组划分与图像读取](https://github.com/LosproeOcl/wut-ml-task06-doc-normalizer/pull/1)
- 处理方式：PR 基于较早的 `main`，未直接合并；仅选择性重写为当前数据契约下的只读校验脚本，避免回退现有数据层、`split_v3`、网页双分支与实验产物。
- 贡献记录：对应提交使用 `Co-authored-by: 张毅卓 <289866717+qingwu0731@users.noreply.github.com>`。

## 贡献约定

1. 新增数据校验或实验工具须保持只读，不修改冻结清单、划分与评估产物。
2. 外部贡献如基于旧分支，应先同步最新 `main`，只提交差异，避免大范围回退。
3. 代码、数据与文档贡献均在提交说明或本文件中注明来源。
