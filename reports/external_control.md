# 外部文本控制实验：SmartDoc + Tobacco Scientific

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-27 |
| 目的 | 外部数据只保留 SmartDoc 与 Tobacco Scientific，观察纸质稿内容分类与公式召回的变化 |
| 训练清单 | `data/manifests/paper_content_extctl.csv` |
| 相关运行 | `runs/paper-cnn-extctl-01`、`-43`、`-44`、`-nw-01`；对照 `runs/paper-cnn-01`、`runs/paper-cnn-base-43`、`-44`、`-nw-01` |
| 决策记录 | `docs/adr/0016-外部公式数据辅助训练与载体门控.md` |

## 1. 数据组成

| 来源 | 训练 | 验证 | 标签 |
|---|---:|---:|---|
| 自采 `paper_*` | 133 | 30 | 自采 text / formula |
| SmartDoc 2015 Ch1 | 500 | 0 | text |
| Tobacco3482 Scientific | 261 | 0 | text |
| **合计** | **894** | **30** | 训练 text 830 / formula 64 |

与 `paper_content.csv` 的区别：

- 不使用 IAM 手写行；
- 不使用 IM2LaTeX 公式裁剪；
- Tobacco 只取 `Scientific` 子类，不再混入其他文档类型；
- SmartDoc 从 250 张增加到 500 张。

因此这是一个**纯 A4 文本外部数据**的对照，外部部分没有任何公式图。

## 2. 训练配置

与 `paper-cnn-01` 相同：MobileNetV3-Small，224 输入，冻结 3 轮后微调，最多 6 轮，早停 patience 2；自采验证集 30 张只用于早停与评估。

三个种子 42 / 43 / 44 使用同一清单与配置。类别权重默认按训练集频次平衡；由于训练集只有 64 张 formula、830 张 text，formula 类权重约为 text 的 12.9 倍。

## 3. 结果

### 3.1 单模型

| 模型 | 训练数据 | 准确率 | 宏 F1 | text 召回 | formula 召回 | 混淆矩阵 |
|---|---|---:|---:|---:|---:|---|
| `paper-cnn-01`（种子 42） | 自采 + 全部外部数据 | 70.00% | 69.70% | 90% | 60% | `[[9,1],[8,12]]` |
| `paper-cnn-base-43` | 自采 + 全部外部数据 | 73.33% | 72.85% | 90% | 65% | `[[9,1],[7,13]]` |
| `paper-cnn-base-44` | 自采 + 全部外部数据 | 66.67% | 66.52% | 90% | 55% | `[[9,1],[9,11]]` |
| `paper-cnn-extctl-01`（种子 42） | 自采 + SmartDoc/Scientific | 80.00% | 78.47% | 80% | 80% | `[[8,2],[4,16]]` |
| `paper-cnn-extctl-43`（种子 43） | 自采 + SmartDoc/Scientific | 86.67% | 85.00% | 80% | 90% | `[[8,2],[2,18]]` |
| `paper-cnn-extctl-44`（种子 44） | 自采 + SmartDoc/Scientific | 83.33% | 81.68% | 80% | 85% | `[[8,2],[3,17]]` |
| `paper-cnn-extctl-nw-01`（种子 42，无类别权重） | 自采 + SmartDoc/Scientific | 66.67% | 66.52% | 90% | 55% | `[[9,1],[9,11]]` |
| `paper-cnn-base-nw-01`（种子 42，无类别权重） | 自采 + 全部外部数据 | 66.67% | 66.52% | 90% | 55% | `[[9,1],[9,11]]` |

### 3.2 多种子汇总

| 组别 | 种子数 | 准确率均值 ± 总体标准差 | 宏 F1 均值 ± 总体标准差 |
|---|---:|---:|---:|
| 全部外部数据 | 3（42 / 43 / 44） | 70.00% ± 2.72 | 69.69% ± 2.58 |
| SmartDoc + Scientific（平衡类别权重） | 3（42 / 43 / 44） | **83.33% ± 2.72** | **81.72% ± 2.67** |
| SmartDoc + Scientific（无类别权重） | 1（42） | 66.67% | 66.52% |
| 全部外部数据（无类别权重） | 1（42） | 66.67% | 66.52% |

平衡权重下，控制组三个种子均值为 83.33%，全部外部数据组为 70.00%。但关闭类别权重后，两组种子 42 都是 66.67%，混淆矩阵也完全相同。说明**当前增益来自公式类权重，而不是 SmartDoc/Scientific 的数据来源**；在相同权重设置下，没有观察到这两类外部数据的额外收益。

### 3.3 错误变化（种子 42 对 `paper-cnn-01`）

| 样本 | 真实 | 原模型 | 控制组 | 说明 |
|---|---|---|---|---|
| `formula_11` | formula | text | formula | 修复 |
| `formula_12` | formula | text | formula | 修复 |
| `车位转让协议正面` | formula | text | formula | 修复 |
| `IMG_20261126_013746` | formula | text | formula | 修复 |
| `0731_1` | formula | text | formula | 修复 |
| `formula_page_06` | formula | formula | text | 新增错误 |
| `IMG_20261126_013809` | text | text | formula | 新增错误 |

净变化：formula 召回 12/20 → 16/20，text 召回 9/10 → 8/10，总计 21/30 → 24/30。

## 4. 解释与限制

1. **外部文本数据本身可能提供了更难的负样本**：Scientific 与 SmartDoc 都是密集 A4 文本页，模型需要把“密集文字”和“公式页”区分开，可能减少了对干净公式裁剪的依赖。
2. **类别权重是主要混杂因素，且消融后两组无差异**：纯文本外部数据使训练集变成 830 text / 64 formula，formula 类权重约为 12.9 倍；关闭类别权重后，控制组与全部外部数据组的种子 42 都是 66.67%，formula 召回 55%。因此不能把 83.33% 归因于 SmartDoc/Scientific 的数据内容。
3. **验证集只有 30 张**：单张影响 3.3 个百分点；三个种子方向一致，但仍不能替代更大验证集或测试集。
4. **尚未接入主链路**：该模型只处理纸质稿分支；载体门控尚未接入网页，当前网页仍使用单模型。

## 5. 复现

```bash
# 生成外部文本对照清单（仅 SmartDoc + Tobacco Scientific）
python3 scripts/build_paper_content_manifest.py \
  --mode smartdoc-scientific --smartdoc 500 \
  --out data/manifests/paper_content_extctl.csv

# 训练（种子 42 / 43 / 44）
docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app/src:/app \
  docnorm:cpu-arm64 python scripts/train_paper_classifier.py \
  --manifest data/manifests/paper_content_extctl.csv \
  --out runs/paper-cnn-extctl-01 --epochs 6 --freeze-epochs 3 \
  --input-size 224 --batch-size 32 --patience 2 --seed 42
```

## 6. 结论

在这 30 张纸质验证集上，只用 SmartDoc + Tobacco Scientific 并启用平衡类别权重时，三个种子的准确率为 80.00%–86.67%，均值 83.33%；全部外部数据组同种子均值为 70.00%。但关闭类别权重后，两组种子 42 都是 66.67%，混淆矩阵完全一致。结论是：**提升来自公式类权重，而不是这两类外部数据本身**。如果目标是提升公式召回，优先调类别权重或采样策略，而不是更换外部数据源；这两类数据可以保留为文本辅助，但没有证据表明它们比原外部组合更好。
