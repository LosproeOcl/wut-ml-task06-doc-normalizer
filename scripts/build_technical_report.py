#!/usr/bin/env python3
"""生成《技术点报告》DOCX（项目技术路线、关键算法/模块、参数与证据链）。"""
from __future__ import annotations

import sys
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH
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

OUTPUT = ROOT / "docs/19-技术点报告.docx"


def cover(doc) -> None:
    for _ in range(4):
        doc.add_paragraph()
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("斜拍课堂文档自动拉正、去反光与内容归类系统")
    set_run_font(run, size=22, bold=True, east=HEAD_FONT)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("技术点报告")
    set_run_font(run, size=18, bold=True, east=HEAD_FONT)
    for _ in range(4):
        doc.add_paragraph()
    for text, size in [
        ("武汉理工大学《机器学习》课程工程实践", 14),
        ("第六组 · Task 06", 12),
        ("版本 v1.0 · 2026-11-28", 11),
    ]:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(text)
        set_run_font(run, size=size)
    doc.add_page_break()


def main() -> int:
    doc = setup_document()
    cover(doc)

    heading(doc, "1  技术路线总览", 1)
    body(
        doc,
        "系统面向斜拍的课堂投影幕布、黑板板书与纸质笔记照片，完成三项处理：定位文档四边并做透视矫正，"
        "抑制反光并输出扫描件，判定页面内容为纯文字或含公式。整体链路按“先跑通、再拆解、再替换、"
        "最后解耦”的顺序迭代，最终形成“载体门控 + 双分支内容分类 + 双路径拉正”的结构。"
    )
    body(
        doc,
        "输入图像先经过质量与载体判定：门控模型给出投影幕布（PPT）或纸质/板书的概率；分类路径使用 "
        "OpenCV 四角检测与透视变换，显示/PDF 路径使用学习四角回归；两条路径共享原图与人工四角，"
        "用户手动应用四角后同时切换。内容分类按载体进入 PPT CNN 或纸质 CNN 集成，模型缺失时回退 "
        "SVM；输出包括正面矫正图、扫描件、载体/分支概率与内容标签。"
    )
    table(
        doc,
        ["模块", "输入", "输出", "主要技术"],
        [
            ["载体门控", "原图", "PPT / 纸质概率", "MobileNetV3-Small 二分类 + TTA"],
            ["分类拉正", "原图", "矫正图、四角", "OpenCV Canny + 轮廓 + 四点透视"],
            ["显示/PDF 拉正", "原图", "学习四角、矫正图", "MobileNetV3-Small 8 坐标回归"],
            ["内容分类", "矫正图", "文字 / 公式", "MobileNetV3-Small、CNN 集成、SVM 兜底"],
            ["扫描件", "矫正图", "白底黑字图", "自适应二值化"],
            ["网页交互", "上传图/队列", "分析结果、PDF", "FastAPI + 原生前端"],
        ],
        "表 1  系统模块与技术路线",
        widths=[2.6, 3.0, 3.6, 6.2],
        font_size=9.6,
        align_center=False,
    )

    heading(doc, "2  关键技术点", 1)
    table(
        doc,
        ["编号", "技术点", "实现要点", "证据"],
        [
            [
                "T1",
                "数据构建与防泄漏划分",
                "以 doc_page_id 为分组键，同一页多角度照片整组进入同一集合；v5 训练 349 / 验证 51 / 测试 72"
                "（自采 442 + 外部测试 30）；清单 SHA-256 校验；5 折分组 CV。",
                "data/splits/split_v5.json、docs/04、reports/final_test_v5.md",
            ],
            [
                "T2",
                "OpenCV 四角检测与透视矫正",
                "Canny 50/150、轮廓与四边形拟合、四点透视；失败回退原图；测试 72 张中 61 张自动拉正，"
                "11 张失败回退。",
                "src/docnorm/rectify/、reports/rectify_detection.md",
            ],
            [
                "T3",
                "学习四角回归与双路径拉正",
                "MobileNetV3-Small 回归 8 个归一化坐标；PPT/纸分别训练 quad-ppt-02 / quad-paper-01，"
                "L2 0.1314 / 0.1347；用于显示与 PDF，分类仍用 OpenCV 视图。",
                "src/docnorm/rectify/quad.py、reports/quad_localization.md、ADR-0015",
            ],
            [
                "T4",
                "去反光、增强与扫描件",
                "CLAHE 与自适应阈值；网页“扫描件”模式输出白底黑字；PDF 支持原图/矫正/扫描三种视图。",
                "web/services.py、docs/03 §13",
            ],
            [
                "T5",
                "载体门控",
                "carrier-gate-v5-01，MobileNetV3-Small 二分类；gate_threshold=0.3、TTA；自采验证 51/51，"
                "外部同源验证 100%。",
                "runs/carrier-gate-v5-01、reports/carrier_routing.md",
            ],
            [
                "T6",
                "双分支内容分类",
                "PPT CNN exp-cnn-ppt-v5（验证 95.24% / F1 92.93%）；纸质 CNN s45/s47 集成（76.67%）；"
                "SVM 72.55% 兜底；路由验证 84.31%，测试 93.06%。",
                "reports/final_test_v5.md、reports/web_integration.md",
            ],
            [
                "T7",
                "网页交互与批量处理",
                "FastAPI + 原生前端；三入口上传、横向批量队列、四角拖拽、双路径显示切换、单张/区间/离散/全部"
                " PDF 导出；训练集标注按人分配队列，标注检查页支持退回重标。",
                "web/、docs/11、docs/01 FR-24/FR-29",
            ],
            [
                "T8",
                "评估、复现与工程化",
                "5 折分组 CV、bootstrap 置信区间、McNemar 检验；104 项测试；Docker arm64/amd64；"
                "v5 逐样本复现 72/72 一致。",
                "reports/cv_oof.md、reports/repro_check_v5.md、tests/",
            ],
            [
                "T9",
                "合成投影与偏度优化（探索）",
                "合成 160 组投影 PPT 课件；v2 CV 78.25%±7.92、v3 76.50%±6.85；但测试复验 PPT 45.83%"
                "低于冻结链路 62.50%，未接入。",
                "docs/17、reports/synth_ppt_test.md",
            ],
        ],
        "表 2  技术点清单与证据",
        widths=[1.2, 3.4, 7.4, 3.4],
        font_size=8.8,
        align_center=False,
    )

    heading(doc, "2.1  数据构建与防泄漏", 2)
    body(
        doc,
        "数据以“同一文档页只进入一个集合”为第一原则。清单用 doc_page_id 标记同一张幻灯片或同一页笔记的"
        "多角度照片，划分脚本按分组键切分；每次修改清单都重算 manifest_sha256，训练与评估启动时校验。"
        "v5 将 v4 测试集并入训练集，从 v4 训练集按 doc_page_id 分层留出 42 张自采样本，另引入 SmartDoc "
        "2015 的 30 张外部纸质页作为独立测试子集；外部 30 张只进 test，不参与训练。"
    )
    body(
        doc,
        "评估采用 5 折分组交叉验证，折内训练/验证按 doc_page_id 隔离；测试集只在模型与配置冻结后运行一次，"
        "不用于阈值选择或早停。该流程是后续所有指标可信的前提。"
    )

    heading(doc, "2.2  四角检测、学习四角与双路径", 2)
    body(
        doc,
        "分类路径使用 OpenCV：灰度化、Canny（PPT/纸质均为 50/150）、形态学闭运算、轮廓查找与四边形近似，"
        "按面积与凸性筛选后做四点透视变换；失败时保留原图并标记 rectify_failed，避免把错误裁切送入分类器。"
        "测试集 72 张中 61 张自动拉正成功，11 张回退原图，分类仍能完成。"
    )
    body(
        doc,
        "显示与 PDF 路径使用学习四角：MobileNetV3-Small 回归 8 个归一化坐标，按载体分别训练。该路径用于"
        "解决“自动检测失败时如何给出可用矫正图”的交互问题，分类仍由 OpenCV 视图决定；两条路径共享原图"
        "与人工四角，用户手动应用四角后同时切换。该解耦是后期最重要的架构调整之一。"
    )

    heading(doc, "2.3  载体门控与双分支分类", 2)
    body(
        doc,
        "单一内容模型难以同时处理投影幕布与纸质/板书：幕布存在反光、摩尔纹与透视，纸质存在桌面背景、"
        "阴影与纸张纹理。系统先做载体二分类，再按载体进入专用分支；门控不确定时标记 uncertain，"
        "允许用户手动重试另一分支，不自动跨分支切换，避免把高置信错误放大。"
    )
    body(
        doc,
        "PPT 分支使用去重后的幻灯片样本与公式权重 0.5，验证集 95.24% / 宏 F1 92.93%；纸质分支使用两个"
        "种子的 CNN 概率平均，验证集 76.67%；SVM 作为模型缺失时的兜底。v5 路由验证 84.31% / 83.81%，"
        "测试集一次性评估 93.06% / 92.65%，其中自采 42 张 88.10%、外部 30 张 100%、公式召回 83.33%。"
    )

    heading(doc, "2.4  扫描件、网页与批量交互", 2)
    body(
        doc,
        "网页层使用 FastAPI + 原生前端，默认只监听 127.0.0.1:54312。上传支持拍照、相册/文件选择；"
        "批量队列可横向滑动、逐张查看原图/四角/矫正图/扫描件，支持四角拖拽与点击放大；PDF 支持当前单张、"
        "区间/离散选中项与全部队列三种导出方式，未校准页会被拦截。扫描件模式使用自适应二值化输出白底黑字，"
        "适合打印与归档。"
    )
    body(
        doc,
        "训练集标注按成员分配队列，标签与四角写入独立文件，训练时合并，不修改冻结清单与划分；"
        "“标注检查”页汇总全组四角记录，可逐条退回重标并保留原因。"
    )

    heading(doc, "3  关键指标与证据链", 1)
    table(
        doc,
        ["指标", "数值", "口径 / 证据"],
        [
            ["v5 测试集总体", "93.06% / 宏 F1 92.65%", "72 张（自采 42 + 外部 30），reports/final_test_v5.md"],
            ["v5 测试集自采子集", "88.10%", "42 张；公式召回 83.33%"],
            ["v5 验证集路由", "84.31% / 83.81%", "51 张；PPT 95.24%，纸质 76.67%"],
            ["5 折分组 CV", "SVM 75.02%±7.80；MobileNet 77.00%±7.91；PPT 73.73%±12.42；纸质 85.00%±9.23", "reports/cv_oof.md、data/splits/cv_v5/"],
            ["自动拉正", "61/72", "11 张失败回退原图"],
            ["复现核验", "72/72 逐样本一致", "reports/repro_check_v5.md"],
            ["测试", "104 项通过", "pytest；Docker arm64"],
        ],
        "表 3  关键指标与证据链",
        widths=[3.4, 6.4, 5.6],
        font_size=9.2,
        align_center=False,
    )
    body(
        doc,
        "口径说明：合计 93.06% 的 Wilson 95% 置信区间为 84.8%–97.0%，下界低于 85%；自采子集与公式召回的"
        "区间下界也低于各自门槛。因此“达到 85%”仅指合计点估计，不能表述为稳健达标；外部 30 张全部为"
        "文字类纸质页，不代表公式能力。"
    )

    heading(doc, "4  工程化与复现", 1)
    body(
        doc,
        "代码按数据层、矫正、增强、分类、训练/评估与网页层拆分；配置集中在 configs/，运行记录写入 "
        "reports/run_index.csv 与 runs/*/run.json；模型清单与 SHA-256 见 reports/model_manifest.csv。"
        "容器提供 linux/arm64 与 linux/amd64 两个原生镜像，正式评估统一在 CPU 上执行。"
    )
    bullet(doc, "测试：docker run … python -m pytest -q，104 项通过。")
    bullet(doc, "复现：reports/repro_check_v5.md 记录同一命令复跑，72/72 逐样本预测与概率一致。")
    bullet(doc, "数据：自采 442 张以加密包发布在 GitHub Release（dataset-self-v5），外部数据来源与许可见 docs/13。")
    bullet(doc, "网页：演示入口 https://ml-proj.losproeocl.cn，用户名 t06，口令 admin（公开演示口令）。")

    heading(doc, "5  技术边界与未采用方案", 1)
    table(
        doc,
        ["方案", "结果", "处理"],
        [
            ["外部预训练零样本", "340 张真实数据 54.41%，等于全判 text", "不直接部署；仅作初始化/辅助训练"],
            ["合成投影 PPT v2/v3", "CV 有提升，但测试 PPT 45.83% < 冻结 62.50%", "保留为负结果，不接入网页"],
            ["自动隐私打码", "本组自设扩展，非课程要求", "按 D-01 取消开发；数据清洗已完成"],
            ["GitHub Pages", "静态托管无法运行 FastAPI/模型", "取消，完整 webapp 走本机 + Server1 反代"],
            ["测试集调阈值", "测试集仅用于一次性评估", "禁止据此调参；阈值只看验证/OOF"],
        ],
        "表 4  技术边界与未采用方案",
        widths=[3.6, 6.0, 5.8],
        font_size=9.2,
        align_center=False,
    )

    heading(doc, "6  结论", 1)
    body(
        doc,
        "本项目的技术核心是分层解耦：载体门控降低跨域干扰，双分支分类吸收两类载体的差异，"
        "双路径拉正把分类精度与显示效果解耦，网页层把模型能力转化为可演示、可标注、可导出的完整流程。"
    )
    body(
        doc,
        "当前版本的强项是工程完整性与可复现性：数据划分、清单哈希、5 折 CV、一次性测试、逐样本复现与 "
        "104 项测试形成闭环；弱项是公式召回与自采子集的置信区间下界仍低于门槛，外部测试仅覆盖纸质文字页。"
        "后续若要继续提升，应优先补充真实斜拍公式样本与跨教室/跨课程场次，避免在测试集上反复调参。"
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print("saved", OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
