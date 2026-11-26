# 外部预训练模型在自采真实数据上的直接测试

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-27 |
| 测试数据 | 自采 340 张（train 236 / val 51 / test 53，已按 `exclusions.csv` 排除） |
| 模型 | `pretrain-external-01`（2,400 张外部预训练）、`pretrain-external-small`（600 张外部预训练） |
| 预处理 | 自动四角 + 人工四角回退 + 拉正，不增强；另做无拉正对照 |
| 用途 | 只诊断外部预训练权重的零样本迁移，不参与任何调参或模型选择 |
| 决策记录 | `docs/adr/0016-外部公式数据辅助训练与载体门控.md` |

## 1. 结论

**不能直接使用。** 两个外部预训练模型在 340 张真实数据上的准确率都是 **54.41%**，正好等于“全部判为 text”的多数类基线；公式召回率只有 **0% / 2.58%**。外部验证集上的 93.3% / 95.0% 不能外推到真实拍摄页。

## 2. 全量结果（340 张）

| 模型 | 外部验证 | 真实数据准确率 | 宏 F1 | text 召回 | formula 召回 | 纸质稿准确率 | PPT 准确率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `pretrain-external-01` | 93.3% | 54.41% | 35.24% | 100.00% | 0.00% | 47.92% | 62.84% |
| `pretrain-external-small` | 95.0% | 54.41% | 37.46% | 97.84% | 2.58% | 49.48% | 60.81% |
| 多数类基线（全判 text） | — | 54.41% | 35.24% | 100.00% | 0.00% | 47.92% | 62.84% |

混淆矩阵（行=真实，列=预测，text / formula）：

- `pretrain-external-01`：`[[185, 0], [155, 0]]`
- `pretrain-external-small`：`[[181, 4], [151, 4]]`

`pretrain-external-01` 把 340 张全部判成 text；`-small` 只判出 4 张 formula，其中真正命中的只有 4 张（公式页共 155 张）。

## 3. 分层结果

### 3.1 按数据划分

| 模型 | train 236 | val 51 | test 53 |
|---|---:|---:|---:|
| `pretrain-external-01` | 54.24% | 54.90% | 54.72% |
| `pretrain-external-small` | 53.81% | 56.86% | 54.72% |

三份划分都接近多数类基线，说明这不是验证集偶然波动。

### 3.2 验证集按载体

| 模型 | PPT val 21 张 | 纸质稿 val 30 张 |
|---|---:|---:|
| `pretrain-external-01` | 85.71% | 33.33% |
| `pretrain-external-small` | 85.71% | 36.67% |

PPT 验证集 21 张里有 18 张 text，全判 text 就能得到 85.71%，所以这个数字没有参考价值。纸质稿验证集 30 张里有 20 张 formula，模型仍以判 text 为主，准确率只有 33%–37%。

### 3.3 不做拉正的对照

验证集 51 张直接缩放、不拉正：

- 两个模型都是 56.86%，宏 F1 40.06%，formula 召回 4.35%（23 张公式页只判对 1 张）。
- 与拉正后的 54.90% / 56.86% 基本一致，说明失败原因不是四角拉正，而是模型本身没有学到可迁移的公式特征。

## 4. 与自采微调模型对比

在同样的纸质稿验证集 30 张上：

| 模型 | 准确率 | 宏 F1 | formula 召回 |
|---|---:|---:|---:|
| 外部预训练直接测试 | 33.33% / 36.67% | — | 0% / 5% |
| 现有 CNN `exp-cnn-05` | 70.00% | 69.70% | 60.00%（12/20） |
| 纸质稿专用 `paper-cnn-01` | 70.00% | 69.70% | 60.00%（12/20） |

外部公式数据已经以 400 张 IM2LaTeX 裁剪的形式参与过 `paper-cnn-01` 的混合训练，但结果与现有 CNN 持平，没有把 formula 召回从 60% 抬上去。直接零样本使用则更差。

## 5. 原因判断

1. **域差过大**：IM2LaTeX 是白底、干净渲染的公式裁剪；真实数据是整页拍摄，公式只占页面一小部分，还带透视、光照、纸张纹理和手写。
2. **任务层级不一致**：外部公式图是“裁剪级”样本，真实标签是“整页是否含公式”。把裁剪图当整页训练，模型学到的是“干净公式图 = formula”，而不是“页面里出现公式 = formula”。
3. **外部验证集同源**：外部验证集与训练集来自同一批数据，93%–95% 只能说明模型拟合了外部分布，不能说明跨域能力。
4. **类别先验**：真实页面大多数区域是文字，模型在整页上倾向输出 text；公式页的公式占比小，全局池化后信号被文字淹没。

## 6. 建议

1. **不要把外部预训练权重直接接到网页或主链路**；当前结果低于现有自采 CNN 的 80.39%（51 张验证集）。
2. 外部公式数据要继续参与，应做**域适配**，而不是直接当整页训练：
   - 把公式裁剪贴到真实纸张背景上，合成“公式只占页面一小块”的训练页；
   - 或训练 patch 级公式检测器，再对整页做 top-k 聚合；
   - 或只用外部数据做初始化，随后在自采训练集上充分微调，并以自采验证集做多种子对比。
3. 更直接的收益来自**补自采公式页**，尤其是公式占比小、手写、倾斜和室内光场景；当前 30 张纸质稿验证集里仍有 8 张公式页被判成 text。
4. 若继续做合成或 patch 方案，合成样本只进训练集，自采 val/test 保持冻结，并披露来源与生成脚本。

## 7. 复现

```bash
# 全量 340 张，标准拉正
docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app/src:/app \
  docnorm:cpu-arm64 python scripts/eval_pretrained_on_self.py \
  --checkpoint runs/pretrain-external-01/backbone.pt \
  --checkpoint runs/pretrain-external-small/backbone.pt \
  --split all --json-out reports/pretrained_zero_shot.json

# 验证集不拉正对照
docker run --rm -v "$PWD:/app" -w /app -e PYTHONPATH=/app/src:/app \
  docnorm:cpu-arm64 python scripts/eval_pretrained_on_self.py \
  --checkpoint runs/pretrain-external-01/backbone.pt \
  --checkpoint runs/pretrain-external-small/backbone.pt \
  --split val --no-rectify \
  --json-out reports/pretrained_zero_shot_raw_val.json
```
