# 标注目录说明

本目录预留标注文件，当前无必须标注项。

## 当前口径

按 ADR-0009，本项目不设离线人工四角标注，也不要求像素级多边形标注。分类监督使用 `data/manifests/sample_manifest.csv` 中的图像级类别。

训练集标签校正写入 `manual_labels.csv`，字段为 `sample_id,label,annotator,updated_at`，只允许训练集样本。训练脚本读取该文件覆盖训练标签，验证与测试保持清单原值，见 ADR-0011。

训练集四角覆盖写入 `manual_corners.csv`，字段为 `sample_id,points,annotator,updated_at`，`points` 为四个顶点 JSON 数组。只允许训练集样本，训练拉正时仅在自动检测失败后回退使用，见 ADR-0012 与 ADR-0015；该文件不作为评估金标准。原始 236 条已完成；2026-11-27 两批新增 102 张完成后，训练集 338 条四角已全部完成，结构校验通过。

训练集标注任务分配写入 `assignees.csv`，字段为 `sample_id,assignee,label,doc_page_id`，由 `scripts/assign_annotations.py` 生成。前端按标注人筛选队列，服务端拒绝非本人写入，见 ADR-0013。原始 236 张按总计数均分给 8 人，当前为 5 人 30 张、3 人 29 张。

2026-11-27 新增首批 93 张实拍 PPT 样本，由 `scripts/assign_inbox_corners.py` 只把未分配、未标注的 PT-INBOX 样本按公式/文字分层平均分配：任万东、王康琦、余青阳各 31 张（公式 12 + 文字 19）。三人累计各 61 张，其余成员保持原分配。

2026-11-27 17:05 又新增第二批 9 张实拍 PPT 文字页（2 张幻灯片的多角度照片），登记为 `PT-INBOX-G49`（5 张）与 `PT-INBOX-G15`（4 张，Anchor Box 同页合并），只加入 train，四角标注全部由余青阳完成；分配后余青阳累计 70 张。

标注检查退回写入 `redo_corners.csv`，字段为 `sample_id,assignee,previous_points,reason,requested_at,status`。退回时从 `manual_corners.csv` 删除该样本并把原坐标留在审计文件中，样本重新进入该成员待标注队列；成员重新保存四角后该行被清除，见 ADR-0014。该文件不参与训练。

## 可选文件

若后续需要记录模型参考角点，可建立 `corners_reference.json`，并明确标注来源为模型预测，不得称为人工真值。

```json
{
  "T06_P01_pptText_classroom_001": {
    "points": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],
    "source": "docaligner",
    "checked": false
  }
}
```

坐标顺序为左上、右上、右下、左下，单位为原图像素。该文件不参与训练，也不作为本项目评估的金标准。

## 禁止内容

1. 不得将检测器自身输出保存为“标注”。
2. 不得把模型参考值写成人工标注。
3. 不得在标注文件中保存含个人信息的图像路径之外的内容。
