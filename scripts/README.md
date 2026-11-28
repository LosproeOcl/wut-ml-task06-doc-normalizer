# 脚本目录说明

本目录存放一次性脚本与运维工具。可复用的业务逻辑应放入 `src/`，不得在此重复实现。

## 计划脚本

| 脚本 | 用途 | 阶段 |
|---|---|---|
| `env_smoke.py` | 检查 Python、依赖版本与运行设备 | M0 |
| `rebuild_split.py` | 基于既有冻结划分重建新版本，不改变分组归属 | M1 |
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
| `check_manifest.py` | 只读校验清单字段、唯一性、分组与类别分布；支持 `--json` |
| `check_dataset.py` | 只读核对清单与磁盘文件一致性；未登记文件只报警告 |
| `reconcile_manifest_paths.py` | 按磁盘实际位置修正清单 file/label；默认预演，`--apply` 写回 |
| `group_inbox_slides.py` | 按同一幻灯片聚合 2026-11-27 inbox 样本，选清晰度代表并更新 split_v4 |
| `assign_inbox_corners.py` | 把新增实拍样本的四角任务按公式/文字分层平均分配给指定成员，默认 PT-INBOX 前缀与三人名单 |
| `ingest_inbox_batch.py` | 把 inbox 新批次按映射表归档、登记清单、更新幻灯片分组与 train 划分、重算清单哈希 |
| `tune_rectify_detector.py` | 用人工四角按 `doc_page_id` 分组调优 OpenCV 检测器的 Canny/面积参数 |
| `eval_quad_routing.py` | 比较 OpenCV、学习四角兜底、学习四角优先三种拉正策略的端到端分类准确率 |
| `build_developer_report.py` | 生成论文格式的开发者视角开发历程 DOCX |
| `make_developer_report_assets.py` | 生成报告所需的数据样本、架构、指标与混淆矩阵图 |
| `train_ppt_quad.py` | 用训练集人工四角标签训练分载体四角回归器（`--carrier ppt/paper`），按 doc_page_id 分组切分 |
| `eval_ppt_quad.py` | 在同一载体验证组上对比学习四角与 OpenCV 检测的归一化误差 |
| `eval_spatial_skew.py` | 对现有 PPT 验证页做合成透视，评估内容模型/完整链路/门控阈值 TTA |
| `eval_gate_skew.py` | 载体门控在合成偏度下的阈值、TTA 与 AUC 评估 |
| `make_skew_figures.py` | 生成空间偏度三张评估图 |

## 2026-11-28 新增脚本

| 脚本 | 用途 |
|---|---|
| `build_synth_ppt_pages.py` | 生成“SCB 教室背景 + 课程课件 + 投影退化”的合成 PPT 示例；输出 1280×960 成对图、manifest 与画廊，图像不入库 |

`check_manifest.py` 与 `check_dataset.py` 基于 PR #1 的校验思路、按当前数据契约重写；贡献记录见 `CONTRIBUTORS.md`。

## 编写约定

1. 脚本须提供 `--help` 说明。
2. 输出统一支持 `--json`，便于其他脚本读取。
3. 失败时返回非零退出码，并输出可定位问题的信息。
4. 不得在脚本中写入样本数据或修改原始图像。
