# 配置目录说明

本目录存放实验配置。配置采用 YAML 格式，按数据、矫正、增强、分类、隐私与运行时六段组织。

## 约定

1. 所有实验差异只通过配置表达，不通过修改代码分支实现。
2. 每次运行须将实际生效配置复制为 `runs/<实验编号>/config.snapshot.yaml`。
3. 配置字段新增或重命名须同步更新 `docs/03-架构设计.md` 第 7.3 节。
4. 配置项不得包含绝对路径与个人路径。

## 字段说明

| 字段 | 含义 |
|---|---|
| `data.manifest` | 样本清单路径 |
| `data.split` | 划分文件路径 |
| `data.raw_dir` | 原始样本根目录 |
| `data.image_size` | 输入图像长边像素数 |
| `rectify.min_area_ratio` | 四边形面积占画面比例下限（置信门槛） |
| `rectify.max_area_ratio` | 四边形面积占画面比例上限 |
| `enhance.enabled` | 是否启用增强 |
| `enhance.method` | 增强方法 |
| `enhance.clahe_clip` | 直方图均衡对比度限值 |
| `enhance.correct_shadows` | 是否执行光照校正 |
| `enhance.shadow_kernel` | 背景估计核大小 |
| `enhance.shadow_strength` | 光照校正混合强度 |
| `classify.model` | 分类模型，取值为 `classic_svm`、`classic_rf` 或 `cnn` |
| `classify.label_map` | 归档标签到评估标签的映射，当前为内容二分类（ADR-0008） |
| `classify.class_weight` | 内容类别类权重策略，默认 `balanced` |
| `classify.backbone` | 深度模型骨干名称 |
| `classify.input_size` | 深度模型输入尺寸 |
| `classify.low_conf_threshold` | 低置信度阈值 |
| `privacy.enabled` | 历史配置，D-01 后固定为 `false` |
| `privacy.face_detector` | 人脸检测器，取值为 `yunet` 或 `haar` |
| `privacy.qr_detector` | 二维码检测器，取值为 `opencv`，备选 `zxing` |
| `privacy.yunet_model` | YuNet 模型路径 |
| `privacy.detect_faces` | 是否检测人脸候选 |
| `privacy.detect_qr` | 是否检测二维码候选 |
| `privacy.method` | 打码方式，取值为 `fill` 或 `pixelate` |
| `privacy.expand_ratio` | 打码区域外扩比例 |
| `privacy.strip_exif` | 是否去除图像元数据 |
| `privacy.require_manual_review` | 是否强制人工复核 |
| `privacy.max_document_coverage` | 打码覆盖文档主体的最大比例 |
| `web.host` | 网页监听地址，默认 `127.0.0.1` |
| `web.port` | 网页端口，默认 54312 |
| `web.max_upload_mb` | 单文件上传体积上限 |
| `web.result_ttl_seconds` | 临时结果保留时长 |
| `web.max_concurrency` | 同时处理的请求数 |
| `web.static_dir` | 静态文件目录 |
| `runtime.seed` | 随机种子 |
| `runtime.device` | 运行设备，正式评估固定为 `cpu` |
| `runtime.num_threads` | 计算线程数，正式评估固定为 1 |
| `runtime.num_workers` | 数据加载进程数，评估阶段固定为 0 |

`configs/default.yaml` 为当前版本（v5）配置。`configs/legacy/v4.yaml` 保留 v4 的 `data.manifest` 与 `data.split`，用于历史复现；不得把 v4 配置用于 v5 评估。

当前 `data.manifest` 为 `data/manifests/sample_manifest_v5.csv`，`data.split` 为 `data/splits/split_v5.json`。v5 清单包含 30 张外部测试样本，只进 test，不参与训练与验证；详见 `docs/13-外部数据使用说明.md`。
