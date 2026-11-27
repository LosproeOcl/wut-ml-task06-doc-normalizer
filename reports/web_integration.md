# 网页双分支主链路接入记录

| 项目 | 内容 |
|---|---|
| 日期 | 2026-11-27 |
| 决策 | ADR-0017 双分支 + ADR-0018 门控 TTA/0.3 阈值 |
| 评估数据 | 自采 `split_v3` 验证集 51 张；测试集未参与 |
| 相关图表 | `reports/figures/eval_*.png` |

## 1. 接入内容

```text
上传原图
  ├─ 载体门控 carrier-gate-01
  │    ├─ paper → 纸质稿 CNN 集成（paper-cnn-extctl-01/43/44）
  │    ├─ ppt   → PPT CNN（exp-cnn-05）
  │    └─ 门控缺失 → 传统 SVM
  └─ 拉正 / 增强 → 分支分类 → 类别与概率
```

- 门控输入：上传原图（与训练分布一致），默认 -12°/0°/12° 旋转 TTA + 0.3 阈值；
- 分类输入：拉正后的图像；
- 分支模型缺失或加载失败时自动回退传统 SVM；
- 响应新增 `carrier`、`carrier_probabilities`、`branch`；
- `/api/health` 新增 `routing` 与 `routing_ready`；
- 网页结果卡显示“载体 / 分支”徽标。

### 模型路径

| 用途 | 默认路径 | 环境变量 |
|---|---|---|
| 载体门控 | `runs/carrier-gate-01/screen_gate.pt` | `DOCNORM_CARRIER_GATE` |
| 纸质稿集成 | `runs/paper-cnn-extctl-01/paper_cnn.pt`、`-43`、`-44` | `DOCNORM_PAPER_MODELS`（`:` 分隔） |
| PPT 分类 | `runs/exp-cnn-05/cnn.pt` | `DOCNORM_PPT_MODEL` |
| SVM 兜底 | `runs/exp-*/svm.joblib` 中验证集最佳 | `DOCNORM_CLASSIC_MODEL` |

模型权重不进入版本控制；部署时必须挂载包含 `runs/` 的仓库目录。

## 2. 验证集结果

`scripts/eval_routed_pipeline.py` 用网页同款 `_classify` 在 51 张验证集逐页评估：

| 指标 | 数值 |
|---|---:|
| 准确率 | **84.31%**（43/51） |
| 宏平均 F1 | **84.01%** |
| text 召回 | 89.29%（25/28） |
| formula 召回 | 78.26%（18/23） |
| PPT 分支准确率 | 90.48%（19/21） |
| 纸质分支准确率 | 80.00%（24/30） |
| 分支分布 | paper 30 / ppt 21 |
| 混淆矩阵 | `[[25, 3], [5, 18]]` |

2026-11-27 按人工复核修正 11 张样本的公式/文字标签后，旧模型在修正标签上为 84.31%；旧的 88.24% 是修正前标签结果，不再作为当前指标。模型尚未在修正标签上重训，因此该数字是保守值。对照单模型 CNN 旧标签 80.39%；测试集尚未评估。

## 3. 网页验证

2026-11-27 重启 `t06-web` 后实测：

| 样本 | 载体 | 分支 | 结果 |
|---|---|---|---|
| `formula_14` | paper 99.99% | paper-cnn-ensemble-3 | formula 54.3% |
| `0731_1` | paper 97.3% | paper-cnn-ensemble-3 | formula 78.8% |
| `IMG_4598` | ppt 99.99% | ppt-cnn-exp-cnn-05 | formula 89.2% |
| `IMG_6010` | ppt 99.99% | ppt-cnn-exp-cnn-05 | text 96.5% |

`/api/health` 的 `routing.routing_ready=true`，三类模型路径均正确返回。单张端到端耗时约 20–160 ms（不含首次模型加载）。

## 4. 评估图

`scripts/make_eval_figures.py` 生成 6 张多维度图（PNG 300 dpi + SVG）：

| 图 | 内容 |
|---|---|
| `eval_pipeline_comparison` | 多数类、单模型、纸质集成、双分支路由的准确率与宏 F1 |
| `eval_seed_stability` | 全部外部数据 vs SmartDoc + Scientific 的三种子稳定性 |
| `eval_weight_ablation` | 平衡权重 / 无权重消融，展示增益来源 |
| `eval_confusion_matrices` | 单模型与纸质集成的混淆矩阵 |
| `eval_recall_comparison` | text / formula 分召回对比 |
| `eval_probability_shift` | 逐样本 P(formula) 迁移与关键翻转 |

生成需要中文字体；容器内挂载 `/fonts/cjk.ttc` 或设置 `CJK_FONT`。

## 5. 限制

1. 51 张验证集与 30 张纸质验证集样本量小；84.31% 的单点结果需结合置信区间解读，且模型尚未在修正标签上重训。
2. 门控在验证集 51/51，但训练使用了自采训练集与外部数据；测试集尚未验证。
3. 纸质分支的增益与类别权重相关，不能据此宣称数据来源本身更优，见 `reports/external_control.md`。
4. 模型文件缺失时自动回退 SVM，此时 `branch=classic-svm`，网页仍可用但不再享受双分支收益。
5. 首次分析需加载多个模型，冷启动比后续请求慢；生产部署可预热。
