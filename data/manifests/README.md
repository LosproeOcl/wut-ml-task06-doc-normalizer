# 样本清单说明

样本清单文件为 `sample_manifest.csv`，是样本元数据的唯一可信来源。清单本身纳入版本控制，对应的图像文件不纳入版本控制。

## 字段定义

| 字段 | 类型 | 必填 | 取值与说明 |
|---|---|---|---|
| `sample_id` | 字符串 | 是 | 全局唯一，取文件名去掉扩展名；同名不同扩展名的两张独立照片，后登记者加 `_jpg` 等扩展名后缀消歧（如 `IMG_6110_jpg`），并在 notes 注明 |
| `file` | 字符串 | 是 | 相对于 `data/raw_samples/` 的路径 |
| `label` | 枚举 | 是 | 归档标签 `ppt_text`、`ppt_formula`、`paper_text`、`paper_formula`；评估时按配置映射为内容二分类 `text`、`formula` |
| `doc_page_id` | 字符串 | 是 | 文档页分组键。同一文档页的多角度拍摄必须填写相同值 |
| `shooter` | 字符串 | 是 | 拍摄者姓名缩写，与留证照片命名一致 |
| `device` | 字符串 | 是 | 手机型号；无元信息的转发/导出图填 `unknown` |
| `scene` | 枚举 | 是 | `classroom`、`corridor`、`dorm`、`outdoor` |
| `angle_deg` | 整数 | 是 | 估计倾斜角，0 至 90 |
| `lighting` | 枚举 | 是 | `natural`、`ceiling`、`side_lamp`、`backlight` |
| `resolution` | 字符串 | 是 | 宽乘高，单位像素，例如 `4032x3024` |
| `shot_at` | 日期 | 是 | 格式为 `YYYY-MM-DD` |
| `notes` | 字符串 | 否 | 反光、遮挡或存疑说明 |
| `privacy_masked` | 布尔 | 是 | 历史字段。记录是否曾生成打码发布副本；按 D-01，副本已停用，不得引用 |
| `privacy_regions` | 整数 | 是 | 打码区域数量，无打码时填 0 |
| `release_file` | 字符串 | 否 | 发布副本路径，无副本时为空；按 D-01 不得引用 |

## 示例行

```csv
T06_P03_pptFormula_classroom_017,02_ppt_formula/T06_P03_pptFormula_classroom_017.jpg,ppt_formula,PPT-CALC-03,yqy,iPhone 14,classroom,35,ceiling,4032x3024,2026-11-27,幕布右侧高光,true,1,release/02_ppt_formula/T06_P03_pptFormula_classroom_017.jpg
```

## 登记规则

1. 每张样本一行，不得合并。
2. `sample_id` 与 `file` 必须与实际文件一致。
3. 同一文档页的样本共享 `doc_page_id`。该字段是防止数据泄漏的关键，填写错误将直接导致指标失真。
4. 补充采集的样本追加至文件末尾，不修改既有行。
5. 确需修改既有行时，在提交说明中注明原因。

## 排除表

`exclusions.csv` 记录不进入训练、评估与对外材料的样本，机器可读，字段为 `sample_id,reason`。`reason` 取值如下。

| 取值 | 含义 |
|---|---|
| `personal_info` | 含姓名、证件号、账号、人脸等个人信息 |
| `unlabeled` | 内容存疑，无法判定类别 |
| `low_resolution` | 短边低于 720 像素 |
| `missing_file` | 清单已登记但文件缺失 |

排除表当前 32 行。数据加载、划分与评估必须以该表为准，不得仅凭清单判断样本可用性。

## 检查方式

数据层已实现清单与划分校验，入口为 `src/docnorm/data/`。检查内容如下。

1. 必填字段是否为空。
2. 枚举字段取值是否合法。
3. `sample_id` 是否唯一。
4. `file` 指向的文件是否存在，由 `find_missing_files` 实现。
5. 同一 `doc_page_id` 的样本是否全部属于同一类别。
6. 类别分布是否满足配额要求。
7. 排除表是否引用未知样本。

划分重建使用 `scripts/rebuild_split.py`，测试见 `tests/unit` 与 `tests/integration`。
