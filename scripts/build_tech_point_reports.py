#!/usr/bin/env python3
"""按技术点生成《小组成语分工技术点报告》分册（每个技术点一份 DOCX）。"""
from __future__ import annotations

import sys
from pathlib import Path

from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_developer_report import (  # noqa: E402
    HEAD_FONT,
    body,
    bullet,
    heading,
    set_run_font,
    setup_document,
    table,
)

OUT = ROOT / "docs/19-技术点报告"
OUT.mkdir(parents=True, exist_ok=True)

REPORTS = [
    {
        "file": "01-数据采集与防泄漏划分.docx",
        "title": "技术点报告：数据采集与防泄漏划分",
        "members": "张毅卓（主责）、余青阳、全体组员",
        "goal": "建立可追溯、可复核、无跨集合泄漏的数据集与划分，为训练、验证和一次性测试提供统一口径。",
        "implementation": [
            "按“载体 × 内容”建立四格归档：PPT 文字、PPT 公式、纸质文字、纸质公式；采集时同步登记拍摄者、设备、场景、光照、分辨率与时间。",
            "以 doc_page_id 作为分组键，同一张幻灯片或同一页笔记的多角度照片整组进入同一集合，避免同页跨训练/验证/测试。",
            "清洗阶段核对清单与磁盘文件，剔除个人信息、低分辨率、文件缺失、非课堂文档与标签存疑样本；每次修改清单重算 manifest_sha256。",
            "v5 将 v4 测试集并入训练集，从 v4 训练集按 doc_page_id 分层留出 42 张自采样本作为测试，并引入 SmartDoc 2015 的 30 张外部纸质页作为独立测试子集。",
        ],
        "params": [
            ["自采合格样本", "442 张（PPT 与纸质/板书四类）"],
            ["v5 划分", "训练 349 / 验证 51 / 测试 72"],
            ["外部测试", "30 张，只进 test，不参与训练"],
            ["分组键", "doc_page_id；同页多角度整组划分"],
            ["校验", "清单 SHA-256；文件存在性与排除表核对"],
        ],
        "results": [
            ["划分结果", "349 / 51 / 72，合格 472 张", "data/splits/split_v5.json"],
            ["排除表", "36 条不合格记录", "data/manifests/exclusions.csv"],
            ["数据契约", "通过；104 项测试含数据契约", "tests/、reports/stage_audit.md"],
        ],
        "difficulties": [
            "同页多角度照片容易被误当成独立样本：用 doc_page_id 聚合，划分脚本按组切分。",
            "清单与磁盘文件不一致：加入文件存在性校验与排除表，训练/评估启动时校验哈希。",
            "外部测试集与训练帧存在文档级重叠：保留 30 张外部测试并单独披露，不与自采指标混合解读。",
        ],
        "boundary": "v5 测试集仅 72 张，单样本约 1.4 个百分点；外部 30 张全部为纸质文字页，不能代表公式能力。测试集只做一次性评估，不用于调参。",
    },
    {
        "file": "02-四角检测与透视矫正.docx",
        "title": "技术点报告：四角检测与透视矫正",
        "members": "任万东（主责）、余青阳、王康琦",
        "goal": "从斜拍原图中稳定定位文档四边，执行透视变换，输出可用于内容分类的正面图；检测失败时保留原图并显式标记。",
        "implementation": [
            "灰度化、Canny 边缘检测（PPT/纸质均为 50/150）、形态学闭运算连接断裂边缘。",
            "轮廓查找与多边形近似，按面积、凸性与长宽比筛选候选四边形；按顶点顺序做四点透视变换。",
            "检测失败或四边形非法时返回 rectify_failed，分类路径使用原图，避免错误裁切放大误差。",
            "用 338 条人工四角做参数网格搜索，比较 50/150 与 90/250 等组合；90/250 提高检出率但分类指标下降，最终分类回退 50/150。",
        ],
        "params": [
            ["Canny 阈值", "PPT 50/150；纸质 50/150"],
            ["检测备选", "90/250 仅保留检测实验，不用于分类"],
            ["输出长边", "1,600 像素"],
            ["失败策略", "保留原图 + rectify_failed 标记"],
        ],
        "results": [
            ["测试集自动拉正", "61/72", "reports/final_test_v5.md"],
            ["失败回退", "11 张按原图分类", "reports/final_test_v5.md"],
            ["分类增益", "拉正后内容分类优于未拉正", "reports/algorithm_tuning.md"],
        ],
        "difficulties": [
            "幕布边框与背景对比度低、反光导致边缘断裂：形态学闭运算与多阈值组合。",
            "纸张与桌面颜色接近：面积/凸性约束与失败回退，避免强行裁切。",
            "检测参数与分类分布耦合：不以检出率单独选参，最终按下游分类指标回退 50/150。",
        ],
        "boundary": "自动检测并非百分之百成功；11 张失败样本按原图分类，仍计入测试指标。该路径只负责分类视图，显示/PDF 视图由学习四角提供。",
    },
    {
        "file": "03-学习四角与双路径拉正.docx",
        "title": "技术点报告：学习四角与双路径拉正",
        "members": "任万东（主责）、蒋翔恒、余青阳",
        "goal": "在自动检测失败或用户需要更贴合的矫正图时，用学习模型回归文档四角，并将“分类拉正”和“显示拉正”解耦。",
        "implementation": [
            "MobileNetV3-Small 回归 8 个归一化坐标（四个顶点的 x/y），按 PPT 与纸质分别训练 quad-ppt-02 与 quad-paper-01。",
            "训练目标为人工四角的归一化坐标，损失使用 L2；推理后做凸性与面积校验，非法时回退 OpenCV 或原图。",
            "分类路径固定使用 OpenCV 视图，保证指标口径稳定；显示与 PDF 路径使用学习四角，用户可在结果卡切换“学习四角 / OpenCV”。",
            "两条路径共享原图与人工四角；用户手动应用四角后，两条路径同时切换。",
        ],
        "params": [
            ["模型", "MobileNetV3-Small，8 坐标回归"],
            ["PPT 模型", "quad-ppt-02，验证 L2 0.1314"],
            ["纸质模型", "quad-paper-01，验证 L2 0.1347"],
            ["默认策略", "分类 OpenCV；显示/PDF 学习四角"],
        ],
        "results": [
            ["PPT 四角 L2", "0.1314", "reports/quad_localization.md"],
            ["纸质四角 L2", "0.1347", "reports/quad_localization.md"],
            ["全链路验证", "84.31% / 83.81%", "reports/final_test_v5.md"],
        ],
        "difficulties": [
            "学习四角直接替代分类拉正会改变输入分布：只用于显示/PDF，分类仍用 OpenCV。",
            "四角坐标尺度不统一：统一归一化到原图宽高，推理后按原图尺寸还原。",
            "非法四边形会导致透视翻转：推理后做凸性、面积与顶点顺序校验，失败回退。",
        ],
        "boundary": "学习四角不参与分类指标；其价值在于自动检测失败时仍能给出可用矫正图，并支持用户手动微调。",
    },
    {
        "file": "04-去反光增强与扫描件.docx",
        "title": "技术点报告：去反光、增强与扫描件",
        "members": "任万东（主责）、孔泽宇",
        "goal": "抑制投影幕布反光与桌面阴影，提升文字对比度，并提供适合打印/归档的白底黑字扫描件。",
        "implementation": [
            "使用 CLAHE 限制对比度自适应直方图均衡，配合自适应阈值去阴影；增强只用于显示与扫描件，分类输入保持拉正后原图，避免分布漂移。",
            "扫描件模式使用自适应二值化输出白底黑字，支持在网页结果卡与 PDF 中切换。",
            "PDF 支持原图 / 矫正图 / 扫描件三种视图；未校准页在多页导出时会被拦截。",
        ],
        "params": [
            ["增强", "CLAHE + 自适应去阴影"],
            ["扫描件", "自适应二值化，白底黑字"],
            ["PDF 视图", "original / rectified / scan"],
        ],
        "results": [
            ["扫描件可读性", "白底黑字，适合打印", "web/services.py"],
            ["分类口径", "增强不进入分类输入，避免指标漂移", "docs/03 §13"],
            ["网页验收", "扫描件与 PDF 导出通过", "reports/stage_audit.md"],
        ],
        "difficulties": [
            "强反光区域信息已丢失，增强无法真正恢复：以扫描件提升可读性，分类仍依赖原图。",
            "增强会改变分类输入分布：将增强限制在显示/导出路径，不进入分类评估。",
        ],
        "boundary": "增强与扫描件是显示/归档能力，不承诺提升分类准确率；强反光与过曝样本仍可能失败。",
    },
    {
        "file": "05-载体门控.docx",
        "title": "技术点报告：载体门控",
        "members": "余青阳（主责）、蒋翔恒、张艺萧",
        "goal": "在内容分类前判定投影幕布（PPT）与纸质/板书，降低跨载体域差对单一内容模型的干扰。",
        "implementation": [
            "MobileNetV3-Small 二分类，输入 224×224；PPT/幕布为正类，纸质/板书与外部纸质数据为负类。",
            "训练使用自采 PPT/paper 与外部辅助数据；自采验证集不参与训练。",
            "推理启用 TTA 与阈值 0.3；低置信样本标记 uncertain，允许用户手动重试另一分支，不自动跨分支切换。",
        ],
        "params": [
            ["模型", "carrier-gate-v5-01，MobileNetV3-Small"],
            ["阈值", "0.3；TTA 开启"],
            ["输入", "224×224"],
            ["兜底", "uncertain + 手动重试；模型缺失回退 SVM"],
        ],
        "results": [
            ["自采验证", "51/51", "reports/carrier_routing.md"],
            ["外部同源验证", "100%", "reports/carrier_routing.md"],
            ["训练集审计", "336/338（历史口径）", "reports/carrier_routing.md"],
        ],
        "difficulties": [
            "PPT 与纸质在颜色、纹理和拍摄场景上差异大：引入外部纸质数据做负类，但严格限制其只参与训练。",
            "高置信错误无法靠阈值修复：加入 uncertain 标记与手动重试，避免自动切换放大错误。",
        ],
        "boundary": "门控不是内容分类器；其输出只决定进入哪个分支。低置信样本需要人工兜底，自动指标仍按默认分支计算。",
    },
    {
        "file": "06-双分支内容分类.docx",
        "title": "技术点报告：双分支内容分类",
        "members": "蒋翔恒（主责）、王康琦、余青阳",
        "goal": "在载体门控之后，分别用 PPT 专用模型与纸质专用模型判定“纯文字 / 含公式”，并保留传统 SVM 兜底。",
        "implementation": [
            "PPT 分支：MobileNetV3-Small 迁移学习，按幻灯片去重、公式权重 0.5，输出文字/公式二分类。",
            "纸质分支：两个种子的 MobileNetV3-Small 概率平均，缓解小样本波动。",
            "传统基线：版面密度、边缘方向直方图与 HOG 特征 + SVM，作为模型缺失时的兜底与对比。",
            "网页结果卡展示载体、命中分支与两类概率；门控不确定或分支低置信时提示手动重试。",
        ],
        "params": [
            ["PPT 模型", "exp-cnn-ppt-v5；输入 224；公式权重 0.5"],
            ["纸质模型", "paper-cnn-v5-s45 / s47 概率平均"],
            ["传统兜底", "exp-svm-v5，1,836 维特征"],
            ["路由验证", "84.31% / 宏 F1 83.81%"],
        ],
        "results": [
            ["PPT 验证", "95.24% / 92.93%", "reports/final_test_v5.md"],
            ["纸质验证", "76.67%", "reports/final_test_v5.md"],
            ["v5 测试", "93.06% / 92.65%；公式召回 83.33%", "reports/final_test_v5.md"],
        ],
        "difficulties": [
            "公式类样本少且与文字页边界模糊：公式权重、去重与分支专用模型结合，但仍存在公式→文字错误。",
            "跨域测试下降：v4 测试 67.92% 暴露域差；v5 重建测试基准后单独披露，不能与 v4 直接比较。",
        ],
        "boundary": "测试集 72 张中外部 30 张全部为纸质文字页，公式能力主要看自采 42 张与公式召回；合计 93.06% 的 Wilson 下界低于 85%，只能表述为点估计达标。",
    },
    {
        "file": "07-网页交互与批量处理.docx",
        "title": "技术点报告：网页交互与批量处理",
        "members": "余青阳（主责）、李念、孔泽宇",
        "goal": "把模型链路封装为可演示、可标注、可导出的网页应用，支持手机与电脑上传、批量队列、四角校准与 PDF 导出。",
        "implementation": [
            "FastAPI 后端 + 原生前端；默认只监听 127.0.0.1:54312，Server1 通过 SSH 反向隧道和 Nginx 反代对外提供演示。",
            "上传支持拍照、相册/文件选择；电脑端禁用相册入口，无摄像头时禁用拍照。",
            "批量队列横向滑动，逐张展示原图/四角/矫正图/扫描件；支持四角拖拽、点击放大、按载体手动重试与双路径显示切换。",
            "PDF 支持当前单张、区间/离散选中项、全部队列三种导出；未校准页拦截。训练集标注按人分配队列，标注检查页支持退回重标。",
        ],
        "params": [
            ["后端", "FastAPI；uvicorn 54312"],
            ["上传上限", "15 MB/张；批量队列"],
            ["PDF", "单张 / 区间 / 离散 / 全部"],
            ["认证", "Nginx Basic Auth（演示口令公开）"],
        ],
        "results": [
            ["网页测试", "104 项测试含接口契约", "tests/unit/test_web.py"],
            ["健康检查", "routing_ready=true", "/api/health"],
            ["演示", "https://ml-proj.losproeocl.cn", "docs/11"],
        ],
        "difficulties": [
            "大图上传卡死：分析端点改线程池、并发闸门与像素上限；前端 Blob URL 懒加载。",
            "多页 PDF 逐页校准：增加逐页状态与拦截，避免未校准页直接导出。",
            "手机/电脑入口差异：按设备能力动态显示拍照/相册/文件入口。",
        ],
        "boundary": "网页层不改变模型指标；演示服务依赖本机容器与 SSH 隧道，承诺维护至 2027-01-01。",
    },
    {
        "file": "08-评估复现与工程化.docx",
        "title": "技术点报告：评估、复现与工程化",
        "members": "张艺萧（主责）、李念、余青阳",
        "goal": "建立小样本条件下可复核的评估协议，保证数据、模型、指标与提交包可追溯、可复现。",
        "implementation": [
            "5 折分组交叉验证，按 doc_page_id 隔离；每折按载体×内容分层，报告均值±标准差。",
            "测试集一次性评估，报告准确率、宏 F1、混淆矩阵、分载体/分类别指标、bootstrap 置信区间与 McNemar 检验。",
            "Docker 提供 linux/arm64 与 linux/amd64 原生镜像；运行日志、run_index.csv、model_manifest.csv 记录实验与权重。",
            "复现核验使用同一命令复跑，逐样本比对预测与概率；104 项测试覆盖数据契约、划分互斥、哈希校验与网页接口。",
        ],
        "params": [
            ["CV", "5 折分组 × 3 种子（分支/全量）"],
            ["区间", "bootstrap 1,000 次；Wilson 对照"],
            ["检验", "McNemar 精确检验"],
            ["环境", "Docker arm64/amd64；CPU 评估"],
        ],
        "results": [
            ["v5 复现", "72/72 逐样本一致", "reports/repro_check_v5.md"],
            ["测试", "104 项通过", "pytest"],
            ["CV", "SVM 75.02±7.80；MobileNet 77.00±7.91", "reports/cv_oof.md"],
        ],
        "difficulties": [
            "小样本导致单点指标波动：报告均值±标准差、置信区间与配对检验，避免只报单点。",
            "事故后权重恢复：提交包权重为重建版，测试复评 90.28% 与正式 93.06% 的差异单独披露。",
        ],
        "boundary": "“达标”仅指合计点估计；自采子集与公式召回的置信区间下界低于门槛。测试集只用于一次性评估，不据此调参。",
    },
    {
        "file": "09-合成投影与偏度优化.docx",
        "title": "技术点报告：合成投影与偏度优化",
        "members": "蒋翔恒（主责）、张艺萧、余青阳",
        "goal": "在不新增真实样本的条件下，用合成投影 PPT 与偏度压力测试探索泛化提升，并给出是否接入的量化结论。",
        "implementation": [
            "以自采训练集 PPT 人工四角为背景，叠加 4:3 课件页、透视、亮度衰减、反光与噪声，生成 160 组合成训练样本。",
            "模板×类别完全平衡；训练时按背景 doc_page_id 跳过当前 CV 验证组，避免背景场景泄漏。",
            "门控 TTA + 阈值 0.3 用于偏度压力测试；合成 v2/v3 做 5 折×3 种子 CV，并在测试集做固定阈值复验。",
        ],
        "params": [
            ["合成 v2", "57 个背景，160 组；CV 78.25%±7.92"],
            ["合成 v3", "19 个 4:3 背景，160 组；CV 76.50%±6.85"],
            ["偏度", "门控 TTA + 阈值 0.3；30°/40° 71.4%→81.0%"],
        ],
        "results": [
            ["v2/v3 CV", "均高于基线 70.44%", "reports/synth_ppt_training.md"],
            ["测试复验", "v2/v3 PPT 45.83% < 冻结 62.50%", "reports/synth_ppt_test.md"],
            ["结论", "不接入网页与最终链路", "docs/17"],
        ],
        "difficulties": [
            "合成背景与训练集共享教室/课程场景，CV 偏乐观；测试集域差更大，增益未迁移。",
            "严格 4:3 过滤后背景只剩 19 个，重复度高；v3 定位更准但折均值低于 v2。",
        ],
        "boundary": "合成数据保留为负结果与技术积累，未进入最终模型；后续应优先补充真实跨教室/跨课程样本，并按完整场次隔离验证。",
    },
]


def build(report: dict) -> None:
    doc = setup_document()
    title = doc.add_paragraph()
    title.alignment = 1  # center
    run = title.add_run(report["title"])
    set_run_font(run, size=18, bold=True, east=HEAD_FONT)
    body(doc, "武汉理工大学《机器学习》课程工程实践 · 第六组 · Task 06", indent=False, size=10.5)
    body(doc, f"参与成员：{report['members']}", indent=False, size=10.5)
    body(doc, "版本 v1.0 · 2026-11-28", indent=False, size=10.5)

    heading(doc, "1  技术点定义与目标", 1)
    body(doc, report["goal"])

    heading(doc, "2  参与成员与分工", 1)
    body(doc, f"本技术点由 {report['members']} 共同完成；具体任务边界与贡献点数见《小组成员及其分工》。")

    heading(doc, "3  实现方案", 1)
    for item in report["implementation"]:
        bullet(doc, item)

    heading(doc, "4  关键参数与做法", 1)
    table(
        doc,
        ["项目", "做法 / 取值"],
        report["params"],
        "表 1  关键参数与做法",
        widths=[4.0, 11.0],
        font_size=9.6,
        align_center=False,
    )

    heading(doc, "5  实验结果与证据", 1)
    table(
        doc,
        ["指标 / 产物", "结果", "证据"],
        report["results"],
        "表 2  实验结果与证据",
        widths=[4.2, 6.2, 5.0],
        font_size=9.2,
        align_center=False,
    )

    heading(doc, "6  难点与解决方案", 1)
    for item in report["difficulties"]:
        bullet(doc, item)

    heading(doc, "7  结论与边界", 1)
    body(doc, report["boundary"])

    path = OUT / report["file"]
    doc.save(path)
    print("saved", path)


def main() -> int:
    for report in REPORTS:
        build(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
