"""生成开发者视角开发历程报告（DOCX，论文格式）。"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "reports/developer_report_assets"
OUTPUT = ROOT / "docs/16-开发历程报告.docx"

BODY_FONT = "宋体"
HEAD_FONT = "黑体"
LATIN_FONT = "Times New Roman"


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
    fonts.set(qn("w:hAnsi"), latin)
    if color:
        run.font.color.rgb = RGBColor(*color)


def body(doc, text, *, indent=True, size=12, bold=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    paragraph = doc.add_paragraph()
    paragraph.alignment = align
    paragraph.paragraph_format.line_spacing = 1.5
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.first_line_indent = Pt(size * 2) if indent else Pt(0)
    run = paragraph.add_run(text)
    set_run_font(run, size=size, bold=bold)
    return paragraph


def bullet(doc, text, *, size=12):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.line_spacing = 1.5
    paragraph.paragraph_format.left_indent = Pt(24)
    paragraph.paragraph_format.first_line_indent = Pt(-12)
    paragraph.paragraph_format.space_after = Pt(2)
    run = paragraph.add_run("• " + text)
    set_run_font(run, size=size)


def heading(doc, text, level=1):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.page_break_before = False
    paragraph.paragraph_format.space_before = Pt(14 if level == 1 else 10)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(text)
    size = {1: 16, 2: 14, 3: 12}[level]
    set_run_font(run, size=size, bold=True, east=HEAD_FONT)
    p_pr = paragraph._p.get_or_add_pPr()
    outline = OxmlElement("w:outlineLvl")
    outline.set(qn("w:val"), str(level - 1))
    p_pr.append(outline)
    return paragraph


def caption(doc, text, kind="图"):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(10)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.keep_with_next = kind == "表"
    run = paragraph.add_run(text)
    set_run_font(run, size=10.5)


def figure(doc, filename, cap, width_cm=15.0):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(8)
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.keep_together = True
    run = paragraph.add_run()
    run.add_picture(str(ASSETS / filename), width=Cm(width_cm))
    caption(doc, cap)


def shade(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _three_line_borders(table_obj) -> None:
    """三线表：仅保留顶线与底线，表头下加细线，无竖线。"""
    tbl_pr = table_obj._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    spec = (
        ("top", "single", "12"),
        ("bottom", "single", "12"),
        ("left", "none", "0"),
        ("right", "none", "0"),
        ("insideH", "none", "0"),
        ("insideV", "none", "0"),
    )
    for tag, val, size in spec:
        element = OxmlElement(f"w:{tag}")
        element.set(qn("w:val"), val)
        if val == "single":
            element.set(qn("w:sz"), size)
            element.set(qn("w:space"), "0")
            element.set(qn("w:color"), "000000")
        borders.append(element)
    tbl_pr.append(borders)


def _header_bottom_border(cell) -> None:
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
    caption(doc, cap, kind="表")
    table_obj = doc.add_table(rows=1, cols=len(headers))
    _three_line_borders(table_obj)
    table_obj.alignment = WD_TABLE_ALIGNMENT.CENTER
    header_row = table_obj.rows[0]
    tr_pr = header_row._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    tr_pr.append(repeat)
    header_cells = header_row.cells
    for index, text in enumerate(headers):
        header_cells[index].text = ""
        paragraph = header_cells[index].paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Pt(0)
        run = paragraph.add_run(str(text))
        set_run_font(run, size=font_size, bold=True)
        _header_bottom_border(header_cells[index])
    for row in rows:
        cells = table_obj.add_row().cells
        for index, text in enumerate(row):
            cells[index].text = ""
            paragraph = cells[index].paragraphs[0]
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER if align_center else WD_ALIGN_PARAGRAPH.LEFT
            )
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.15
            run = paragraph.add_run(str(text))
            set_run_font(run, size=font_size)
    for row_index, row in enumerate(table_obj.rows):
        tr_pr = row._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        tr_pr.append(cant_split)
        if row_index < len(table_obj.rows) - 1:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.keep_with_next = True
    table_obj.autofit = False
    if widths:
        # 控制总宽不超过版心 15.6 cm，并写入 tblGrid，避免长 URL 把表格撑出页面
        total = sum(widths)
        scale = min(1.0, 15.6 / total) if total else 1.0
        scaled = [width * scale for width in widths]
        for row in table_obj.rows:
            for index, width in enumerate(scaled):
                row.cells[index].width = Cm(width)
        grid = table_obj._tbl.tblGrid
        if grid is not None:
            for col, width in zip(grid.gridCol_lst, scaled):
                col.set(qn("w:w"), str(int(round(width * 567))))
        tbl_pr = table_obj._tbl.tblPr
        tbl_w = OxmlElement("w:tblW")
        tbl_w.set(qn("w:w"), str(int(round(sum(scaled) * 567))))
        tbl_w.set(qn("w:type"), "dxa")
        tbl_pr.append(tbl_w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_page_number(paragraph):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instruction)
    run._r.append(end)


def add_toc(doc):
    entries = [
        ("1  引言", 1), ("1.1  任务背景", 2), ("1.2  报告结构", 2), ("1.3  符号与约定", 2),
        ("2  数据集的选择与处理", 1), ("2.1  数据来源与采集口径", 2), ("2.2  数据形状与分布", 2),
        ("2.3  清洗、分组与划分", 2), ("2.4  标注体系与质量", 2),
        ("3  模型类型的选择", 1), ("3.1  任务分解", 2), ("3.2  传统模型与深度学习模型", 2),
        ("3.3  所用算法清单与原理简述", 2), ("3.4  载体门控与双分支", 2),
        ("3.5  四角定位模型：OpenCV 与学习回归", 2),
        ("4  模型架构设计与模块排布", 1), ("4.1  总体架构", 2), ("4.2  载体门控", 2),
        ("4.3  内容分类分支", 2), ("4.4  双路径拉正", 2), ("4.5  部署结构", 2),
        ("5  模型参数与版本更迭", 1), ("5.1  训练与评估配置", 2), ("5.2  版本演进顺序", 2),
        ("5.3  关键参数迭代", 2), ("5.4  上线取舍与原因", 2),
        ("6  开发过程中遇到的问题与解决方案", 1), ("6.1  数据问题", 2), ("6.2  模型问题", 2),
        ("6.3  工程问题", 2), ("6.4  流程问题", 2),
        ("7  不同版本产物与测试截图", 1), ("7.1  早期批量队列与结果页", 2),
        ("7.2  偏度样本的失败与修正", 2), ("7.3  当前双路径与显示切换", 2),
        ("8  当前上线状态与阶段审计", 1), ("8.1  线上模型与指标", 2),
        ("8.2  v4 测试集一次性评估（历史）", 2), ("8.3  v5 重建与测试集一次性评估", 2),
        ("8.4  阶段审计结论", 2), ("8.5  残余风险", 2),
        ("9  小组分工与量化贡献", 1), ("10  结论", 1), ("参考文献", 1),
        ("附录 A  关键复现命令", 1), ("附录 B  线上模型清单", 1),
        ("附录 C  产出文档索引与在线资源", 1), ("附录 D  部署、测试、使用与数据集获取", 1),
    ]
    begin_paragraph = doc.add_paragraph()
    begin_run = begin_paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = 'TOC \\o "1-1" \\h \\z \\u'
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    begin_run._r.append(begin)
    begin_run._r.append(instruction)
    begin_run._r.append(separate)
    for title, level in entries:
        if level != 1:
            continue
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Pt(0)
        paragraph.paragraph_format.first_line_indent = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.0
        run = paragraph.add_run(title)
        set_run_font(run, size=10.5)
    end_paragraph = doc.add_paragraph()
    end_run = end_paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    end_run._r.append(end)


def setup_document():
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.8)
    section.right_margin = Cm(2.8)
    section.header_distance = Cm(1.5)
    section.footer_distance = Cm(1.5)
    section.different_first_page_header_footer = True

    normal = doc.styles["Normal"]
    normal.font.name = LATIN_FONT
    normal.font.size = Pt(12)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header.add_run("武汉理工大学《机器学习》课程实践 · 第六组")
    set_run_font(run, size=9, color=(120, 120, 120))

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_page_number(footer)

    settings = doc.settings.element
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    settings.append(update)
    return doc


def cover(doc):
    for _ in range(4):
        doc.add_paragraph()
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("斜拍文档规范化系统的\n数据、模型与上线演进")
    set_run_font(run, size=24, bold=True, east=HEAD_FONT)

    for _ in range(4):
        doc.add_paragraph()

    for text, size in [
        ("武汉理工大学《机器学习》课程实践", 14),
        ("第六组 · Task 06", 12),
        ("报告版本：v1.6（v5 口径，评审修订）", 11),
        ("2026 年 11 月 28 日", 11),
    ]:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(text)
        set_run_font(run, size=size)
    doc.add_page_break()


def abstract(doc):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("摘  要")
    set_run_font(run, size=16, bold=True, east=HEAD_FONT)

    body(
        doc,
        "本报告记录斜拍文档规范化系统从数据构建到上线的开发过程。系统面向投影幕布（PPT）与纸质或板书的"
        "非正面拍摄场景，完成文档定位与透视矫正、反光抑制与增强、文字/公式内容归类。数据由 v3 的 340 张"
        "（236/51/53）扩展到 v4 的 442 张，2026-11-28 重建为 v5（自采 442 + 外部测试 30；训练 349 / 验证 51 / "
        "测试 72）；模型从传统特征+SVM 基线，发展到“载体门控 + 双分支 CNN”，再演进到“OpenCV 分类拉正 + "
        "学习四角显示拉正”的双路径结构。"
    )
    body(
        doc,
        "v4 验证集路由为 86.27% / 宏 F1 86.19%，v4 测试集一次性评估为 67.92%；清单级审计确认各分支训练清单"
        "未越过 split_v4 边界，归因于跨场景域差与样本量。v5 全量重训后，验证集 84.31% / 83.81%，测试集"
        "一次性评估 93.06% / 92.65%（自采 88.10%、外部 100%），里程碑 M3（测试指标达标）通过。"
        "局限：v5 更换了测试基准，v4 与 v5 数字不可直接比较；自采子集与公式召回的 Wilson 区间下界低于门槛；"
        "外部子集仅含文字类页面且与训练共享文档模型，100% 不代表公式或全新文档的泛化。"
    )
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.first_line_indent = Pt(0)
    run = paragraph.add_run("关键词：")
    set_run_font(run, size=12, bold=True, east=HEAD_FONT)
    run = paragraph.add_run("文档规范化；载体门控；MobileNetV3；四角回归；双路径拉正；数据标注")
    set_run_font(run, size=12)

    doc.add_page_break()


def toc(doc):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("目  录")
    set_run_font(run, size=16, bold=True, east=HEAD_FONT)
    paragraph.paragraph_format.space_after = Pt(8)
    add_toc(doc)
    doc.add_page_break()


def section_intro(doc):
    heading(doc, "1  引言", 1)
    heading(doc, "1.1  任务背景", 2)
    body(
        doc,
        "课程实践要求完成一个斜拍文档规范化系统：输入手机或相机拍摄的文档照片，定位文档四角，"
        "进行透视变换得到正面图，并判断页面内容是纯文字还是包含数学公式。实际场景中，"
        "拍摄对象并不总是 A4 纸，还包括教室投影幕布、黑板板书、纸质笔记本和打印材料；"
        "拍摄角度、室内灯光、幕布反光和纸张纹理都会影响定位与分类。"
    )
    body(
        doc,
        "项目周期只有两周，数据规模有限，且需要在中央处理器上完成训练和演示。"
        "因此开发路线按“先跑通、再拆解、再替换、最后解耦”的顺序迭代："
        "先用传统特征建立可复现基线，再用 MobileNetV3 做迁移学习；发现单一模型难以同时处理幕布与纸质稿后，"
        "引入载体门控和双分支；发现标注四角可以训练定位模型后，又尝试把定位与分类解耦，"
        "最终形成当前的双路径拉正结构。"
    )

    heading(doc, "1.2  报告结构", 2)
    body(
        doc,
        "第 2 章说明数据集的选择、形状、清洗和标注；第 3 章说明模型类型的选择依据并给出所用算法的"
        "清单与原理简述；第 4 章给出最终模型架构、架构迭代过程与各模块的排布；第 5 章按版本记录参数"
        "选择与变化、指标变化和上线取舍；第 6 章归纳开发中遇到的问题与解决方案；第 7 章结合版本截图"
        "说明产物演进；第 8 章给出当前上线状态与阶段审计结论；第 9 章给出小组分工与量化贡献；"
        "第 10 章总结可复用的经验；附录 A–D 提供复现命令、模型清单、文档索引，以及面向检查者的"
        "部署、测试、使用与数据集获取指南。"
    )

    heading(doc, "1.3  符号与约定", 2)
    body(
        doc,
        "为避免歧义，全文统一使用下表中的术语与符号。载体名称固定为“投影幕布（PPT）”与“纸质或板书”；"
        "“A4 纸质”仅指打印 A4 纸张样本（外部数据与示例图），归档标签 paper_* 同时涵盖纸质笔记与板书。"
        "内容类别固定为“纯文字/含公式”。归档标签（四选一）用于数据登记与文件目录；评估标签（二选一）用于"
        "指标计算，映射关系由配置文件定义（ADR-0008）。关键超参数（Canny 阈值、门控 TTA/阈值、公式权重）"
        "集中在 §5.1 表 9/10，不在本表重复。"
    )
    table(
        doc,
        ["符号 / 术语", "含义与约定"],
        [
            ["ppt_text / ppt_formula / paper_text / paper_formula", "四格归档标签：载体（投影幕布、纸质/板书）× 内容（纯文字、含公式），对应 data/raw_samples 下的四个目录"],
            ["text / formula", "评估用内容二分类标签；paper_text→text、ppt_formula→formula 等按 label_map 映射"],
            ["doc_page_id", "文档页分组键：同一页幻灯片/笔记的多角度照片共享该键，划分时整组进入同一集合"],
            ["shooter", "拍摄者缩写（yqy=余青阳、zyz=张毅卓、rwd=任万东、wkq=王康琦、jxh=蒋翔恒、zyx=张艺萧、kzy=孔泽宇、ln=李念）；external 表示外部样本"],
            ["split_v4 / split_v5", "冻结划分版本；v4 为 338/51/53 历史口径，v5 为当前口径 349/51/72（含外部测试 30 张）"],
            ["train / val / test", "训练集（拟合参数）、验证集（模型选择与早停）、测试集（仅最终一次性评估）"],
            ["Acc / 宏 F1", "准确率与宏平均 F1（文字、公式两类 F1 的算术平均）"],
            ["95% CI", "自助法（bootstrap）1,000 次重采样得到的 95% 置信区间"],
            ["CV / OOF", "交叉验证（Cross-Validation，按 doc_page_id 分组 5 折）与折外预测（Out-of-Fold）"],
            ["去重（dedupe）", "同一幻灯片多角度照片按清晰度只保留一张参与训练"],
            ["runs/<实验编号>", "一次训练/评估的产物目录（metrics.json、run.json、模型权重、日志）"],
        ],
        "表 1  全文符号与约定",
        widths=[6.2, 8.8],
        font_size=9.5,
        align_center=False,
    )
    heading(doc, "1.4  里程碑与验收标准", 2)
    body(
        doc,
        "报告中的 M1–M4 是本组采用的四个阶段门禁，标准在项目开始时写入 docs/05-项目计划与分工.md，"
        "每个里程碑均以仓库产物为证据判定："
    )
    bullet(doc, "M1 数据就绪：合格样本完成采集、质量检查与标注登记，划分文件首次冻结（v3，236/51/53，340 张），"
                "清单与磁盘文件一致；以 split 文件、排除表与数据契约测试为证据。")
    bullet(doc, "M2 基线可用：传统特征 + SVM/随机森林与 MobileNetV3 两个基线完成，验证集路由准确率达到 82% 门禁；"
                "以验证集指标文件与运行日志为证据。")
    bullet(doc, "M3 指标达标：测试集一次性评估准确率不低于 85%，并完成传统/深度学习/分支对比、混淆矩阵、"
                "分类别召回与按载体分组；以 reports/final_test_v5.md 与评估 JSON 为证据。")
    bullet(doc, "M4 交付冻结：代码、报告、成员分工文档、复现核验（逐样本一致）、对外材料合规抽查与网页功能验收全部完成；"
                "以 tag、repro_check 记录与提交包为证据。")
    body(
        doc,
        "本报告对应的判定：M1 于 2026-11-26 通过（v3 冻结），M2 于 2026-11-27 通过（验证 86.27%，高于 82%），"
        "M3 于 2026-11-28 通过（v5 测试集合计 93.06%，附基准变更与置信区间披露），M4 于 2026-11-28 通过"
        "（恢复重建权重已复现验证集路由 84.31%，测试复评 90.28% 并单独披露）。"
    )


def section_data(doc):
    heading(doc, "2  数据集的选择与处理", 1)
    heading(doc, "2.1  数据来源与采集口径", 2)
    body(
        doc,
        "数据集全部为组员实地实拍：投影幕布拍摄于教室课堂，纸质/板书拍摄于教室、宿舍桌面与户外，"
        "每张样本在清单中逐张登记拍摄者（shooter）、设备、场景、光照、分辨率与拍摄时间，"
        "清单与图像一一对应并可复核，因此数据集本身即构成采数留证；组内 2026-11-28 决定以"
        "“实拍数据集 + 逐张元数据”作为留证口径，不再单独提交现场过程照片。"
        "自采合格样本 442 张；另引入 SmartDoc 2015 的 30 张外部实拍作为外部测试子集。"
        "自采数据集以加密压缩包形式归档于 GitHub Release（解压口令见随附《项目访问与数据集口令.txt》，不随仓库上传）。"
    )
    body(
        doc,
        "自采数据全部来自校内教室、宿舍和自习场景，按“载体 × 内容”划分为四个归档格："
        "PPT/幕布文字、PPT/幕布公式、纸质/板书文字、纸质/板书公式。采集时要求文档四角完整入画、"
        "主体内容可辨认，避免路人正脸、学号和姓名等个人信息；含个人信息的样本统一进入排除表，"
        "不参与训练、验证和测试。"
    )
    body(
        doc,
        "外部数据只作辅助训练，不进入自采评估集。SCB screen[4] 数据用于训练投影幕布/载体门控的正类；"
        "SmartDoc 2015[5]、Tobacco3482[6]、IAM[7] 与 IM2LaTeX[8] 用于纸质分支的辅助训练或外部对照；"
        "外部预训练权重另做零样本评估，但不在网页默认链路中直接使用。外部数据的来源、许可和用途"
        "记录在 data/manifests/ 下的辅助清单与 docs/13-外部数据使用说明.md 中。"
    )

    heading(doc, "2.2  数据形状与分布", 2)
    body(
        doc,
        "截至 2026-11-27，样本清单共 478 条记录，剔除 36 条不合格样本后，合格样本 442 张。"
        "按内容二分类统计为文字 244 张、公式 198 张；按载体统计为 PPT/幕布 250 张、纸质/板书 192 张。"
        "其中 340 张为 v3 冻结口径（训练 236 / 验证 51 / 测试 53）；v4 新增两批共 102 张 PPT 训练样本后达到 442 张，"
        "冻结划分 split_v4 的计数为训练 338、验证 51、测试 53，val/test 与 v3 保持同一批文档页。"
        "各集合的内容与载体分布如表 2 所示。2026-11-28 重建 split_v5：新增 30 张外部测试样本"
        "（SmartDoc 2015 03-captured-nexus，全部 paper_text，只进测试集），自采测试样本改从 v4 训练集按"
        "doc_page_id 分层留出，v4 测试集并入训练集，v4 验证集保持不变；v5 合格样本 472 张，"
        "计数为训练 349、验证 51、测试 72，分布见表 3。"
    )
    table(
        doc,
        ["集合", "文字", "公式", "合计", "PPT/幕布", "纸质/板书"],
        [
            ["训练", "188", "150", "338", "205", "133"],
            ["验证", "28", "23", "51", "21", "30"],
            ["测试", "28", "25", "53", "24", "29"],
            ["合计", "244", "198", "442", "250", "192"],
        ],
        "表 2  合格样本的集合、内容与载体分布（v4 口径）",
        widths=[2.2, 2.4, 2.4, 2.4, 3.2, 3.2],
    )
    table(
        doc,
        ["集合", "文字", "公式", "合计", "PPT/幕布", "纸质/板书"],
        [
            ["训练", "204", "145", "349", "208", "141"],
            ["验证", "28", "23", "51", "21", "30"],
            ["测试（含外部 30）", "42", "30", "72", "21", "51"],
            ["合计（含外部 30）", "274", "198", "472", "250", "222"],
        ],
        "表 3  v5 口径的集合、内容与载体分布",
        widths=[3.4, 2.4, 2.4, 2.4, 3.2, 3.2],
    )
    body(
        doc,
        "排除表的 36 条记录中，personal_info 25 条、non_course_document 4 条、unlabeled 3 条、"
        "low_resolution 3 条、missing_file 1 条。分辨率范围为 1080×784 至 6120×4596，"
        "常见尺寸包括 4032×3024、3072×4096、4096×3072、1279×1706 和 5712×4284。"
        "分辨率差异较大，因此训练与推理统一先按长边缩放，再进入检测或分类。"
    )
    figure(doc, "dataset_examples.png", "图 1  四类代表性样本（上排：投影幕布文字/公式；下排：纸质/板书以 A4 纸质为例。数据集全部为实地实拍，逐张登记拍摄者、时间、场景与光照，本身即为采数留证）", 15.2)
    figure(
        doc,
        "dataset_overview.png",
        "图 2  数据集总览缩略图（每类 6 张、共 24 张；第 1/2 行为投影幕布，第 3/4 行为纸质/板书；均已剔除含人脸与可识别个人信息的样本）",
        15.8,
    )
    figure(
        doc,
        "eval_v5_distribution.png",
        "图 3  v5 各集合内容构成与采集条件分布（右图括号内为场景样本数）",
        15.4,
    )

    heading(doc, "2.3  清洗、分组与划分", 2)
    body(
        doc,
        "数据处理的第一条原则是“同一文档页只进入一个集合”。清单用 doc_page_id 作为分组键，"
        "同一张幻灯片或同一页笔记的多角度照片共享该键；划分脚本按分组键切分，避免同一页的不同角度"
        "同时出现在训练和验证中。第一批 93 张新增 PPT 样本按幻灯片内容聚合为 48 组；"
        "第二批 9 张目标检测章节实拍包含两张幻灯片，其中 5 张成立 PT-INBOX-G49，"
        "另外 4 张与已有 Anchor Box 页合并到 PT-INBOX-G15，避免同页被误当成两个独立分组。"
    )
    body(
        doc,
        "清洗过程中发现过三类问题：一是清单登记但磁盘文件缺失，数据层加入文件存在性校验并把缺失样本写入排除表；"
        "二是内容标签与归档路径不一致，人工复核后修正了 11 张样本并重算 split_v3 哈希；"
        "三是同一页多角度样本被误合并或误拆分，通过看图复核和分组脚本修正。每次修改清单都重新计算"
        "manifest_sha256，训练与评估启动时校验哈希，防止“沿用旧划分但换了清单”的隐性错误。"
    )
    body(
        doc,
        "第二批 9 张样本的导入流程被固化为 scripts/ingest_inbox_batch.py：读取映射表，把图像移入类别目录，"
        "追加清单行，更新幻灯片分组与 train 集合，重算清单哈希。这样新增数据不再依赖手工改 CSV，"
        "也保证第二批样本能进入四角训练集。"
    )

    heading(doc, "2.4  标注体系与质量", 2)
    body(
        doc,
        "训练集四角标注使用网页“训练集四角”工具完成：系统先给出自动检测或学习四角建议，标注人拖动四个控制点，"
        "确认后写入 manual_corners.csv。标注只允许训练集样本，服务端校验样本归属与标注人，"
        "验证集和测试集不能写入。标注任务按人分配：原始 236 张分给 8 名成员；第一批 93 张按公式/文字分层，"
        "平均分给任万东、王康琦、余青阳各 31 张；第二批 9 张全部分给余青阳。最终训练集 338 张全部有记录。"
    )
    figure(doc, "annotation_examples.png", "图 4  人工四角标注示例（左：PPT 公式；中：PPT 文字；右：A4 纸质；红框为保存的四角，黄点为顶点）", 15.2)
    figure(
        doc,
        "annotation_examples_overview.png",
        "图 5  人工四角标注缩略总览（6 张 PPT + 6 张纸质，均为无个人信息样本；每格下方为样本标识）",
        15.8,
    )
    body(
        doc,
        "结构审计结果显示：338 条记录均为唯一 sample_id，全部属于训练集；四角面积占比 0.0455–0.9901，"
        "中位数 0.5919；没有重复点、共线、非凸或越界记录。标注人分布为余青阳 70、任万东 61、王康琦 61、"
        "张毅卓 30、李念 29、蒋翔恒 29、张艺萧 29、孔泽宇 29。标注阶段还修复了一个交互问题："
        "手工点击顺序不一定是沿边缘的环状顺序，旧逻辑会把合法四边形误判为凹四边形；"
        "现在后端先取凸包再规范角点顺序，前端在第四个点落下后自动排序，并增加“重选四角”按钮。"
    )


def section_model_choice(doc):
    heading(doc, "3  模型类型的选择", 1)
    heading(doc, "3.1  任务分解", 2)
    body(
        doc,
        "最初把问题当成单一的四分类任务，但实际错误分析发现两类错误来源不同：一类是“载体判断错误”，"
        "例如把投影幕布当成纸质稿；另一类是“内容判断错误”，例如公式页被当成文字页。"
        "把两者拆开后，可以为不同载体选择不同的预处理、分类模型和评估口径，也便于定位错误来源。"
        "最终任务分解为：载体门控（PPT/幕布 vs 纸质/板书）、内容二分类（文字 vs 公式）、"
        "四角定位与透视拉正、以及网页端的交互与导出。"
    )

    heading(doc, "3.2  传统模型与深度学习模型", 2)
    body(
        doc,
        "传统基线使用 1,836 维特征：版面密度 64 维、边缘方向直方图 8 维、HOG 1,764 维，"
        "分别训练 SVM 与随机森林。SVM 在验证集上为 76.47% / 宏 F1 75.71%，随机森林为 72.55% / 71.21%。"
        "传统特征可解释、训练快，适合作为复现基线，但对幕布反光、透视形变和公式符号的区分能力有限。"
    )
    body(
        doc,
        "深度学习选择 MobileNetV3-Small[1]，而不是更大的 MobileNetV3-Large 或 EfficientNet-B0。"
        "原因有三点：训练和演示都在中央处理器上完成，轻量骨干的推理与迭代成本更低；自采训练集只有数百张，"
        "大模型更容易过拟合；输入 224 像素已经能保留公式符号和版面结构。实验也验证了这一点："
        "主对照 MobileNetV3-Small 224 为 80.4%；MobileNetV3-Large 224 为 78.4%，EfficientNet-B0 为 74.5%，"
        "Small 输入从 224 提高到 320 反而降到 78.4%（数据见 reports/algorithm_tuning.md）。"
        "因此最终把 MobileNetV3-Small + 224 作为主骨干。"
    )
    body(
        doc,
        "外部预训练权重也做过零样本测试：在 340 张真实数据上仅 54.41%，formula 召回 0%–2.58%，"
        "等于多数类基线。这说明外部裁剪公式图与手机整页拍摄之间存在明显域差，外部数据只能用于辅助训练或"
        "初始化，不能直接部署。"
    )

    heading(doc, "3.3  所用算法清单与原理简述", 2)
    body(
        doc,
        "系统实际用到的算法按下表逐一列明，覆盖矫正、增强、传统基线、深度模型与评估五个环节。"
        "表中“原理简述”给出理解所需的最低限度解释，便于非算法岗成员复核。"
    )
    table(
        doc,
        ["算法", "所在环节", "原理简述"],
        [
            ["Canny 边缘检测", "文档定位", "高斯平滑去噪后用 Sobel 求梯度幅值与方向，再以高低双阈值筛选强边缘，弱边缘仅在与强边缘连通时保留（滞后连接），得到连续的文档边界直线"],
            ["四边形拟合与透视变换", "文档矫正", "对边缘点用多边形逼近得到四边形顶点，按“左上、右上、右下、左下”排序后求解 3×3 单应矩阵，把任意四边形区域映射为正对矩形（warpPerspective）"],
            ["CLAHE + 阴影抑制", "反光/光照增强", "限制对比度的自适应直方图均衡：把图像分块均衡、对直方图裁剪限幅，避免局部过增强；另用大尺度背景估计估计光照并相除，抑制侧向阴影"],
            ["自适应阈值二值化", "扫描件模式", "以局部均值减常数 C 作为逐像素阈值（cv2.adaptiveThreshold），使不同亮度区域都能得到清晰的黑白文本"],
            ["版面密度 / 边缘方向 / HOG 特征", "传统基线特征", "版面密度统计文字块的疏密分布；边缘方向直方图统计梯度主方向；HOG 在单元格内累计梯度方向并做块归一化，共 1,836 维"],
            ["SVM（支持向量机）", "传统基线分类", "在特征空间中寻找使两类样本间隔最大的超平面，仅由少数支持向量决定；用 RBF 核把特征隐式映射到高维处理线性不可分，概率输出经 Platt 校准"],
            ["随机森林", "传统基线对照", "Bagging 思想：对样本和特征做有放回抽样训练多棵决策树，预测时投票/平均，方差低、对特征尺度不敏感"],
            ["MobileNetV3-Small", "深度分类主干", "轻量 CNN：倒残差块（先 1×1 升维、3×3 深度可分离卷积、1×1 降维）压缩计算量，通道注意力（SE）加权重要通道，h-swish 激活；ImageNet 预训练后两阶段微调"],
            ["迁移学习两阶段微调", "CNN 训练策略", "先冻结主干只训练分类头（大学习率），再解冻全部层用小学习率微调，避免小样本把预训练特征拉偏"],
            ["载体门控（二分类 CNN）", "PPT/纸质分支路由", "同一 MobileNetV3 主干训练 screen/other 二分类，输出 P(screen) 概率，配合旋转 TTA 与阈值 0.30 决定走哪个分支"],
            ["旋转 TTA", "门控稳健性", "测试时增强：对输入做 -12°/0°/+12° 三次旋转分别预测再取平均，缓解空间偏度导致的误判"],
            ["四角回归（QuadRegressor）", "显示路径拉正", "以 CNN 主干 + 全连接头直接回归四个角点坐标（SmoothL1 损失），用于显示/PDF 路径与检测失败兜底"],
            ["CNN+LSTM 复合模型", "对照实验", "CNN 提取全图特征后按行切成序列交给 LSTM（门控循环记忆单元，通过输入门/遗忘门/输出门控制信息流），测试序列建模能否提升整页判别，结论为无稳定收益"],
            ["遗传算法特征选择", "传统特征降维", "把特征子集编码为染色体，以验证准确率为适应度，经选择、交叉、变异迭代搜索更优子集，效果有限未采用"],
            ["StratifiedGroupKFold", "交叉验证", "分层分组 K 折：保证每折内类别比例接近，同时同一 doc_page_id 的样本不跨折，避免分组泄漏"],
            ["Platt/概率校准与 OOF", "阈值与校准", "用折外预测拟合阈值与概率校准，避免在验证集上反复调参造成过拟合"],
            ["自助法置信区间", "统计报告", "对测试集有放回重采样 1,000 次计算准确率分布，取 2.5%/97.5% 分位作为 95% CI"],
            ["麦克尼马尔检验", "模型对比", "对两模型在同一测试集上的逐样本对错做配对卡方检验，判断差异是否显著"],
        ],
        "表 4  系统所用算法清单与原理简述",
        widths=[4.2, 2.6, 8.2],
        font_size=9.0,
        align_center=False,
    )

    heading(doc, "3.4  载体门控与双分支", 2)
    body(
        doc,
        "载体门控沿用 MobileNetV3-Small 二分类结构，输入 160×160，输出 other/screen 两类概率。"
        "训练清单混合 SCB 屏幕、自采 PPT/paper 与外部 A4 数据；v4 时期为 2,236 张训练，v5 重训后为 2,349 张训练、1,000 张外部验证；"
        "自采验证 51 张只做最终检查；v5 门控在外部验证 1,000/1,000（外部同源），自采验证与测试中的少量门控误判由质量兜底纠正，"
        "但训练集审计 338 张中有 2 张错误，说明“高分”不等于“没有难例”。"
    )
    body(
        doc,
        "门控之后是两条内容分支。PPT 分支使用单模型 MobileNetV3-Small；纸质分支在 v4 使用 3 个种子的 CNN 集成、v5 改为 s45/s47 二模型集成，"
        "对三个 softmax 概率取平均。纸质稿的外部数据域差更大，单模型在 30 张纸质验证上只有 70%–86.67%，"
        "集成可以降低单次训练波动。两条分支都缺失时回退传统 SVM，保证网页在模型文件缺失时仍能分析。"
    )

    heading(doc, "3.5  四角定位模型：OpenCV 与学习回归", 2)
    body(
        doc,
        "四角定位最初使用 OpenCV[2] 规则检测：灰度化、Canny 边缘、轮廓/最小外接矩形、面积门槛、候选评分。"
        "它的优点是无需训练、速度快、可解释；缺点是对低对比度纸张、强反光和多文档同框不稳定。"
        "在 160 张早期实测中自动检出率约 82%，纸质公式类只有 62%。"
    )
    body(
        doc,
        "随着训练集人工四角标注完成，我们尝试用 MobileNetV3-Small 直接回归 8 个归一化坐标"
        "（左上、右上、右下、左下）。这是一个“定位模型”，不参与内容分类。PPT 四角模型在 52 张验证页上"
        "全部有预测，平均 L2 为 0.1314；纸质模型在 29 张验证页上全部有预测，L2 为 0.1347。"
        "同样验证集上 OpenCV 调优参数虽然成功样本的 L2 接近（0.18 左右），但会拒检一部分页面。"
        "这为后面的“双路径”提供了基础。"
    )


def section_architecture(doc):
    heading(doc, "4  模型架构设计与模块排布", 1)
    heading(doc, "4.1  总体架构", 2)
    body(
        doc,
        "当前线上架构可以概括为“一个门控、两条分类分支、两条拉正路径、一个兜底”。"
        "上传图像先做 EXIF 方向校正和长边限制，再进入载体门控；门控输出 PPT 或纸质，"
        "分别选择 OpenCV 分类拉正参数和内容分类模型；学习四角模型独立运行，只负责显示、扫描件和 PDF 的拉正。"
        "两条路径在用户手动应用四角或手动切换载体时可以重新汇合。总体结构如图 6 所示。"
    )
    figure(doc, "architecture.png", "图 6  当前线上模型与双路径拉正结构", 15.4)
    body(
        doc,
        "该架构经历了三次整体迭代，每次迭代都由明确的失效证据触发，而不是追逐新模型："
        "第一次迭代（单模型 → 门控 + 双分支）由“PPT 幕布与 A4 纸质在亮度、纹理、构图上差异过大，"
        "单一模型顾此失彼”触发；第二次迭代（单路径 → 分类/显示双路径）由“学习四角定位更准，"
        "但改变分类输入分布导致准确率下降”触发；第三次迭代（v5 全量重训与纸质二模型集成）由"
        "“v4 测试评估暴露训练集与测试集口径重叠”触发。各次迭代的动机与关键参数变化见表 5。"
    )
    table(
        doc,
        ["迭代", "架构变化", "触发原因（证据）", "关键参数变化"],
        [
            ["第 1 次\n单模型 → 门控 + 双分支", "新增载体门控（MobileNetV3 二分类，160 输入）；内容分类拆成 PPT/纸质两个 CNN；SVM 降为兜底", "单一 CNN 在混合载体验证集上互相拖累；门控在自采 val 51/51 全对", "门控：3 轮、batch 48、输入 160、冻结 2 轮；分支按载体独立训练"],
            ["第 2 次\n单路径 → 分类/显示双路径", "分类路径保持 OpenCV 拉正；显示/PDF 路径引入学习四角（quad-ppt-02、quad-paper-01）；手动四角可统一覆盖两条路径", "学习四角直接作分类输入：全链路 86.27%→82.35%；作兜底 84.31%；按其重训仅 71.43%/70.00%", "quad 回归：SmoothL1、L2 0.1314/0.1347；分类 Canny 固定 50/150（90/250 仅检测实验）"],
            ["第 3 次\nv4 模型 → v5 全量重训", "全部分类模型在 v5 训练集重训；纸质分支由 3 模型集成改为 s45/s47 二模型集成；网页默认权重切换", "v4 一次性测试 67.92%；清单级审计确认无 split 泄漏，归因于域差与样本量；为建立稳定基准重建 v5（旧测试并入训练、自采测试由旧训练池留出、加外部 30 张）", "PPT：15 轮/冻结 3/去重/公式权重 0.5；纸质：6 轮/冻结 3/外部文本 761 张；SVM/CNN 全量重训；其余推理参数（阈值 0.3、TTA）不变"],
        ],
        "表 5  整体架构的三次迭代：变化、原因与参数",
        widths=[3.0, 4.6, 4.2, 3.2],
        font_size=9.0,
        align_center=False,
    )

    heading(doc, "4.2  载体门控", 2)
    body(
        doc,
        "门控输入为上传原图（长边限制 2,000 像素后缩放至 160×160），默认在 -12°、0°、+12° 三个旋转角度上"
        "做 TTA，对三个 softmax 输出取平均，阈值设为 0.30：P(screen) ≥ 0.30 判为 PPT，否则判为纸质。"
        "阈值 0.30 是空间偏度实验的结果：在 21 张 PPT 验证页的合成梯形透视（0°/30°/40°）压力测试中，"
        "门控 TTA + 0.3 把 30°/40° 条件下的完整链路从 71.4% 提升到 81.0%。"
        "门控只决定分支，不直接决定内容标签。"
    )
    figure(
        doc,
        "carrier_gate_curves_v5.png",
        "图 7  载体门控训练曲线（v5 恢复重建版：2,149 训练 / 900 验证；原权重日志已丢失）",
        14.0,
    )

    heading(doc, "4.3  内容分类分支", 2)
    body(
        doc,
        "v5 冻结链路的 PPT 分支使用 exp-cnn-ppt-v5：MobileNetV3-Small，输入 224×224，按幻灯片去重后训练 155 张、"
        "验证 21 张，公式类权重 0.5。验证集准确率 95.24%，宏 F1 92.93%。"
        "纸质分支使用 paper-cnn-v5-s45/s47 两个种子，输入 224×224，基于自采 paper（141 张训练 / 30 张验证）"
        "加 SmartDoc 500 张与 Tobacco Scientific 261 张外部文本训练（合计 902 张训练），"
        "两模型概率平均后验证 76.67%。SVM 兜底使用 exp-svm-v5（传统特征，v5 训练 349 张），验证 72.55%。"
        "作为对照，v4 时期的 PPT 分支 exp-cnn-ppt-dedup-fw 同样为 95.24%；纸质 3 模型集成的 80.00% 与 v5 的 76.67% "
        "训练池不同（v5 从训练集移出 21 张纸质样本作测试、并入 v4 测试 29 张纸质样本），两者不可直接拼接。"
    )
    figure(
        doc,
        "paper_model_curves_v5.png",
        "图 8  纸质分支训练曲线（v5 恢复重建版：s45 / s47 的验证准确率）",
        13.5,
    )
    table(
        doc,
        ["模块", "骨干/结构", "输入", "训练/验证", "验证指标"],
        [
            ["载体门控", "MobileNetV3-Small 二分类", "160×160", "2,349 / 1,000", "外部 1000/1000；v5 test 69/72（兜底纠正）"],
            ["PPT 分类", "MobileNetV3-Small（exp-cnn-ppt-v5）", "224×224", "155 / 21（去重）", "95.24% / F1 92.93%"],
            ["纸质分类", "2×MobileNetV3-Small 集成（s45/s47）", "224×224", "902 / 30", "集成 76.67%（单模型 73.33%）"],
            ["SVM 兜底", "1,836 维特征 + SVM（exp-svm-v5）", "拉正图", "349 / 51", "72.55% / F1 71.21%"],
        ],
        "表 6  线上内容分支与兜底模型",
        widths=[2.5, 5.0, 2.3, 2.7, 4.5],
    )

    heading(doc, "4.4  双路径拉正", 2)
    body(
        doc,
        "双路径是本次开发最重要的结构决策。分类路径继续使用 OpenCV[2] 拉正：PPT/纸质均 Canny 50/150（PPT 90/250 仅为检测实验），"
        "面积门槛 0.15–0.98，输出长边 1,600。显示/导出路径使用学习四角：PPT quad-ppt-02、纸质 quad-paper-01，"
        "预测四角后做透视变换，生成矫正图和扫描件。两条路径共享同一张原图和同一套人工四角；"
        "用户手动应用四角后，两条路径都切换到人工四角。"
    )
    body(
        doc,
        "这样拆分的依据在于分类器对拉正分布非常敏感。实测（v4 验证集口径）把学习四角直接作为分类输入时，"
        "全链路从 86.27% 降到 82.35%；只把学习四角作为检测失败兜底也降到 84.31%；"
        "按学习四角重训内容模型则降到 PPT 71.43%、纸质 70.00%。定位精度提高并不自动带来分类提高。"
        "把两条路径拆开后，分类器保持训练时的 OpenCV 分布，显示/PDF 则获得更完整的幕布四角，"
        "分类指标不下降。"
    )
    table(
        doc,
        ["路径", "拉正方式", "参数/模型", "用途"],
        [
            ["分类路径", "OpenCV 规则检测", "PPT/纸质 50/150（90/250 仅检测实验）", "决定 text/formula；v4 口径 86.27%，v5 84.31%"],
            ["显示/导出", "学习四角回归", "quad-ppt-02；quad-paper-01", "矫正图、扫描件、PDF"],
            ["人工覆盖", "人工四角", "manual_corners / 用户点选", "两条路径统一切换"],
        ],
        "表 7  双路径拉正的分工",
        widths=[2.6, 4.0, 5.2, 5.0],
    )
    doc.add_page_break()
    figure(
        doc,
        "rectify_scan_ppt.png",
        "图 9  正面 PPT 三联：原图 / OpenCV 拉正（Canny 50/150）/ 扫描件（自适应二值化）",
        15.8,
    )

    heading(doc, "4.5  部署结构", 2)
    body(
        doc,
        "服务使用 FastAPI[3] + Uvicorn，直接运行在 Server1 的 Docker 容器 docnorm:cpu-amd64，"
        "绑定 127.0.0.1:54312；Nginx 反向代理，不使用 SSH 反向隧道。公开部署设置 "
        "DOCNORM_PUBLIC_MODE=1，前端隐藏训练集标签、四角与标注检查，后端对应接口返回 404。"
        "模型权重不进入 Git，部署时挂载 runs/ 目录；健康检查 /api/health 返回门控、PPT/纸质模型、"
        "SVM、学习四角、quad_policy、quad_display、public_mode 与 routing_ready。分析接口在线程池中执行，"
        "并发上限 2，上传长边限制 2,000 像素，解码像素上限 6,000 万，避免大图拖死整机。"
    )


def section_versions(doc):
    heading(doc, "5  模型参数与版本更迭", 1)
    heading(doc, "5.1  训练与评估配置", 2)
    body(
        doc,
        "v4 实验使用 split_v4，v5 实验使用 split_v5；随机种子默认 42，跨种子实验另设 43–47。训练只在训练集上更新参数，"
        "验证集用于早停和模型选择，测试集不参与调参。CNN 训练默认冻结骨干 3 轮，分类头学习率 1e-3，"
        "解冻后全模型学习率 1e-4，batch 32，输入 224，增强为默认的随机裁剪、旋转、透视和颜色扰动。"
        "PPT 专用模型额外使用 --dedupe-inbox 按幻灯片去重，并把公式类权重乘 0.5；"
        "纸质集成在 v4 使用种子 42/43/44，v5 使用 s45/s47。需要注意：验证集自 v3 沿用至 v5 并参与多轮模型选择，"
        "其单点数值已有选择偏差，§5.4 的 5 折分组 CV 用于对冲这一偏差。"
    )
    table(
        doc,
        ["项目", "PPT 分类", "纸质分类", "载体门控", "四角回归"],
        [
            ["骨干", "MobileNetV3-Small", "MobileNetV3-Small", "MobileNetV3-Small", "MobileNetV3-Small"],
            ["输入", "224×224", "224×224", "160×160", "224×224"],
            ["训练/验证", "155 / 21（v5 去重；v4 为 152/21）", "902 / 30（v5；v4 为 894/30）", "2,349 / 1,000（v5；v4 为 2,236/1,000）", "153 / 52（PPT）；104 / 29（纸质）"],
            ["轮数/早停", "15 / 5", "6 / 2", "3", "30 / 6"],
            ["关键参数", "公式权重 0.5；按幻灯片去重", "外部文本 + 自采 paper；平衡类权重", "TTA ±12°；阈值 0.3", "SmoothL1；冻结 3 轮"],
            ["验证结果", "95.24% / F1 92.93%", "集成 76.67%", "外部 1000/1000", "L2 0.1314 / 0.1347"],
        ],
        "表 8  当前主要模型的训练配置（v5）",
        widths=[2.6, 4.3, 4.0, 3.0, 4.2],
        font_size=9.5,
    )
    table(
        doc,
        ["参数", "取值", "选择理由"],
        [
            ["训练轮数 / 早停耐心", "PPT 15/5；纸质 6/2；门控 3/2；CNN 13/5", "小样本下验证损失 2–4 轮内即过拟合，早停按验证集 accuracy 保留最佳轮；耐心值取“验证集单样本≈2% 波动”经验值"],
            ["学习率（head / 全网）", "1e-3 / 1e-4（AdamW）", "两阶段迁移学习常用配置：分类头用大学习率快速收敛，解冻后用小学习率保护预训练特征"],
            ["输入尺寸 / batch", "224×224 / 32（分类）；160×160 / 48（门控）", "224 为 MobileNetV3 预训练原生输入；门控只需场景级判断，160 足够且省时"],
            ["类别权重", "自动 balanced；PPT 公式权重再乘 0.5", "平衡权重缓解公式样本少；实验发现 PPT 上公式页背景与文字页接近，权重 1.0 会过度偏向公式，0.5 在验证集上最优"],
            ["数据增强", "RandomResizedCrop(0.7–1.0)+旋转 5°+透视 0.15+色彩抖动（default）", "模拟拍摄角度与光照变化；增强强度提高（skew）在公式页上反而降低召回，故公式密集分支保持 default"],
            ["拉正 / 输出长边", "OpenCV 50/150；输出 1,600", "338 张人工四角调参结论：更高阈值提高幕布检出率但分类输入分布变化，折中取 50/150"],
            ["门控阈值 / TTA", "0.30；-12°/0°/+12° 平均", "合成 30°/40° 偏度压力测试：TTA+0.3 把完整链路 71.4%→81.0%"],
            ["随机种子", "42（对照实验另设 43/44/45…）", "与 runtime.seed 一致；跨种子重跑用于报告均值 ± 标准差而非单点"],
        ],
        "表 9  关键训练参数的取值与选择理由（v5 最终配置）",
        widths=[3.6, 4.6, 6.8],
        font_size=9.0,
        align_center=False,
    )

    heading(doc, "5.2  版本演进顺序", 2)
    body(
        doc,
        "版本演进的主线是持续修正评估口径、拆分任务和确认上线边界，而非单纯追逐指标。"
        "表 10 按时间顺序列出关键版本、参数变化和最终决策。"
    )
    table(
        doc,
        ["版本", "数据/时间", "模型与关键参数", "验证结果", "上线决策"],
        [
            ["V0", "v3 236/51/53", "传统特征 1,836 维 + SVM/RF", "SVM 76.47%；RF 72.55%", "保留为兜底"],
            ["V1", "v3", "MobileNetV3-Small 224，未增强，13 轮、冻结 2 轮、batch 32", "80.39% / F1 79.03%", "替换传统主模型"],
            ["V2", "v3，修正 11 张标签", "载体门控 + 纸质 3 模型集成 + PPT CNN", "旧标签 88.24%；修正后 84.31%", "接入双分支，旧指标不再作为当前值"],
            ["V3", "v4 338/51/53", "PPT 去重 + 公式权重 0.5（dedup-fw）", "PPT 95.24%；全链路 86.27%", "替换 PPT 分支，v4 基线（历史）"],
            ["V3.1", "v4", "从旧模型热启动（warm-01）", "95.24% / F1 91.43%", "不替换：F1 略低"],
            ["V4", "v4 + 338 四角", "OpenCV 调参实验；分类回退 PPT/纸质 50/150，90/250 仅检测", "PPT 检测 84.62%；全链路 86.27%", "分类保持 50/150"],
            ["V5", "v4", "学习四角 quad-ppt-02 / quad-paper-01", "52/52、29/29；L2 0.1314/0.1347", "只用于显示/建议，不直接分类"],
            ["V5.1", "v4", "学习四角优先/兜底/重训内容模型", "82.35% / 84.31%；重训 71.43%/70.00%", "全部否决"],
            ["V5.2", "v4", "OpenCV 分类 + 学习四角显示 + 手动重试", "86.27% / F1 86.19%", "v4 时期线上版本"],
            ["V6", "v5 349/51/72（外部 30 只进 test）", "全部分类模型重训：门控 carrier-gate-v5-01、PPT exp-cnn-ppt-v5、纸质 paper-cnn-v5-s45/s47、SVM exp-svm-v5；纸质集成改为 2 模型（val 76.67%）", "路由 84.31% / F1 83.81%；测试 93.06% / F1 92.65%（CI 86.11%–98.61%；自采 88.10%、外部 100%）", "当前线上版本；v4 的 67.92% 转为历史结果"],
        ],
        "表 10  版本演进与上线取舍",
        widths=[1.4, 3.0, 7.0, 4.6, 4.2],
        font_size=9.0,
    )
    figure(doc, "val_metrics_v5.png", "图 10  v5 验证集指标与五折分组 CV 对比（左：验证/外部门控；右：CV 均值 ± 标准差）", 15.2)
    body(
        doc,
        "需要特别说明版本表中两组数值：V0 行随机森林的 72.55% 与 v5 SVM 的 72.55% 数值相同但实验不同"
        "（v3 的 RF 与 v5 的 SVM），不是复制错误；V0 行标注为 v3 口径。88.24% 与 84.31% 的关系是：88.24% 是标签修正前的旧口径：当时 11 张样本的公式/文字标签"
        "与归档路径不一致。人工复核后，旧模型在修正标签上降到 84.31%，属于评估口径修正带来的变化，模型本身并未退化。"
        "后续所有版本都在修正标签上比较，因此 v4 时期的 86.27% 不能与旧 88.24% 直接拼接。"
        "同理，v4 测试集一次性评估 67.92% 经清单级审计确认并非 split 泄漏（纸质分支训练清单仅含 v4 训练组 133 张，"
        "30 张验证组只用于早停）；v5 重建后基准已更换：旧测试并入训练、自采测试由旧训练池留出，"
        "因此 v4 的 67.92% 与 v5 的 93.06% 不可直接比较。纸质分支 val 从 80.00% 变为 76.67%，"
        "源于训练池与外部镜像变化，而非“去泄漏”。"
    )

    heading(doc, "5.3  关键参数迭代", 2)
    body(
        doc,
        "（1）类别权重与公式召回。早期单模型的公式召回只有 14/23，错误集中在“公式页判文字”。"
        "在损失中加入平衡类别权重后，公式召回提升，但 PPT 文本页出现少量误判；最终 PPT 专用模型把"
        "公式类权重乘 0.5，在 21 张 PPT 验证上达到 16 个文本正确、4 个公式全对、1 个文本误判，"
        "准确率 95.24%。"
    )
    body(
        doc,
        "（2）人工四角策略。训练时曾有 always/fallback/none 三种策略。always 把训练图全部换成紧贴边缘的"
        "裁切，验证集却仍用自动检测，分布偏移导致指标从 74.5% 降到 64.7%；最终采用 fallback："
        "自动检测成功时用自动结果，失败才回退人工四角。"
    )
    body(
        doc,
        "（3）PPT 去重与公式权重。新增 93 张 PPT 样本中同一幻灯片有多个角度，按 doc_page_id 聚合为 48 组，"
        "每组保留清晰度最高的一张作为分类训练代表；其余样本仍可用于四角训练。PPT 专用模型从 85.7% 提升到"
        "95.24%，说明去重和权重比单纯增加样本更有效。"
    )
    body(
        doc,
        "（4）OpenCV 参数。用 338 张人工四角对 Canny 阈值和面积门槛做网格搜索，按 doc_page_id 分组切分。"
        "PPT 90/250 虽把验证检出率从 76.92% 提升到 84.62%，但用它重训分类器只有 85.71% / F1 81.52%，"
        "因此分类拉正最终回退 50/150，90/250 只保留为检测实验。纸质保留 50/150。纸质 30/90 虽然把检出率"
        "提高到 86.21%，但全链路（v4 验证集口径）从 86.27% 降到 84.31%，因为 formula_14 被错误检出并拉正后判成 text。"
        "因此“检出率更高”不等于“端到端更好”。"
    )
    body(
        doc,
        "（5）学习四角。PPT 模型 52/52 覆盖、L2 0.1314；纸质 29/29、L2 0.1347。"
        "但直接替换分类输入时全链路降到 82.35%，按学习四角重训内容模型又因 152 张（v4 口径）样本过拟合降到 71.43%"
        "（PPT）和 70.00%（纸质 seed 42）。最终只把学习四角用于显示/PDF，分类器继续看 OpenCV 视图。"
    )

    heading(doc, "5.4  上线取舍与原因", 2)
    body(
        doc,
        "本节集中说明五类取舍：轻量 CNN 与更大骨干的取舍、载体门控与内容分类拆分、学习四角是否替换分类输入、"
        "OpenCV 与学习四角解耦的双路径拉正、以及 v4 测试暴露泛化不足后重建基准并全部重训（含基准变更披露）。"
        "各版本的指标与参数见 5.1–5.3。"
    )
    body(
        doc,
        "取舍一（v4 时期）：为什么当时用 86.27% 而不是旧 88.24%？因为 88.24% 建立在未修正的标签上，"
        "修正后旧模型只有 84.31%；86.27% 与同一口径可比，且 PPT 分支从 90.48% 提升到 95.24%。"
        "v5 重训后同类比较改为：纸质集成 76.67% 与 v4 的 80.00% 训练池/外部镜像不同，不可直接拼接。"
    )
    body(
        doc,
        "取舍二：为什么用 dedup-fw 而不是热启动？两者 PPT 准确率都是 95.24%，但热启动的宏 F1 为 91.43%，"
        "低于 dedup-fw 的 92.93%，说明公式类更不稳；在没有额外收益的情况下选择更平衡的模型。"
    )
    body(
        doc,
        "取舍三：为什么学习四角不做分类主定位？定位 L2 更小，但分类器对拉正后的尺度、裁切和透视变化敏感；"
        "重训又受限于 152/894 张（v4 口径）样本和分布差异。把定位与分类解耦，既保留学习四角的显示收益，"
        "又不牺牲分类指标。"
    )
    body(
        doc,
        "取舍四：为什么门控不做自动跨分支切换？实测按“谁置信度高用谁”会把 4 张 PPT 误切到纸质，"
        "全链路降到 80.39%（v4 口径）。最终只做 uncertain 标记、质量兜底与手动“按 PPT/纸质重试”，v5 沿用该策略，测试集 3 张门控误判均被纠正。"
    )
    figure(doc, "confusion_val_v5.png", "图 11  v5 验证集路由混淆矩阵（文字/公式，n=51，准确率 84.31%）", 10.5)
    body(
        doc,
        "单次 21 张验证集不足以支撑 PPT 分支选择，因此补充了 5 折分组交叉验证："
        "按 doc_page_id 分组、按载体×内容分层，每折 200 训练组 / 50 验证组，PPT 与纸质各 5 折 × 3 种子。"
        "PPT 折内均值 70.44% ± 8.24，纸质 88.90% ± 5.29；OOF 分别为 71.71% 和 90.23%。"
        "这说明原验证集 PPT 95.24% 是单点峰值，不能作为稳定泛化指标；纸质 OOF 虽高，但测试只有 72.4%，域差明显。"
        "OOF 阈值把 PPT 提到 75.12%、纸质 90.98%，但原验证集检查降到 84.31%，因此没有直接采用；"
        "用该阈值对测试集仅作诊断时为 69.81%，仍远低于 85%（以上均为 v4 口径）。详见 reports/cv_oof.md。"
        "v5 重建后重跑分支 CV：PPT 73.73% ± 12.42、纸质 85.00% ± 9.23（SVM 75.02% ± 7.80、CNN 77.00% ± 7.91），"
        "OOF 未重跑，v4 数值仅作历史对照。"
    )


def section_problems(doc):
    heading(doc, "6  开发过程中遇到的问题与解决方案", 1)
    body(
        doc,
        "项目遇到的问题大致分为数据、模型、工程和流程四类。表 11 汇总了影响较大的问题、解决方式和验证证据，"
        "随后对其中几个关键问题做展开说明。"
    )
    table(
        doc,
        ["类别", "问题", "解决方案", "验证/证据"],
        [
            ["数据", "同一文档页多角度跨集合，存在泄漏", "doc_page_id 分组；按组切分；看图复核", "split 互斥校验、集成测试"],
            ["数据", "标签与归档路径不一致", "人工复核 11 张，修正 file/label 并重算哈希", "split_v3/v4 哈希校验"],
            ["数据", "清单有记录但文件缺失", "文件存在性校验；写入排除表", "check_dataset.py 一致"],
            ["模型", "公式召回偏低", "平衡类权重；PPT 公式权重 0.5；分层划分", "PPT 95.24%，公式 4/4"],
            ["模型", "幕布偏度导致门控误判", "旋转 TTA；阈值 0.3；合成偏度评估", "30°/40° 71.4%→81.0%"],
            ["模型", "学习四角拉正改变分类输入分布", "分类/显示双路径；不直接替换分类", "82.35%→86.27%（v4 验证集）"],
            ["工程", "上传大图点击后卡死", "同步端点线程池；并发闸门；像素上限；JPEG 缩放解码", "健康检查 29 ms；上传分析正常"],
            ["工程", "手工四角被误判凹四边形", "凸包规范化；前端自动排序；重选按钮", "任意顺序保存成功"],
            ["工程", "多页 PDF 未逐页校准", "逐页校准门禁；待校准/已校准状态", "导出前拦截未校准页"],
            ["流程", "模型版本与文档数值漂移", "运行日志、模型清单、阶段审计", "104 项测试；审计报告"],
        ],
        "表 11  主要问题、解决方案与验证证据",
        widths=[1.8, 5.5, 6.5, 4.2],
        font_size=9.2,
    )

    heading(doc, "6.1  数据问题：泄漏、缺失与标签噪声", 2)
    body(
        doc,
        "数据泄漏是最危险的问题。同一张幻灯片的多角度照片如果被分到训练和验证，模型会“记住”页面而不是学习特征。"
        "因此所有划分都以 doc_page_id 为单位，新增样本先聚合幻灯片再入 train。第二批 Anchor Box 照片最初被当作"
        "新分组，复核后与已有 PT-INBOX-G15 合并，避免同页重复。"
    )
    body(
        doc,
        "标签噪声直接影响指标解释。人工复核发现 11 张样本的公式/文字标签与归档路径不一致，修正后重算哈希。"
        "这次修正让旧模型的验证结果从 88.24% 降到 84.31%，但这是更可信的口径。后续所有报告都明确区分"
        "“旧标签历史值”和“修正标签当前值”。"
    )

    heading(doc, "6.2  模型问题：召回、偏度与分布偏移", 2)
    body(
        doc,
        "公式召回偏低时，第一反应是换更大模型，但实验表明 MobileNetV3-Large、320 输入和 EfficientNet-B0"
        "都没有稳定收益。真正有效的是调整类别权重、按幻灯片去重和清理标签。这提醒我们：小样本任务里，"
        "数据质量和任务拆分往往比模型容量更重要。"
    )
    body(
        doc,
        "空间偏度问题暴露了门控的弱点：斜拍时幕布在画面中的形状和亮度变化，门控容易把它判成纸质。"
        "旋转 TTA + 0.3 阈值在 21 张 PPT 验证页的合成 30°/40° 透视测试上把完整链路从 71.4% 提升到 81.0%，但仍有高置信错误"
        "（如 IMG_6178，P(ppt)=0.082）。这类错误无法靠阈值修复，最终用结果卡的手动弹体重试兜底。"
    )
    figure(
        doc,
        "synth_ppt_preview.jpg",
        "图 12  合成投影 PPT 示例（SCB 教室背景 + 生成课件 + 投影退化，用于偏度与分布压力测试）",
        15.2,
    )
    body(
        doc,
        "学习四角的失败则说明“定位指标”和“分类指标”不是一回事。学习四角的角点 L2 更小，"
        "拉正图视觉上更完整，但分类器训练时看到的是 OpenCV 拉正图，换一种裁切/尺度就会翻转边界样本。"
        "重训内容模型的尝试又因为样本量小而过拟合。最终把定位与分类解耦，是这次开发最重要的工程判断之一，完整评估见 reports/quad_localization.md[10]。"
    )

    heading(doc, "6.3  工程问题：上传卡死、四角交互与 PDF", 2)
    body(
        doc,
        "上传卡死有两个根因：后端 /api/analyze 是 async def，却在事件循环里同步执行解码、OpenCV 和推理，"
        "一个请求就会堵住整个服务；前端选图时又在主线程用 createImageBitmap 解整张手机原图生成缩略图，"
        "多张大图叠加会触发内存抖动。修复方式是：端点改为同步函数交给 FastAPI 线程池；加入并发信号量、"
        "6,000 万像素上限和 JPEG DCT 缩放解码；前端改用 Blob URL + 懒加载，超过 15 MB 的文件直接跳过。"
        "修复后分析进行中健康检查仍能在 29 ms 内返回。"
    )
    body(
        doc,
        "手工四角的“四边形不是凸多边形”是点击顺序问题。旧 order_quad 假设四个点已经按环状顺序输入，"
        "用户按“左上→右下→右上→左下”点击时会把合法四边形判成非凸。现在先求凸包再规范化角点顺序，"
        "前端在第四个点落下后自动排序，并增加“重选四角”。"
    )
    body(
        doc,
        "多页 PDF 最初可以直接导出，但用户可能没有逐页确认四角。现在导出前检查 calibrated 状态，"
        "未校准的页面会被拦截，缩略图显示“待校准/已校准”；同时支持学习四角/OpenCV 两种视图导出。"
    )

    heading(doc, "6.4  流程问题：版本、文档与审计", 2)
    body(
        doc,
        "开发后期最大的风险在于“文档写的和代码跑的不一致”。例如 split_v3 与 split_v4、"
        "88.24% 与 84.31%、旧 PPT 模型与 dedup-fw 同时出现在不同文档里。为此增加了运行日志 run.json、"
        "reports/run_index.csv、reports/model_manifest.csv，并在阶段审计中逐项核对数据、模型、网页、测试和文档。"
        "2026-11-28 更新后的审计结论为：M2 通过、M3 通过（v5 测试集 93.06%，自采子集 88.10%）、M4 通过（报告与成员分工文档交付，复现核验逐样本一致，合规抽查通过）；详细清单见 reports/stage_audit.md[11]。"
    )


def section_screenshots(doc):
    heading(doc, "7  不同版本产物与测试截图", 1)
    body(
        doc,
        "仓库 docs/record-img/ 保存了开发过程中不同阶段的网页截图，reports/annotation_examples/ 保存了人工四角"
        "目视检查图。本节选取隐私风险较低的截图，说明界面和结果产物的演进；截图中的人脸与可识别个人信息均已"
        "模糊处理，未脱敏的原始照片不放入报告。"
    )
    heading(doc, "7.1  早期批量队列与单张结果页", 2)
    body(
        doc,
        "图 13 汇总 docs/record-img/ 的全部 10 张过程截图，按阶段分为 (a) 早期标注与批量队列 4 张、"
        "(b) 早期单图识别与偏度样本 3 张、(c) v5 当前版本 3 张。图 13(a) 包含训练集四角标注"
        "（含一次“只用 PPT 白色区域”的退回重标）、训练集标签校正、标注检查页与早期批量队列；"
        "图 13(b) 包含早期 PPT 文字单图、偏度失败样本与纸质文字单图。截图保留了当时的批量队列、"
        "逐张完成状态、原图/矫正图/扫描件三栏、四角拖动、PDF 模式与导出按钮；载体徽标、"
        "双路径显示切换和手动载体重试是后续版本补充的。"
    )
    figure(
        doc,
        "record_img_gallery_early_a.png",
        "图 13(a)  早期标注与批量队列（4 张）：训练集四角、标签校正、标注检查与早期批量队列；人脸与个人信息已模糊处理",
        15.8,
    )
    body(
        doc,
        "图 13(a) 的标注页展示了按人筛选、四角退回重标与标签校正的实际界面；批量队列页展示了逐张完成状态、"
        "三栏结果与导出入口。"
    )
    doc.add_page_break()
    figure(
        doc,
        "record_img_gallery_early_b.png",
        "图 13(b)  早期单图识别与偏度样本（3 张）：PPT 文字、偏度失败样本与纸质文字；人脸与个人信息已模糊处理",
        15.8,
    )
    body(
        doc,
        "从图 13(b) 可以看到，早期结果的矫正图与扫描件已经能把幕布内容拉正，但界面信息密度较高，"
        "结果卡只显示标签和概率，没有解释载体/分支，也没有显示“分类拉正”和“显示拉正”的区别。"
        "后续版本把载体、分支、不确定标记、显示切换拆成独立信息块，减少误读。"
    )

    heading(doc, "7.2  偏度样本的失败与修正", 2)
    body(
        doc,
        "图 14 是空间偏度样本的测试截图，文件名直接标注“偏度-不达预期”。该样本在早期链路中门控或定位不稳定，"
        "说明正面样本的高准确率不能外推到斜拍场景。后续用合成 0°–40° 压力测试定位瓶颈，"
        "引入门控旋转 TTA 与 0.3 阈值，并用学习四角提供失败建议，才把偏度场景的完整链路从 71.4% 提升到 81.0%。"
    )
    figure(doc, "record_skew.png", "图 14  偏度样本测试截图（早期版本，标注为“不达预期”）", 13.0)

    heading(doc, "7.3  当前双路径与显示切换", 2)
    body(
        doc,
        "当前版本在结果卡新增“拉正显示：学习四角 / OpenCV”切换。切换只改变矫正图、扫描件和 PDF 的视图，"
        "分类结果仍由 OpenCV 视图决定；OpenCV 未检出时切到 OpenCV 视图会显示原图，并提示原因。"
        "表 12 记录当前双路径接口与文件证据；图 13(c) 为 v5 当前版本的三张复验截图。"
    )
    table(
        doc,
        ["证据", "内容"],
        [
            ["/api/health", "routing_ready=true；quad_policy=off；quad_display=true"],
            ["/api/analyze", "返回 display_quad、classifier_status、suggested_quad、carrier_override"],
            ["结果文件", "rectified.png / rectified_opencv.png；scan.png / scan_opencv.png"],
            ["PDF 接口", "mode=scan|rectified|original；view=quad|opencv"],
        ],
        "表 12  当前双路径接口与产物证据",
        widths=[4.0, 11.0],
        align_center=False,
    )
    body(
        doc,
        "图 13(c) 汇总 v5 当前版本的三张复验截图：PPT 公式页、纸质公式页与纸质文字页。"
        "三张图均展示载体门控、命中分支、文字/公式概率、四角拖动、矫正图与扫描件，"
        "并保留“学习四角 / OpenCV”显示切换；与图 13(a)/(b) 的早期版本对照，可以直观看到信息块与交互的演进。"
    )
    figure(
        doc,
        "record_img_gallery_v5.png",
        "图 13(c)  v5 当前版本复验截图（3 张）：PPT 公式、纸质公式、纸质文字；含载体门控、分支概率、四角与扫描件",
        15.8,
    )
    body(
        doc,
        "版本截图的共同演进线索是：从“能分析一张图”到“能批量处理并校准”，再到“能解释分支、标记不确定、"
        "切换显示视图”。界面变化的背后是模型结构的变化：单模型 → 双分支 → 双路径 → 质量兜底。"
    )


def section_status(doc):
    heading(doc, "8  当前上线状态与阶段审计", 1)
    heading(doc, "8.1  线上模型与指标", 2)
    body(
        doc,
        "当前 t06-web 服务运行在 127.0.0.1:54312，健康检查 routing_ready=true。分类链路为 OpenCV 按载体拉正 + "
        "PPT/纸质分支；显示链路为学习四角拉正。2026-11-28 起默认权重切换为 v5 重训模型，样本索引改用 "
        "sample_manifest_v5.csv 与 split_v5.json。v5 验证集 51 张的指标为 84.31% / 宏 F1 83.81%，"
        "PPT 分支 95.24%，纸质分支 76.67%。作为历史对照，v4 时期同一验证集上旧链路为 86.27% / 宏 F1 86.19%、"
        "纸质分支 80.00%；v4 与 v5 的训练池不同，两组数字不可直接比较（审计见 §8.2）。"
    )
    table(
        doc,
        ["指标", "数值", "说明"],
        [
            ["全链路准确率", "84.31%（43/51）", "v5 验证集；v4 历史值 86.27%"],
            ["宏平均 F1", "83.81%", "文字/公式两类"],
            ["PPT 分支", "95.24%（20/21）", "exp-cnn-ppt-v5"],
            ["纸质分支", "76.67%（23/30）", "paper-cnn-v5-s45/s47 二模型集成"],
            ["外部 30 张（test）", "100%", "全部为文字类纸质页"],
            ["自动拉正（test）", "61/72", "11 张 rectify_failed 按原图分类兜底"],
        ],
        "表 13  当前验证集指标与测试集要点（v5 口径）",
        widths=[4.5, 4.5, 6.0],
        align_center=False,
    )
    heading(doc, "8.2  v4 测试集一次性评估（历史）", 2)
    body(
        doc,
        "在冻结当时模型与配置后，2026-11-27 对 v4 的 53 张测试集执行了一次性最终评估。该链路（v4 时期）准确率 67.92% / "
        "宏 F1 67.92%，95% 置信区间 54.72%–81.13%；其中纸质 72.41%、PPT 62.50%。单模型 CNN 为 66.04%，"
        "传统 SVM 为 67.92%，McNemar 检验 p=1.00。测试集未达到 85% 验收线。"
        "事后清单级审计（data/manifests/paper_content_extctl.csv × split_v4.json）：纸质分支训练清单的自采样本 133 张全部属于 v4 训练组，"
        "30 张验证组仅用于早停与验证，v4 验证/测试样本未进入任何分支的训练；载体门控与 PPT 分支同样只用训练组。"
        "因此 v4 的 67.92% 应归因于跨场景域差、难样本与训练量限制，而非数据泄漏。该结果保留为历史记录，不与 v5 混用。"
    )
    table(
        doc,
        ["方法", "准确率", "宏 F1", "说明"],
        [
            ["双分支路由（v4 模型）", "67.92%（36/53）", "67.92%", "95% CI 54.72%–81.13%"],
            ["单模型 CNN", "66.04%（35/53）", "63.86%", "exp-cnn-05"],
            ["传统 SVM", "67.92%（36/53）", "67.92%", "相同混淆矩阵"],
        ],
        "表 14  v4 测试集一次性评估结果（历史）",
        widths=[4.0, 4.5, 3.0, 4.5],
        align_center=False,
    )
    heading(doc, "8.3  v5 重建与测试集一次性评估", 2)
    body(
        doc,
        "针对上述泛化不足与测试基准局限，2026-11-28 重建 split_v5：v4 测试集并入训练集；自采测试样本改从 v4 "
        "训练集按 doc_page_id 分层留出 42 张（ppt_text 6 / ppt_formula 15 / paper_text 6 / paper_formula 15）；"
        "引入 SmartDoc 2015 的 03-captured-nexus 30 张作为外部测试子集（全部 paper_text，只进测试集，不参与"
        "训练、验证与阈值选择）；v4 验证集保持不变。全部分类模型在 v5 训练集上从零重训，模型选择只依据验证集；"
        "期间用自采-only 纸质对照（验证 40%–53%）否决了去掉外部文本数据的方案。"
    )
    body(
        doc,
        "冻结配置在 v5 测试集 72 张上的一次性评估为 93.06% / 宏 F1 92.65%，95% 置信区间 86.11%–98.61%；"
        "自采子集 42 张 88.10% / 86.83%，外部子集 30 张 100%（全部为文字类页面，不覆盖公式）。按载体纸质 96.08%、"
        "PPT 85.71%；文字召回 100%、公式召回 83.33%，均满足任一类召回不低于 70% 的要求。"
        "5 张错误全部为“公式→文字”的低公式密度页，CNN 与 SVM 基本同样误判；另有 11 张拉正失败按原图分类兜底、"
        "3 张门控误判被质量兜底纠正。McNemar 检验：路由对单模型 CNN p=0.00052、对 SVM p=0.00049。"
        "测试集在冻结前未运行任何评估，评估后未据此调参；复现核验逐样本完全一致。"
    )
    body(
        doc,
        "需要明确三项边界。第一，基准已更换：v5 将 v4 测试的 53 张并入训练集，自采测试的 42 张改从 v4 训练池留出，"
        "因此 v4 的 67.92% 与 v5 的 93.06% 不是同一把尺子，提升中“训练集扩充（含旧测试难例）”与“测试集换血”"
        "的贡献无法分离；新自采测试与训练同源，可能偏易，长期应以重新采集的独立留出集作为硬基准。"
        "第二，外部 30 张是 SmartDoc 的文档模型图（03-captured-nexus），与训练用的 500 张视频帧经 MD5 逐字节比对无重复，"
        "但两者共享同一批 30 个打印文档（文档级重叠，非图像级），因此外部 100% 部分反映同文档熟悉度，不能外推为"
        "全新文档表现；该子集只含 paper_text，宏 F1 的 100% 为退化值，不应单独引用。"
        "第三，统计稳健性：合计 67/72 的 Wilson 95% 区间为 84.8%–97.0%，自采 37/42 为 75.0%–94.8%，"
        "公式召回 25/30 为 66.4%–92.7%；按 doc_page_id 聚类的自助法因测试集 72 页互不重复，与逐图重采样一致"
        "（合计 86.1%–98.6%）。因此“达到 85%”仅在合计口径的点估计与区间下界边缘成立，自采子集与公式召回"
        "的区间下界低于门槛，报告不作过度外推。"
    )
    table(
        doc,
        ["方法 / 口径", "准确率", "宏 F1", "说明"],
        [
            ["双分支路由（合计 72）", "93.06%（67/72）", "92.65%", "95% CI 86.11%–98.61%"],
            ["双分支路由（自采 42）", "88.10%（37/42）", "86.83%", "更接近真实分布的口径"],
            ["双分支路由（外部 30）", "100%", "100%", "全部为文字类纸质页"],
            ["单模型 CNN", "73.61%（53/72）", "70.61%", "exp-cnn-v5"],
            ["传统 SVM", "76.39%（55/72）", "73.15%", "exp-svm-v5"],
            ["5 折分组 CV", "SVM 75.02%±7.80；CNN 77.00%±7.91；PPT 73.73%±12.42；纸质 85.00%±9.23", "—", "测试集未参与"],
        ],
        "表 15  v5 测试集一次性评估与交叉验证",
        widths=[4.6, 5.4, 2.4, 3.6],
        align_center=False,
    )
    table(
        doc,
        ["来源", "PPT 文字", "PPT 公式", "纸质/板书 文字", "纸质/板书 公式", "合计"],
        [
            ["自采", "6", "15", "6", "15", "42"],
            ["外部（SmartDoc）", "0", "0", "30", "0", "30"],
            ["合计", "6", "15", "36", "15", "72"],
        ],
        "表 16  v5 测试集构成（来源 × 载体 × 内容）",
        widths=[3.0, 2.2, 2.2, 3.0, 3.0, 1.8],
        font_size=9.5,
    )
    body(
        doc,
        "测试集 93.06% 高于验证集 84.31% 的原因有两项：其一，测试集合计中有 30 张（41.7%）是外部文字类纸质页，"
        "该子集全部判对且只覆盖文字类；其二，验证集 51 张中纸质公式 19 张（37.3%），而自采测试 42 张中纸质公式 "
        "15 张（35.7%），比例接近，但验证集的纸质公式页来自更早批次、拉正失败率更高。按同一自采口径比较，"
        "测试 88.10% 与验证 84.31% 的差距缩小到约 3.8 个百分点，仍低于合计口径的 93.06%，"
        "说明“合计达标”有相当部分来自外部易样本，不能直接解读为模型在真实分布上达到 93%。"
    )
    body(
        doc,
        "权重恢复说明（2026-11-28）：原 v5 权重与运行目录在一次本地文件操作中意外丢失，且 Tobacco-3482 原镜像的"
        "文件名不可复得。本组按公开来源重建数据（SmartDoc 2015 官方发布包经 SHA-256 校验、SCB 官方镜像、"
        "Tobacco-3482 另一公开镜像），以相同脚本与超参数重训后复评：合计 90.28% / 宏 F1 89.55"
        "（自采 83.33%、外部 100%；纸质 92.16%、PPT 85.71%，95% CI 83.33%–95.83%）。"
        "表中冻结的 93.06% 是原权重的一次性评估记录，继续作为 M3 的正式结果保留；两套权重的差异来自"
        "Tobacco 镜像中 261 张文本页的内容与命名不一致，评估口径未变。提交包内为恢复权重，"
        "复评明细见 reports/final_test_v5_recovery.json。"
    )
    figure(
        doc,
        "test_recovery_compare.png",
        "图 20  v5 测试集：正式冻结（原权重）与恢复权重复评的对照（合计/自采/外部）",
        13.0,
    )
    figure(
        doc,
        "eval_v5_overall.png",
        "图 15  v5 测试集方法对比与路由分层准确率（右图含 85% 门禁线）",
        15.4,
    )
    figure(
        doc,
        "eval_v5_confusion.png",
        "图 16  v5 测试集混淆矩阵（左：合计 72 张；右：自采 42 张）",
        14.0,
    )
    figure(
        doc,
        "eval_v5_recall.png",
        "图 17  分类别召回与 70% 下限（合计与自采口径）",
        11.5,
    )
    figure(
        doc,
        "eval_v5_cv.png",
        "图 18  v5 五折分组交叉验证（均值 ± 标准差）",
        12.5,
    )
    figure(
        doc,
        "eval_v5_ci.png",
        "图 19  v5 测试集准确率与自助法 95% 置信区间（含按载体点估计）",
        13.5,
    )
    body(
        doc,
        "图 15 至图 19 由 scripts/make_eval_figures_v5.py 直接读取 reports/final_test_v5.json 与 "
        "runs/cv-v5-* 的产物生成，可随评估结果重新渲染。需要注意图 15 右图：外部 30 张全部为文字类纸质页，"
        "其 100% 不能解读为公式表现；图 17 的公式召回 83.33% 是更接近真实短板的数字。"
    )
    heading(doc, "8.4  阶段审计结论", 2)
    body(
        doc,
        "阶段审计的结论是：M2 基线可用通过；M3 在 v5 口径下通过（测试集 93.06%，自采子集 88.10%，均不低于 85%，"
        "且附置信区间与分类别召回）；M4 解除指标阻塞，进入交付收尾。需要如实披露的边界：外部测试子集只覆盖"
        "文字类纸质页，其 100% 不能解读为公式表现；公式召回 83.33% 的短板仍存在，错误集中在低公式密度页；"
        "门控在外部域（杂志页）有 3 张误判，均被质量兜底纠正。"
    )
    body(
        doc,
        "M4 收尾清单：v5 复现核验与 tag（已完成，逐样本一致）、开发者报告与评估图表按 v5 重生成、"
        "演示文稿、对外材料合规抽查（D-01）。"
    )

    heading(doc, "8.5  残余风险", 2)
    body(
        doc,
        "v5 测试集 72 张，单样本约 1.4 个百分点；合计口径受测试集构成影响（外部 30 张全为文字类），"
        "因此自采子集 88.10% 是更接近真实分布的口径，报告中两者必须并列。公式召回 83.33% 与低公式密度页的"
        "边界歧义仍是主要风险；门控的外部域鲁棒性依赖质量兜底；C-03 零样本诊断曾在包含 v4 测试集的 340 张"
        "数据上运行过，虽未用于模型选择，但继续披露。测试集标签口径与域泛化的风险已在 reports/stage_audit.md 登记，"
        "v5 的错误归因见 reports/error_cases_v5.md。"
    )


def section_team(doc):
    heading(doc, "9  小组分工与量化贡献", 1)
    body(
        doc,
        "本组 8 名成员按“数据—模型—评估—工程—交付”五条线分工。贡献采用可复核的加权点数制换算为百分比，"
        "计算项全部来自仓库文件或组内登记的交付物，不使用主观评分；完整逐人说明见"
        "《小组成员及其分工》（docs/18-小组成员及其分工.docx）。"
    )
    body(
        doc,
        "计算公式：个人点数 = 采集样本数×1 + 四角标注数×2 + 主责实验组数×2 + 主笔文档份数×8 + "
        "工程交付项×10 + 里程碑/审计次数×20 + 岗位责任分；贡献占比 = 个人点数 ÷ 全组总点数 × 100%，"
        "保留一位小数，合计按最大余数法校平为 100.0%。采集、四角、实验、文档、工程、里程碑六项的原始计数"
        "分别取自 sample_manifest_v5.csv（shooter）、manual_corners.csv（annotator）、run_index.csv（script）、"
        "docs/reports 目录、交付物清单与阶段审计记录；岗位责任分为负责模块数与不可替代交付责任的组内登记值。"
    )
    table(
        doc,
        ["成员", "采集", "四角", "实验", "文档", "工程", "里程碑", "岗位", "总点数", "占比"],
        [
            ["余青阳", "189", "140", "114", "144", "80", "120", "150", "1017", "27.5%"],
            ["张毅卓", "30", "60", "12", "32", "40", "40", "80", "374", "10.1%"],
            ["任万东", "40", "122", "12", "16", "30", "0", "75", "375", "10.1%"],
            ["王康琦", "36", "122", "90", "16", "30", "0", "20", "394", "10.6%"],
            ["蒋翔恒", "37", "58", "170", "16", "30", "0", "20", "411", "11.1%"],
            ["张艺萧", "38", "58", "18", "32", "40", "80", "40", "386", "10.4%"],
            ["孔泽宇", "35", "58", "0", "32", "40", "0", "130", "375", "10.1%"],
            ["李念", "37", "58", "4", "24", "60", "0", "110", "373", "10.1%"],
            ["合计", "442", "676", "420", "312", "350", "240", "625", "3705", "100.0%"],
        ],
        "表 17  贡献加权点数与占比（计算过程见表 18 与正文公式）",
        widths=[2.0, 1.1, 1.1, 1.1, 1.1, 1.1, 1.3, 1.1, 1.4, 1.1],
        font_size=8.8,
    )
    table(
        doc,
        ["计算项", "系数", "原始计数与来源", "说明"],
        [
            ["采集样本", "1 点/张", "442 张，sample_manifest_v5.csv（shooter）", "按拍摄者归属，外部 30 张不计入成员"],
            ["四角标注", "2 点/条", "338 条，manual_corners.csv（annotator）", "按标注人归属；分配与复核计入岗位责任分"],
            ["主责实验", "2 点/组", "210 组（运行 193 + 评估 9 + 复现 2 + 其他 6）", "按 run_index 与评估/复现记录归属"],
            ["主笔文档", "8 点/份", "39 份（docs 18 + reports 21）", "含报告、规范、实验记录与评估报告"],
            ["工程交付", "10 点/项", "35 项", "容器/CI/CLI/部署/脚本/图表/运行索引等"],
            ["里程碑/审计", "20 点/次", "12 次", "M1–M4 判定、标签审计、复现核验、合规抽查"],
            ["岗位责任分", "登记值", "625 点", "负责人 150、数据 80、矫正 75、传统 20、深度学习 20、评估 40、可视化 130、工程 110"],
        ],
        "表 18  计算项、系数与原始计数",
        widths=[2.2, 1.8, 7.2, 4.4],
        font_size=8.8,
        align_center=False,
    )


def section_conclusion(doc):
    heading(doc, "10  结论", 1)
    body(
        doc,
        "这次开发给出的最重要经验是：在数据规模有限、部署资源有限的课程项目中，模型结构的选择必须和"
        "数据质量、评估口径、前端交互一起考虑。传统基线提供了可复现的起点，MobileNetV3-Small 在 CPU 上"
        "取得了可用的性价比；载体门控把“幕布/纸质”这个混杂因素拆开，双分支让各载体使用更适合的模型；"
        "四角标注不仅改善了训练回退，还让我们发现“定位更准”不等于“分类更好”；最终的双路径拉正把"
        "定位与分类解耦，让显示/PDF 用上了更好的四角。"
    )
    body(
        doc,
        "比模型结构更重要的教训来自评估口径：v4 测试集一次性评估为 67.92%，清单级审计确认各分支训练清单"
        "均未越过 split_v4 边界，问题在于跨场景泛化与训练量，而非 split 泄漏。2026-11-28 重建 split_v5 并"
        "全部重训后，验证为 84.31%，测试集合计 93.06%（自采 88.10%），M3 通过；但必须同时说明：v5 更换了"
        "测试基准（旧测试并入训练、自采测试由旧训练池留出），v4 与 v5 数字不可直接比较，且自采子集与公式"
        "召回的置信下界低于门槛。可信的评估来自冻结划分、逐页分组、一次性测试与完整披露，而不是更“好看”的"
        "测试图片。从工程角度看，上传卡死、非凸四角、PDF 校准、门控高置信错误这些问题都不是"
        "“模型精度”问题，但会直接决定系统是否可用；把它们记录成可复现的脚本、测试和文档，比单次提高一个"
        "百分点的指标更有价值。"
    )


def references(doc):
    doc.add_page_break()
    heading(doc, "参考文献", 1)
    refs = [
        "[1] Howard A, Sandler M, Chu G, et al. Searching for MobileNetV3[C]//Proceedings of the IEEE/CVF International Conference on Computer Vision. 2019: 1314-1324.",
        "[2] Bradski G. The OpenCV Library[J]. Dr. Dobb's Journal of Software Tools, 2000.",
        "[3] FastAPI Documentation. https://fastapi.tiangolo.com/ (accessed 2026-11-27).",
        "[4] SCB-Dataset: A Dataset for Detecting Student Classroom Behavior[DS/OL]. GitHub: https://github.com/Whiffe/SCB-dataset (accessed 2026-11-28); 镜像: HuggingFace wintonYF/SCB-Dataset.",
        "[5] Burie J C, Chazalon J, Coustaty M, et al. ICDAR2015 Competition on Smartphone Document Capture and OCR (SmartDoc)[C]//2015 13th International Conference on Document Analysis and Recognition (ICDAR). IEEE, 2015: 1161-1165. 数据: Zenodo record 1230218; 计算版: github.com/jchazalon/smartdoc15-ch1-dataset.",
        "[6] Harley A W, Ufkes A, Derpanis K G. Evaluation of Deep Convolutional Nets for Document Image Classification and Retrieval[C]//ICDAR. 2015.",
        "[7] Marti U V, Bunke H. The IAM-database: an English sentence database for offline handwriting recognition[J]. IJDAR, 2002, 5(1): 39-46.",
        "[8] Deng Y, Kanervisto A, Ling J, et al. Image-to-Markup Generation with Coarse-to-Fine Attention[C]//ICML. 2017.",
    ]
    for ref in refs:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.line_spacing = 1.3
        paragraph.paragraph_format.left_indent = Pt(24)
        paragraph.paragraph_format.first_line_indent = Pt(-24)
        paragraph.paragraph_format.space_after = Pt(3)
        run = paragraph.add_run(ref)
        set_run_font(run, size=10.5)
    body(
        doc,
        "内部资料（本项目仓库，均纳入版本控制）：reports/web_integration.md（网页双分支接入与路由评估）、"
        "reports/quad_localization.md（分载体四角模型与门控审计）、reports/stage_audit.md（阶段门禁审计）、"
        "docs/06-评估与验收方案.md（指标口径与验收清单）、reports/recovery_20261128.md（权重恢复记录）。",
        size=10.5,
    )


def appendix(doc):
    doc.add_page_break()
    heading(doc, "附录 A  关键复现命令", 1)
    commands = [
        ("数据校验", "python scripts/check_manifest.py data/manifests/sample_manifest_v5.csv && python scripts/check_dataset.py data/manifests/sample_manifest_v5.csv"),
        ("集成测试", "python -m pytest tests/unit tests/integration -q"),
        ("v5 划分重建", "python scripts/build_external_nexus_manifest.py && python scripts/build_split_v5.py"),
        ("PPT 分类训练", "python scripts/train_cnn.py --manifest data/manifests/sample_manifest_v5.csv --split data/splits/split_v5.json --carrier ppt --dedupe-inbox --formula-weight 0.5 --no-enhance --exp-id exp-cnn-ppt-v5"),
        ("纸质分类训练", "python scripts/train_paper_classifier.py --manifest data/manifests/paper_content_v5.csv --out runs/paper-cnn-v5-s45 --seed 45"),
        ("测试集一次性评估", "DOCNORM_CARRIER_GATE=runs/carrier-gate-v5-01/screen_gate.pt DOCNORM_PPT_MODEL=runs/exp-cnn-ppt-v5/cnn.pt DOCNORM_PAPER_MODELS=runs/paper-cnn-v5-s45/paper_cnn.pt:runs/paper-cnn-v5-s47/paper_cnn.pt python scripts/eval_final_test.py --manifest data/manifests/sample_manifest_v5.csv --split data/splits/split_v5.json"),
        ("四角模型训练", "python scripts/train_ppt_quad.py --carrier ppt --out runs/quad-ppt-02"),
        ("四角评估", "python scripts/eval_ppt_quad.py --carrier ppt --model runs/quad-ppt-02/quad_ppt.pt"),
        ("路由评估", "python scripts/eval_routed_pipeline.py --manifest data/manifests/sample_manifest_v5.csv --split-file data/splits/split_v5.json"),
        ("OpenCV 调参", "python scripts/tune_rectify_detector.py --carrier ppt"),
    ]
    for name, command in commands:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Pt(12)
        paragraph.paragraph_format.first_line_indent = Pt(0)
        paragraph.paragraph_format.space_after = Pt(3)
        run = paragraph.add_run(name + "：")
        set_run_font(run, size=10.5, bold=True)
        run = paragraph.add_run(command)
        set_run_font(run, size=9.5, east="Menlo", latin="Menlo")

    doc.add_page_break()
    heading(doc, "附录 B  线上模型清单", 1)
    body(
        doc,
        "模型权重不进入 Git，部署时挂载 runs/。完整 SHA-256 见 reports/model_manifest.csv，下表列出角色、路径与指标。"
    )
    table(
        doc,
        ["角色", "路径", "指标"],
        [
            ["载体门控", "runs/carrier-gate-v5-01/screen_gate.pt", "外部 1000/1000；test 门控 69/72（兜底纠正）"],
            ["PPT 分类", "runs/exp-cnn-ppt-v5/cnn.pt", "95.24% / F1 92.93%"],
            ["纸质分类 45", "runs/paper-cnn-v5-s45/paper_cnn.pt", "val 73.33%；集成 76.67%"],
            ["纸质分类 47", "runs/paper-cnn-v5-s47/paper_cnn.pt", "val 73.33%；集成 76.67%"],
            ["PPT 四角", "runs/quad-ppt-02/quad_ppt.pt", "52/52；L2 0.1314"],
            ["纸质四角", "runs/quad-paper-01/quad_ppt.pt", "29/29；L2 0.1347"],
            ["SVM 兜底", "runs/exp-svm-v5/svm.joblib", "72.55% / F1 71.21%"],
        ],
        "表 B1  线上模型清单（v5）",
        widths=[3.0, 8.5, 4.5],
        font_size=9.5,
        align_center=False,
    )
    body(
        doc,
        "可复现性与资源占用：模型权重大小分别为门控 4.4 MB、PPT CNN 6.2 MB、纸质 CNN 各 6.2 MB、SVM 5.0 MB、"
        "四角回归各 4.4 MB；训练时长（容器内 CPU，含数据加载与验证）为 PPT 358 s、单模型 CNN 331 s、SVM 56 s、"
        "载体门控 380 s、纸质 s45/s47 各 678/644 s；四角回归约 8–10 min。推理时延：在 30 张验证图上，"
        "解码后完整处理链路（含门控 TTA、拉正与分类）单张中位 0.05 s、P90 0.06 s；含解码与文件 I/O 的"
        "一次性测试评估 53 张约 60 s（v4 记录）。随机种子固定为 42（跨种子实验 43–47），"
        "依赖版本见 env/Dockerfile（Python 3.11、PyTorch 2.15 CPU、OpenCV 4.14），全部实验的 run.json 记录"
        "环境、参数与耗时。"
    )


def appendix_c(doc):
    doc.add_page_break()
    heading(doc, "附录 C  产出文档索引与在线资源", 1)
    body(
        doc,
        "下表列出本仓库全部过程与交付文档在提交包中的路径，以及在线资源地址，"
        "用于体现项目的工程化与可追溯程度。项目目录内路径以 `代码/` 为基准；"
        "实验报告、成员分工、技术点报告与访问口令位于提交包一级目录。"
    )
    table(
        doc,
        ["路径", "内容"],
        [
            ["README.md / CHANGELOG.md / CONTRIBUTORS.md / LICENSE", "项目总览、变更记录、贡献者与 PR 处理；MIT 代码许可"],
            ["docs/03-架构设计.md", "架构、数据契约与接口"],
            ["docs/04-数据采集与标注规范.md", "采集与标注规范、质量清单"],
            ["docs/05-项目计划与分工.md", "里程碑计划与分工"],
            ["docs/06-评估与验收方案.md", "指标口径、实验矩阵与验收清单"],
            ["docs/07 至 docs/09", "协作流程、环境复现、风险登记"],
            ["docs/10 至 docs/15", "参考调研、部署、运行日志、外部数据、屏幕检测、偏度调研"],
            ["docs/16-开发历程报告.docx/.pdf", "本报告"],
            ["docs/17-合成投影PPT试点.md", "合成数据试点"],
            ["docs/18-小组成员及其分工.docx", "小组分工与量化贡献（本报告第 9 节的完整版）"],
            ["docs/19-技术点报告/（9 份分册）", "按技术点分册：数据、矫正、门控、分类、网页、评估、合成等"],
            ["docs/adr/0001 至 0018", "架构决策记录 18 篇"],
            ["docs/assets、docs/record-img", "留证与过程截图素材"],
            ["reports/final_test_v5.md / .json / 预测 CSV", "v5 测试集一次性评估"],
            ["reports/repro_check_v5.md", "v5 复现核验（逐样本一致）"],
            ["reports/error_cases_v5.md", "错误案例四类归因"],
            ["reports/final_test.md、repro_check.md", "v4 历史评估与复现（对照）"],
            ["reports/web_integration.md、external_control.md、stage_audit.md、cv_oof.md", "v4 历史网页接入、外部对照与 OOF；stage_audit.md 另含 v5 最终审计"],
            ["reports/figures/（含 eval_v5_*）", "全部评估与报告图（300dpi PNG+SVG）"],
            ["reports/run_index.csv、model_manifest.csv", "193 条运行索引；v5 模型 SHA-256 清单"],
            ["data/manifests/、data/splits/、data/annotations/", "清单、冻结划分 v1–v5、标注与排除表"],
            ["data/splits/cv_v5/、data/manifests/cv_v5/", "v5 五折交叉验证折与纸质折清单"],
            ["src/、scripts/、web/、tests/、configs/", "源代码、61 个脚本、网页、104 项测试、配置（含 legacy/v4）"],
        ],
        "表 C1  产出文档索引",
        widths=[7.6, 7.4],
        font_size=9.0,
        align_center=False,
    )
    table(
        doc,
        ["资源", "地址"],
        [
            ["项目仓库（GitHub）", "https://github.com/LosproeOcl/doc-normalizer"],
            ["线上演示", "https://ml-proj.losproeocl.cn（用户名 t06，口令 admin，公开；承诺维护至 2027 年 1 月 1 日）"],
            ["成员 GitHub 主页", "余青阳 github.com/LosproeOcl；张毅卓 github.com/qingwu0731；任万东 github.com/RenWandong；王康琦 github.com/qywkq；蒋翔恒 github.com/Jiang-Xiangheng；张艺萧 github.com/zhangyixiao123；孔泽宇 github.com/jsindkdneksn；李念 github.com/hanss0090"],
            ["自采数据集归档", "GitHub Release：自采 442 张加密压缩包（解压口令见随附 TXT，不随仓库上传）"],
        ],
        "表 C2  在线资源与成员主页",
        widths=[4.2, 10.8],
        font_size=9.5,
        align_center=False,
    )


def appendix_d(doc):
    doc.add_page_break()
    heading(doc, "附录 D  部署、测试、使用与数据集获取（检查者指南）", 1)
    body(
        doc,
        "本附录面向检查者，按“部署 → 测试 → 使用 → 数据集获取”四步组织；所有命令均可在提交包根目录"
        "（或克隆 GitHub 仓库后）直接执行。推荐环境：Ubuntu 22.04 x86_64 + Docker 与 git；"
        "当前线上服务直接运行在 Server1 的 amd64 容器中。"
    )

    heading(doc, "D.1  部署：构建镜像并启动网页服务", 2)
    body(doc, "第一步在服务器项目目录构建 CPU 镜像（x86_64 使用 amd64）：")
    _cmd(doc, "docker build --build-arg INSTALL_CJK_FONTS=0 -f env/Dockerfile -t docnorm:cpu-amd64 .")
    body(doc, "第二步启动网页服务（公开模式，关闭训练集标注与标注检查；挂载仓库目录运行，包含 v5 权重）：")
    _cmd(
        doc,
        "docker run -d --name t06-web --restart unless-stopped -p 127.0.0.1:54312:54312 "
        '-v "$PWD:/app" -w /app -e PYTHONPATH=/app/src:/app -e DOCNORM_PUBLIC_MODE=1 '
        "docnorm:cpu-amd64 uvicorn web.app:app --host 0.0.0.0 --port 54312",
    )
    body(doc, "第三步健康检查：返回 JSON 中 routing_ready=true 表示载体门控、纸质集成与 PPT 分支全部就绪；public_mode=true 表示标注功能已关闭；")
    _cmd(doc, "curl -s http://127.0.0.1:54312/api/health")
    body(
        doc,
        "线上演示地址为 https://ml-proj.losproeocl.cn（Nginx Basic Auth，用户名 t06，口令 admin，"
        "为公开演示口令；承诺维护至 2027 年 1 月 1 日）。检查者也可在 Server1 上直接访问 "
        "127.0.0.1:54312 完成全部功能验收，两者运行同一份代码与模型。",
    )

    heading(doc, "D.2  测试：数据契约、单元/集成与一次性评估复现", 2)
    body(doc, "数据契约校验（清单、排除表、冻结划分与磁盘文件四者一致）：")
    _cmd(doc, "python scripts/check_manifest.py data/manifests/sample_manifest_v5.csv --json")
    _cmd(doc, "python scripts/check_dataset.py data/manifests/sample_manifest_v5.csv --json")
    body(
        doc,
        "单元与集成测试共 104 项（含 v4/v5 数据契约、划分互斥、哈希校验、网页接口契约）。"
        "网页契约测试需要 httpx2，可在容器内执行：",
    )
    _cmd(doc, "docker run --rm -v \"$PWD:/app\" -w /app -e PYTHONPATH=/app/src:/app docnorm:cpu-amd64 sh -c \"pip install -q httpx2 && python -m pytest -q\"")
    body(
        doc,
        "预期输出 104 passed。挂载数据集后，数据契约测试会额外核对 472 张合格样本的文件存在性与哈希；"
        "未挂载数据时该子集自动跳过（requires_dataset 标记），其余测试不受影响。"
    )
    body(doc, "v5 测试集一次性评估复现（与 reports/final_test_v5.md 第 6 节完全相同的命令）：")
    _cmd(
        doc,
        "DOCNORM_CARRIER_GATE=runs/carrier-gate-v5-01/screen_gate.pt "
        "DOCNORM_PPT_MODEL=runs/exp-cnn-ppt-v5/cnn.pt "
        "DOCNORM_PAPER_MODELS=runs/paper-cnn-v5-s45/paper_cnn.pt:runs/paper-cnn-v5-s47/paper_cnn.pt "
        "python scripts/eval_final_test.py --manifest data/manifests/sample_manifest_v5.csv "
        "--split data/splits/split_v5.json --cnn-model runs/exp-cnn-v5/cnn.pt "
        "--classic-model runs/exp-svm-v5/svm.joblib --out reports/final_test_v5_recheck.json",
    )
    body(
        doc,
        "预期结果：准确率 93.06% / 宏 F1 92.65%，混淆矩阵 [[42,0],[5,25]]，与 "
        "reports/final_test_v5.json 及 repro_check_v5.md 逐样本一致（CPU 约 3 分钟）。"
        "该命令只做推理，不改任何文件。",
    )

    heading(doc, "D.3  使用：网页功能与命令行", 2)
    body(
        doc,
        "网页入口提供三类上传方式（手机：拍照 / 相册或文件合并选择；电脑：拍照 / 从文件选择，"
        "无摄像头时自动禁用拍照）。上传后每张图进入横向批量队列，可逐张查看原图、四角、矫正图、"
        "扫描件四个阶段；支持拖拽四角校准、点击放大、按载体手动重试；“扫描件”模式输出白底黑字的"
        "自适应二值化结果；PDF 导出支持当前单张、区间/离散多选与全部队列三种方式，未校准页会被拦截。"
        "分类结果卡展示载体门控概率、命中分支与文字/公式两类概率；门控不确定或分支低置信时自动"
        "尝试另一分支比较置信度，模型缺失时回退 SVM 兜底。",
    )
    body(
        doc,
        "命令行等价能力见附录 A：样本校验（check_manifest/check_dataset）、批量矫正、训练与评估脚本、"
        "路由评估（eval_routed_pipeline.py）。全部脚本支持 --json 输出，退出码 0/2/3 分别表示成功、"
        "输入错误与处理失败。",
    )

    heading(doc, "D.4  数据集获取：Release 加密包与放置路径", 2)
    table(
        doc,
        ["项目", "内容"],
        [
            ["Release", "GitHub Releases 页，tag dataset-self-v5"],
            ["资产名", "dataset-self-442-encrypted.zip"],
            ["显示标签", "自采数据集 442 张（加密）"],
            ["大小", "1,126,447,306 字节（约 1.05 GiB）"],
            ["SHA-256", "f2a5489d3463bedc0cdfece75b7df917d8c6c6b384c3797ee43c5b2280d2e597"],
            ["解压口令", "见随附《项目访问与数据集口令.txt》，不随仓库上传"],
        ],
        "表 D1  自采数据集 Release 信息与获取命令",
        widths=[2.6, 12.0],
        font_size=9.2,
        align_center=False,
    )
    body(doc, "下载与解压命令：")
    _cmd(doc, "gh release download dataset-self-v5 --repo LosproeOcl/doc-normalizer")
    _cmd(doc, "unzip -P <口令> dataset-self-442-encrypted.zip -d data/raw_samples/")
    body(
        doc,
        "解压后得到 01_ppt_text、02_ppt_formula、03_paper_text、04_paper_formula 四个目录，"
        "与仓库内 data/raw_samples/README.md 的目录约定一致；数据集自身的元数据"
        "（拍摄者、设备、场景、光照、分辨率、拍摄时间）已在 data/manifests/sample_manifest_v5.csv "
        "逐张登记，划分见 data/splits/split_v5.json。外部公开数据集（SmartDoc 2015、SCB-Dataset、"
        "Tobacco-3482、IM2LaTeX-100K、IAM）按各自动态下载或从原发布页获取，来源与许可见 "
        "docs/13-外部数据使用说明.md 与 data/manifests/external_aux.csv。",
    )
    body(
        doc,
        "获取数据集后，可重跑的完整证据链依次为：数据契约测试（D.2）→ 5 折分组 CV（data/splits/cv_v5/，"
        "复现 reports/final_test_v5.md 第 7 节）→ 验证集路由评估（eval_routed_pipeline.py，84.31%）→ "
        "测试集一次性评估（D.2 命令，93.06%）。除测试集评估外均不涉及 reports/final_test_v5.json 的口径。",
    )


def _cmd(doc, text):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.left_indent = Pt(12)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.keep_together = True
    run = paragraph.add_run("$ " + text)
    set_run_font(run, size=9.5, east="Menlo", latin="Menlo")


def main():
    doc = setup_document()
    cover(doc)
    abstract(doc)
    toc(doc)
    section_intro(doc)
    section_data(doc)
    section_model_choice(doc)
    section_architecture(doc)
    section_versions(doc)
    section_problems(doc)
    section_screenshots(doc)
    section_status(doc)
    section_team(doc)
    section_conclusion(doc)
    references(doc)
    appendix(doc)
    appendix_c(doc)
    appendix_d(doc)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
