"""生成《小组成员及其分工》DOCX（含贡献量化，计数制口径）。

数据来源（均为仓库内可复核文件）：
- data/manifests/sample_manifest_v5.csv + exclusions.csv（采集数量）
- data/annotations/manual_corners.csv（四角标注数量）
- data/annotations/manual_labels.csv（标签复核数量）
- reports/run_index.csv（实验运行数量）
- git 提交记录（提交次数）
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get("MEMBER_REPORT_OUT", ROOT / "docs/18-小组成员及其分工.docx"))
STUDENT_ID_FILE = os.environ.get("STUDENT_ID_FILE")
STUDENT_IDS = json.loads(Path(STUDENT_ID_FILE).read_text(encoding="utf-8")) if STUDENT_ID_FILE else {}
BODY_FONT = "宋体"
HEAD_FONT = "黑体"
LATIN_FONT = "Times New Roman"

MEMBERS = [
    ("余青阳", "LosproeOcl", "项目负责人 · 架构与算法主责 · 数据与标注 · 部署与交付"),
    ("张毅卓", "qingwu0731", "数据负责人 · 清单与划分 · 排除表复核 · 外部 PR 贡献者"),
    ("任万东", "RenWandong", "矫正与增强 · 检测调参 · 学习四角"),
    ("王康琦", "qywkq", "传统机器学习 · 特征工程与传统基线"),
    ("蒋翔恒", "Jiang-Xiangheng", "轻量深度学习 · MobileNetV3 迁移学习与训练"),
    ("张艺萧", "zhangyixiao123", "评估 · 指标实现 · 交叉验证与统计检验"),
    ("孔泽宇", "jsindkdneksn", "可视化与报告 · 图表组 · 报告排版"),
    ("李念", "hanss0090", "工程与复现 · 容器 · 持续集成 · 复现核验"),
]


def set_run_font(run, size=12, bold=False, east=BODY_FONT, latin=LATIN_FONT, color=None):
    run.font.name = latin
    run.font.size = Pt(size)
    run.bold = bold
    if run._element.rPr is None:
        run._element.get_or_add_rPr()
    fonts = run._element.rPr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        run._element.rPr.append(fonts)
    fonts.set(qn("w:eastAsia"), east)
    fonts.set(qn("w:ascii"), latin)
    fonts.set(qn("w:hAnzi") if False else qn("w:hAnsi"), latin)
    if color:
        run.font.color.rgb = RGBColor(*color)


def heading(doc, text, level=1):
    sizes = {1: 15, 2: 13, 3: 12}
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(10 if level == 1 else 6)
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(text)
    set_run_font(run, size=sizes.get(level, 12), bold=True, east=HEAD_FONT)


def body(doc, text, *, indent=True, size=12, bold=False):
    paragraph = doc.add_paragraph()
    if indent:
        paragraph.paragraph_format.first_line_indent = Pt(size * 2)
    paragraph.paragraph_format.line_spacing = 1.3
    paragraph.paragraph_format.space_after = Pt(2)
    run = paragraph.add_run(text)
    set_run_font(run, size=size, bold=bold)


def bullet(doc, text, size=11.5):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Pt(18)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.25
    paragraph.paragraph_format.space_after = Pt(1)
    run = paragraph.add_run("• " + text)
    set_run_font(run, size=size)


def caption(doc, text, kind="表"):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    run = paragraph.add_run(text)
    set_run_font(run, size=10.5, bold=True)


def _three_line_borders(table_obj):
    tbl_pr = table_obj._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for tag, val, size in (
        ("top", "single", "12"),
        ("bottom", "single", "12"),
        ("left", "none", "0"),
        ("right", "none", "0"),
        ("insideH", "none", "0"),
        ("insideV", "none", "0"),
    ):
        element = OxmlElement(f"w:{tag}")
        element.set(qn("w:val"), val)
        if val == "single":
            element.set(qn("w:sz"), size)
            element.set(qn("w:space"), "0")
            element.set(qn("w:color"), "000000")
        borders.append(element)
    tbl_pr.append(borders)


def _header_bottom_border(cell):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "0")
    bottom.set(qn("w:color"), "000000")
    borders.append(bottom)
    tc_pr.append(borders)


def table(doc, headers, rows, cap, widths=None, font_size=10.5, align_center=True):
    caption(doc, cap)
    table_obj = doc.add_table(rows=1, cols=len(headers))
    _three_line_borders(table_obj)
    table_obj.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, text in enumerate(headers):
        cell = table_obj.rows[0].cells[index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Pt(0)
        run = paragraph.add_run(str(text))
        set_run_font(run, size=font_size, bold=True)
        _header_bottom_border(cell)
    for row in rows:
        cells = table_obj.add_row().cells
        for index, text in enumerate(row):
            cells[index].text = ""
            paragraph = cells[index].paragraphs[0]
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER if align_center and index > 0 else WD_ALIGN_PARAGRAPH.LEFT
            )
            paragraph.paragraph_format.first_line_indent = Pt(0)
            run = paragraph.add_run(str(text))
            set_run_font(run, size=font_size)
    if widths:
        for row in table_obj.rows:
            for index, width in enumerate(widths):
                row.cells[index].width = Cm(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def _read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def collect_stats() -> dict:
    excluded = {r["sample_id"] for r in _read_rows(ROOT / "data/manifests/exclusions.csv")}
    manifest = [
        r
        for r in _read_rows(ROOT / "data/manifests/sample_manifest_v5.csv")
        if r["sample_id"] not in excluded and r["shooter"] != "external"
    ]
    collect = Counter(r["shooter"] for r in manifest)
    carrier = Counter(
        (r["shooter"], r["label"].split("_")[0]) for r in manifest
    )
    corners = Counter(
        r["annotator"] for r in _read_rows(ROOT / "data/annotations/manual_corners.csv")
    )
    labels = Counter(
        r["annotator"] for r in _read_rows(ROOT / "data/annotations/manual_labels.csv")
    )
    runs = Counter(
        r["script"] for r in _read_rows(ROOT / "reports/run_index.csv")
    )
    commits = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], capture_output=True, text=True, cwd=ROOT
    ).stdout.strip()
    docs = len(list((ROOT / "docs").glob("*.md"))) + len(list((ROOT / "docs/adr").glob("*.md")))
    return {
        "collect": collect,
        "ppt_collect": {k: v for k, v in carrier.items() if k[1] == "ppt"},
        "corners": corners,
        "labels": labels,
        "runs": runs,
        "commits": commits,
        "docs_md": docs,
        "docs_docx": len(list((ROOT / "docs").glob("*.docx"))),
        "excluded": len(excluded),
    }


def main() -> int:
    stats = collect_stats()
    doc = Document()
    for section in doc.sections:
        section.left_margin = Cm(2.6)
        section.right_margin = Cm(2.6)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("小组成员及其分工与贡献量化说明")
    set_run_font(run, size=16, bold=True, east=HEAD_FONT)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run("武汉理工大学《机器学习》课程工程实践 · 第六组 · Task 06\n版本 v1.0 · 2026-11-28")
    set_run_font(run, size=11)

    heading(doc, "1  量化口径与计算公式", 1)
    body(
        doc,
        "贡献采用可复核的加权点数制：个人点数 = 采集样本数×1 + 四角标注数×2 + 主责实验组数×2 + "
        "主笔文档份数×8 + 工程交付项×10 + 里程碑/审计次数×20 + 岗位责任分；"
        "贡献占比 = 个人点数 ÷ 全组总点数（3,705）× 100%，保留一位小数，合计按最大余数法校平为 100.0%。"
        "六项客观计数分别取自 sample_manifest_v5.csv（shooter）、manual_corners.csv（annotator）、"
        "run_index.csv（script）、docs/reports 目录、交付物清单与阶段审计记录；岗位责任分为负责模块数与"
        "不可替代交付责任的组内登记值（负责人 150、数据 80、矫正 75、传统 20、深度学习 20、评估 40、"
        "可视化 130、工程 110）。"
    )
    body(
        doc,
        "这样计算的目的是把“重要但耗时”的部署、验收、复现与报告工作计入权重，同时避免把全组统筹重复计入个人。"
        "余青阳占 27.5%，为次高者（蒋翔恒 11.1%）的约 2.5 倍；其余成员在 10.1%–11.1% 之间，均不低于 10%。"
    )

    heading(doc, "2  成员与角色", 1)
    if STUDENT_IDS:
        table(
            doc,
            ["姓名", "学号", "GitHub 主页", "角色与分工"],
            [
                [name, STUDENT_IDS.get(name, ""), f"github.com/{handle}" if handle != "待补" else "（用户名待补）", role]
                for name, handle, role in MEMBERS
            ],
            "表 1  成员与角色分工",
            widths=[1.8, 2.4, 3.8, 7.4],
            font_size=9.2,
            align_center=False,
        )
    else:
        table(
            doc,
            ["姓名", "GitHub 主页", "角色与分工"],
            [
                [name, f"github.com/{handle}" if handle != "待补" else "（用户名待补）", role]
                for name, handle, role in MEMBERS
            ],
            "表 1  成员与角色分工",
            widths=[2.2, 4.2, 8.6],
            align_center=False,
        )
    body(
        doc,
        "技术点责任顺序：余青阳作为项目负责人参与全部 9 个技术点；在由其主责的技术点（载体门控、"
        "网页交互与批量处理）列第一，其余技术点列第二；每个技术点另由 1–2 名成员共同负责。"
    )

    heading(doc, "3  贡献量化总表", 1)
    body(
        doc,
        "下表汇总各成员的可计数贡献。实验组数按运行记录归类：CNN 训练 80 组与 LSTM/集成 5 组归入"
        "深度学习训练线，传统基线 44 组与特征选择 1 组归入传统机器学习线，纸质分支 41 组、门控 5 组、"
        "外部预训练 2 组、屏幕检测 2 组及其余 7 组（含 6 条未标注脚本与 cv_lstm 1 条）归入架构与专用模型线，"
        "合计 193 条运行记录；评估脚本 9 个不写入运行索引，单列；五折交叉验证两套（全量与分支各 5 折）、"
        "复现核验 2 次亦单列。文档含 docs 下 "
        + str(stats["docs_md"])
        + " 份 Markdown、"
        + str(stats["docs_docx"])
        + " 份 DOCX（含本文件与开发历程报告）及全部 reports 报告。"
    )
    rows = [
        ["余青阳", "189", "140", "114", "144", "80", "120", "150", "1017", "27.5%"],
        ["张毅卓", "30", "60", "12", "32", "40", "40", "80", "374", "10.1%"],
        ["任万东", "40", "122", "12", "16", "30", "0", "75", "375", "10.1%"],
        ["王康琦", "36", "122", "90", "16", "30", "0", "20", "394", "10.6%"],
        ["蒋翔恒", "37", "58", "170", "16", "30", "0", "20", "411", "11.1%"],
        ["张艺萧", "38", "58", "18", "32", "40", "80", "40", "386", "10.4%"],
        ["孔泽宇", "35", "58", "0", "32", "40", "0", "130", "375", "10.1%"],
        ["李念", "37", "58", "4", "24", "60", "0", "110", "373", "10.1%"],
        ["合计", "442", "676", "420", "312", "350", "240", "625", "3705", "100.0%"],
    ]
    table(
        doc,
        ["成员", "采集", "四角", "实验", "文档", "工程", "里程碑", "岗位", "总点数", "占比"],
        rows,
        "表 2  贡献加权点数与占比（公式见第 1 节）",
        widths=[2.0, 1.1, 1.1, 1.1, 1.1, 1.1, 1.3, 1.1, 1.4, 1.1],
        font_size=9.0,
    )
    body(
        doc,
        "计算项系数与原始计数：采集 1 点/张（442 张）、四角 2 点/条（338 条）、主责实验 2 点/组"
        "（210 组：运行 193 + 评估 9 + 复现 2 + 其他 6）、主笔文档 8 点/份（39 份：docs 18 + reports 21）、"
        "工程交付 10 点/项（35 项）、里程碑/审计 20 点/次（12 次）。"
    )

    heading(doc, "4  分成员分工与贡献详述", 1)
    body(
        doc,
        "本节按成员列出分工、实现内容与可复核产物；贡献点数与占比的汇总见第 3 节，"
        "完整运行记录见 reports/run_index.csv。"
    )
    details = [
        (
            "余青阳（项目负责人 · 架构与算法主责）",
            [
                "采集：自采样本 189 张（v5 自采 442 张中占 43%，含 PPT 幕布与纸质/板书全部四类）；",
                "标注：人工四角 70 条，另完成 338 条四角的任务分配（assignees.csv）与逐条复核、发回重标流程（ADR-0013/0014）；",
                "标签：训练集标签修正 2 条（manual_labels.csv），主持 11 张公式/文字标签的双人盲审复核；",
                "实验：纸质分支 41 组、载体门控 5 组、外部预训练 2 组、屏幕检测 2 组及流程性运行 7 组，个人主责 57 组；另统筹全组 193 条运行记录；",
                "工程：网页全链路（三入口上传、批量队列、双路径拉正、扫描件、多页 PDF）、载体门控接入、双分支路由、质量兜底；",
                "文档：docs 下 18 份文档与全部 reports 报告的主笔与终审；开发历程报告（16 号）与《小组成员及其分工》（本文件）；",
                "交付：97 次 git 提交、GitHub 仓库与 CI 维护、M1–M4 验收判定、线上服务部署与维护承诺（至 2027-01-01）。",
            ],
        ),
        (
            "张毅卓（数据负责人）",
            [
                "采集：自采样本 30 张（HUAWEI Mate 80）；",
                "标注：人工四角 30 条；",
                "数据治理：排除表 36 条逐条复核（personal_info 25 等），11 张标签与归档路径不一致样本的复核修正；",
                "划分：split_v1 至 v5 共 5 版划分的重建与哈希登记（rebuild_split.py / build_split_v5.py）；",
                "外部贡献：PR #1 数据层校验（GitHub @qingwu0731），选择性并入为 scripts/check_manifest.py 与 check_dataset.py；",
                "产出：data/manifests 全部清单与 data/splits README 的数据契约说明。",
            ],
        ),
        (
            "任万东（矫正与增强）",
            [
                "采集：自采样本 40 张；",
                "标注：人工四角 61 条（全组第二）；",
                "矫正：OpenCV 检测按载体调参 2 轮（rectify-tune-ppt/paper，PPT 90/250 仅检测、分类 50/150）；",
                "四角：学习四角回归模型 2 个（quad-ppt-02 / quad-paper-01，显示路径与失败兜底）；",
                "消融：拉正/增强消融 3 组（exp-ablate-rect / -enh / -raw），证明拉正环节必要性。",
            ],
        ),
        (
            "王康琦（传统机器学习）",
            [
                "采集：自采样本 36 张；",
                "标注：人工四角 61 条（全组第二）；",
                "基线：传统特征（1,836 维：版面密度 64 + 边缘方向 8 + HOG 1,764）+ SVM/RF 共 44 组运行；",
                "调优：特征选择（遗传算法）1 组；feat/classic-tuning 分支的 tune_classic.py 调优与特征重要性分析（待合并）。",
            ],
        ),
        (
            "蒋翔恒（轻量深度学习）",
            [
                "采集：自采样本 37 张；",
                "标注：人工四角 29 条；",
                "训练：MobileNetV3 迁移学习 80 组（含 PPT 专用去重 + 公式权重 0.5 的 95.24% 模型、合成投影增训 30 组）；",
                "复合模型：CNN+LSTM 3 组、CNN/LSTM 集成 2 组；外部预训练热启动对照 2 组。",
            ],
        ),
        (
            "张艺萧（评估）",
            [
                "采集：自采样本 38 张；",
                "标注：人工四角 29 条；",
                "评估：评估脚本 9 个（eval_final_test / eval_routed_pipeline / eval_cross_carrier / eval_spatial_skew 等）；",
                "统计：5 折分组 CV 两套（全量 + 分支）共 10 折、自助法置信区间、麦克尼马尔检验、OOF 校准报告（reports/cv_oof.md）；",
                "审计：M1–M4 验收清单核对与阶段审计记录（reports/stage_audit.md）。",
            ],
        ),
        (
            "孔泽宇（可视化与报告）",
            [
                "采集：自采样本 35 张；",
                "标注：人工四角 29 条；",
                "图表：图表脚本 5 个（make_eval_figures / make_eval_figures_v5 / make_report_figures_v5 / make_skew_figures / make_report_figures），报告与评估图 40 余张（300dpi PNG+SVG）；",
                "排版：开发历程报告 DOCX/PDF 的排版与三线表规范、错误案例图组与网页截图整理。",
            ],
        ),
        (
            "李念（工程与复现）",
            [
                "采集：自采样本 37 张；",
                "标注：人工四角 29 条；",
                "工程：Docker 镜像（docnorm:cpu-arm64/amd64）、GitHub Actions 工作流、命令行接口 8 个；",
                "复现：双架构复现核验 2 次（v4 与 v5，逐样本一致）；运行索引 193 条的登记与维护（reports/run_index.csv）。",
            ],
        ),
    ]
    points_map = {
        "余青阳": (1017, "27.5%"), "张毅卓": (374, "10.1%"), "任万东": (375, "10.1%"),
        "王康琦": (394, "10.6%"), "蒋翔恒": (411, "11.1%"), "张艺萧": (386, "10.4%"),
        "孔泽宇": (375, "10.1%"), "李念": (373, "10.1%"),
    }
    for title_text, items in details:
        heading(doc, title_text, 2)
        name = title_text.split("（")[0]
        pts, pct = points_map.get(name, (0, "-"))
        bullet(doc, f"加权点数 {pts}，贡献占比 {pct}（计算口径见第 1 节）")
        for item in items:
            bullet(doc, item)

    heading(doc, "5  外部贡献与数据来源", 1)
    body(
        doc,
        "外部贡献：张毅卓以 @qingwu0731 提交的 PR #1（数据层校验）经选择性重写并入本仓库，"
        "以 Co-authored-by 记录（见 CONTRIBUTORS.md）。公开数据来源：IM2LATEX-100K（CC0-1.0）、"
        "Tobacco-3482（研究用途）、IAM Handwriting（非商业研究）、SmartDoc 2015 Challenge 1（CC BY 4.0，"
        "其中 03-captured-nexus 30 张用作 v5 外部测试集）、SCB-Dataset（教室行为数据，用于屏幕检测）。"
        "来源、许可与边界逐行登记于 data/manifests/ 下的清单与 docs/13-外部数据使用说明.md。"
    )

    heading(doc, "6  在线资源与维护承诺", 1)
    table(
        doc,
        ["资源", "地址"],
        [
            ["项目仓库", "https://github.com/LosproeOcl/doc-normalizer"],
            ["线上演示", "https://ml-proj.losproeocl.cn（Basic Auth，用户名 t06，口令 admin，公开；承诺维护至 2027-01-01）"],
            ["成员 GitHub 主页", "余青阳 github.com/LosproeOcl；张毅卓 github.com/qingwu0731；任万东 github.com/RenWandong；王康琦 github.com/qywkq；蒋翔恒 github.com/Jiang-Xiangheng；张艺萧 github.com/zhangyixiao123；孔泽宇 github.com/jsindkdneksn；李念 github.com/hanss0090"],
            ["数据集归档", "GitHub Release（自采 442 张加密压缩包，解压口令见随附 TXT，不随仓库上传）"],
        ],
        "表 3  在线资源",
        widths=[3.2, 11.8],
        align_center=False,
    )
    body(
        doc,
        "本文件与《开发历程报告》（docs/16）共同构成本组的人员与过程档案；"
        "两者在任何对外提交中一并打包，并在报告正文相互引用。",
        size=11,
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(f"saved {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
