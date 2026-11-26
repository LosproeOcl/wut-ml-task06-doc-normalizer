# 脚本目录说明

本目录存放一次性脚本与运维工具。可复用的业务逻辑应放入 `src/`，不得在此重复实现。

## 计划脚本

| 脚本 | 用途 | 阶段 |
|---|---|---|
| `env_smoke.py` | 检查 Python、依赖版本与运行设备 | M0 |
| `check_manifest.py` | 校验样本清单字段、唯一性与类别分布 | M1 |
| `make_split.py` | 按分组键生成划分文件并计算清单哈希 | M1 |
| `check_dataset.py` | 核对清单记录与实际文件是否一致 | M1、M4 |
| `download_weights.py` | 下载 MobileNetV3 权重并校验哈希 | M1 至 M2 |
| `export_report_assets.py` | 汇总图表与指标至报告目录 | M4 |

## 2026-11-27 新增脚本

| 脚本 | 用途 |
|---|---|
| `build_carrier_gate_manifest.py` | 构建 PPT/纸质稿载体门控清单 |
| `build_paper_content_manifest.py` | 构建纸质稿内容辅助训练清单；`--mode smartdoc-scientific` 生成外部文本对照清单 |
| `train_paper_classifier.py` | 训练纸质稿专用内容模型 |
| `eval_pretrained_on_self.py` | 外部预训练权重在自采真实数据上的零样本评估 |
| `train_screen_gate.py` | 训练屏幕存在性/载体门控（同一结构，换清单） |
| `index_runs.py` | 汇总 `runs/` 为 `reports/run_index.csv` |
| `make_report_figures.py` | 生成诊断图与对比图 |

## 编写约定

1. 脚本须提供 `--help` 说明。
2. 输出统一支持 `--json`，便于其他脚本读取。
3. 失败时返回非零退出码，并输出可定位问题的信息。
4. 不得在脚本中写入样本数据或修改原始图像。
