# 配置目录说明

本目录存放实验配置。配置采用 YAML 格式，按数据、矫正、增强与分类四段组织。

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
| `data.image_size` | 输入图像长边像素数 |
| `rectify.min_area_ratio` | 四边形面积占画面比例下限 |
| `rectify.max_area_ratio` | 四边形面积占画面比例上限 |
| `enhance.enabled` | 是否启用增强 |
| `enhance.method` | 增强方法 |
| `enhance.clahe_clip` | 直方图均衡对比度限值 |
| `classify.model` | 分类模型，取值为 `classic_svm`、`classic_rf` 或 `cnn` |
| `classify.backbone` | 深度模型骨干名称 |
| `classify.input_size` | 深度模型输入尺寸 |
| `classify.low_conf_threshold` | 低置信度阈值 |
| `runtime.seed` | 随机种子 |
| `runtime.device` | 运行设备，正式评估固定为 `cpu` |

`configs/default.yaml` 为基线配置示例。其他实验在此基础上覆盖差异项。
