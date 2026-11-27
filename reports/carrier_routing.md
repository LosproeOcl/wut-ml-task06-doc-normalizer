# PPT / A4 纸质稿双分支实验记录

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-27 |
| 数据划分 | `split_v4`，测试集未参与 |
| 目标 | 先用场景门控区分 PPT/幕布与 A4 纸质稿，再验证纸质稿专用内容模型是否优于现有单模型 |
| 相关运行 | `runs/carrier-gate-01/`、`runs/paper-cnn-01/`、`runs/paper-cnn-extctl-01/43/44` |
| 决策记录 | `docs/adr/0016-外部公式数据辅助训练与载体门控.md` |

## 1. 背景

外部数据（SmartDoc、Tobacco3482、IAM、IM2LaTeX）在 A4 纸质稿上表现较好，但直接混入 PPT 训练会拉低屏幕场景的区分度。因此把任务拆成两层：

1. **场景门控**：整图二分类 `screen`（PPT/幕布）与 `other`（A4 纸质稿）；
2. **内容分类**：PPT 分支沿用现有 CNN，纸质稿分支尝试用自采 paper + 外部 A4 数据训练专用模型。

## 2. 数据组成

### 2.1 场景门控 `data/manifests/carrier_gate.csv`

| 来源 | 训练 | 验证 | 说明 |
|---|---:|---:|---|
| SCB screen | 1,000 | 500 | 投影幕布正类 |
| 自采 `ppt_*` | 103 | 0 | 自采训练集，验证集不参与 |
| SmartDoc / Tobacco / IAM / IM2LaTeX | 1,000 | 500 | 按 4:4:1:1 抽样作为纸质负类 |
| 自采 `paper_*` | 133 | 0 | 自采训练集 |
| **合计** | **2,236** | **1,000** | screen 1,103 / other 1,133 |

### 2.2 纸质稿内容模型 `data/manifests/paper_content.csv`

| 来源 | 训练 | 验证 | 标签 |
|---|---:|---:|---|
| 自采 `paper_*` | 133 | 30 | 自采 text / formula |
| SmartDoc | 250 | 0 | text |
| Tobacco3482 | 200 | 0 | text |
| IAM | 50 | 0 | text |
| IM2LaTeX | 400 | 0 | formula |
| **合计** | **1,033** | **30** | 训练 text 569 / formula 464；验证 text 10 / formula 20 |

自采验证集只有 30 张纸质稿，单张约影响 3.3 个百分点，结论只作方向判断。

## 3. 场景门控结果

`carrier-gate-01`：MobileNetV3-Small，输入 160，3 轮，batch 48。

| 验证集 | 准确率 | 宏 F1 | 混淆矩阵（other / screen） |
|---|---:|---:|---|
| 外部验证 1,000 张 | 1.0000 | 1.0000 | `[[500, 0], [0, 500]]` |
| 自采验证 51 张 | 1.0000 | 1.0000 | 51/51 全对 |

外部验证集与训练集同源，难度偏低；自采验证仅 51 张，因此 100% 不能直接外推为线上指标，但方向明确：混合 SCB 屏幕数据与外部 A4 数据后，模型可以稳定区分两类载体。

## 4. 纸质稿专用内容模型结果

`paper-cnn-01`：MobileNetV3-Small，输入 224，先冻结 3 轮再微调，早停于第 4 轮。

| 指标 | 纸质稿专用模型 | 现有 CNN `exp-cnn-05`（同 30 张） |
|---|---:|---:|
| 准确率 | 0.7000 | 0.7000 |
| 宏 F1 | 0.6970 | 0.6970 |
| 混淆矩阵 | `[[9, 1], [8, 12]]` | `[[9, 1], [8, 12]]` |

- 两模型在 30 张中 28 张一致；错误均集中在“纸质公式被判成 text”。
- 专用模型把 `车位转让协议反面` 判对，但把 `formula_11` 判错，净效果抵消。
- 按 0.2–1.0 的权重融合两模型概率，准确率仍为 0.70；权重 0.5/0.6 时降到 0.6667。

结论：外部 A4 数据能训练出可用的场景门控，但还没有把纸质稿内容分类精度抬高于现有 CNN。外部公式图（IM2LaTeX）与手机拍摄的整页公式存在明显域差，混合训练没有带来可测收益。

## 5. 结论与下一步

1. **场景门控已接入网页主链路**：选择 PPT / 纸质分支；自采验证 51/51，但训练集审计 336/338，存在 `IMG_6178` 等高置信错误，页面提供手动载体重试。
2. **纸质稿分支已接入 extctl 集成**：`paper-cnn-extctl-01/43/44` 三模型概率平均，自采纸质验证 80.00%；`paper-cnn-01` 仅作为历史对照。
3. **优先补自采纸质公式数据**：倾斜、室内光、整页拍摄的公式页，比继续加外部裁剪公式图更有价值。
4. **若要继续混合训练**：先按来源分层采样并做域匹配增强（透视、光照、整页上下文），再以自采验证集做 McNemar 检验，避免被 30 张小验证集的波动误导。

## 6. 复现

```bash
# 构建清单
PYTHONPATH=src python3 scripts/build_carrier_gate_manifest.py
PYTHONPATH=src python3 scripts/build_paper_content_manifest.py

# 场景门控
docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app/src \
  docnorm:cpu-arm64 python scripts/train_screen_gate.py \
  --manifest data/manifests/carrier_gate.csv --out runs/carrier-gate-01 \
  --epochs 3 --input-size 160 --batch-size 48 --patience 2

# 纸质稿专用内容模型
docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app/src:/app \
  docnorm:cpu-arm64 python scripts/train_paper_classifier.py \
  --manifest data/manifests/paper_content.csv --out runs/paper-cnn-01 \
  --epochs 6 --freeze-epochs 3 --input-size 224 --batch-size 32 --patience 2
```

图表：`reports/figures/carrier_gate_curves.png`、`reports/figures/paper_model_curves.png`。


## 7. 2026-11-27 网页接入与门控审计

- 门控已接入：paper → 纸质 CNN 集成，ppt → `exp-cnn-ppt-dedup-fw`，模型缺失回退 SVM；全链路验证集 86.27% / 宏 F1 86.19%。
- 门控训练清单仍为旧版 2,236 张，未纳入 2026-11-27 新增的 102 张实拍训练样本；审计 338 张训练集正确 336 张（99.4%）。
- 错误样本：`IMG_6178`（PPT 近景 → paper，P(ppt)=0.082，阈值无法修复）；`fc714b...`（paper → ppt，P=0.314，阈值提到 0.35 可修复但会降低偏度鲁棒性）。
- 兜底：结果卡 `uncertain` 标记 + “按 PPT / 按纸质重试”，不自动跨分支切换（自动切换实测降至 80.39%）。
