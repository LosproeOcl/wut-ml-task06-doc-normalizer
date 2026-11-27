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
OUTPUT = ROOT / "docs/16-开发者视角开发历程报告.docx"

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
    run = paragraph.add_run()
    run.add_picture(str(ASSETS / filename), width=Cm(width_cm))
    caption(doc, cap)


def shade(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def table(doc, headers, rows, cap, widths=None, font_size=10.5, align_center=True):
    caption(doc, cap, kind="表")
    table_obj = doc.add_table(rows=1, cols=len(headers))
    table_obj.style = "Table Grid"
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
        shade(header_cells[index], "DCE8F7")
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
    if widths:
        for row in table_obj.rows:
            for index, width in enumerate(widths):
                row.cells[index].width = Cm(width)
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
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.first_line_indent = Pt(0)
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = 'TOC \\o "1-3" \\h \\z \\u'
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instruction)
    run._r.append(end)


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

    # 打开文档时提示更新目录
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

    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("——开发者视角的顺序开发历程报告")
    set_run_font(run, size=15, bold=False, east=HEAD_FONT)

    for _ in range(4):
        doc.add_paragraph()

    for text, size in [
        ("武汉理工大学《机器学习》课程实践", 14),
        ("第六组 · Task 06", 12),
        ("报告版本：v1.0", 11),
        ("2026 年 11 月 27 日", 11),
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
        "本报告按实际开发顺序记录斜拍文档规范化系统从数据构建到模型上线的完整过程。"
        "系统面向投影幕布、黑板板书和纸质笔记等非正面拍摄场景，目标是把一张斜拍文档转换为正面扫描件，"
        "并判断页面内容属于文字还是公式。开发过程中，数据集由 340 张扩展到 442 张合格样本，"
        "划分冻结为训练 338 张、验证 51 张、测试 53 张；模型从传统特征与 SVM 基线，发展到"
        "“载体门控 + PPT/纸质双分支”的轻量深度模型，再演进到“OpenCV 分类拉正 + 学习四角显示拉正”的双路径结构。"
    )
    body(
        doc,
        "当前线上链路在验证集上达到 86.27% / 宏 F1 86.19%，其中 PPT 分支 95.24%、纸质分支 80.00%。"
        "报告重点说明四类取舍：为什么选择轻量 CNN 而不是更大的骨干网络；为什么把载体门控与内容分类拆开；"
        "为什么学习四角模型定位更准却不能直接替换分类器输入；以及为什么最终采用 OpenCV 与学习四角解耦的双路径拉正。"
        "同时记录了数据泄漏、标签修正、公式召回偏低、上传卡死、非凸四角、门控高置信误判等问题的发现与解决过程，"
        "但 2026-11-27 测试集一次性评估仅为 67.92% / 宏 F1 67.92%，未达 85% 验收线，M3 未通过、M4 阻塞；报告如实记录这一结果与错误分析。"
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
    add_toc(doc)
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("（目录页码由 Word 自动生成；若未显示，右键“更新域”即可。）")
    set_run_font(run, size=9, color=(130, 130, 130))
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
        "因此开发路线不是“一次性设计一个复杂模型”，而是按“先跑通、再拆解、再替换、最后解耦”的顺序迭代："
        "先用传统特征建立可复现基线，再用 MobileNetV3 做迁移学习；发现单一模型难以同时处理幕布与纸质稿后，"
        "引入载体门控和双分支；发现标注四角可以训练定位模型后，又尝试把定位与分类解耦，"
        "最终形成当前的双路径拉正结构。"
    )

    heading(doc, "1.2  报告结构", 2)
    body(
        doc,
        "第 2 章说明数据集的选择、形状、清洗和标注；第 3 章说明模型类型的选择依据；"
        "第 4 章给出最终模型架构与各模块的排布；第 5 章按版本记录参数更迭、指标变化和上线取舍；"
        "第 6 章归纳开发中遇到的问题与解决方案；第 7 章结合版本截图说明产物演进；"
        "第 8 章给出当前上线状态与阶段审计结论；第 9 章总结可复用的经验。"
    )


def section_data(doc):
    heading(doc, "2  数据集的选择与处理", 1)
    heading(doc, "2.1  数据来源与采集口径", 2)
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
        "冻结划分 split_v4 的计数为训练 338、验证 51、测试 53，val/test 与 v3 保持同一批文档页。"
        "各集合的内容与载体分布如表 1 所示。"
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
        "表 1  合格样本的集合、内容与载体分布",
        widths=[2.2, 2.4, 2.4, 2.4, 3.2, 3.2],
    )
    body(
        doc,
        "排除表的 36 条记录中，personal_info 25 条、non_course_document 4 条、unlabeled 3 条、"
        "low_resolution 3 条、missing_file 1 条。分辨率范围为 1080×784 至 6120×4596，"
        "常见尺寸包括 4032×3024、3072×4096、4096×3072、1279×1706 和 5712×4284。"
        "分辨率差异较大，因此训练与推理统一先按长边缩放，再进入检测或分类。"
    )
    figure(doc, "dataset_examples.png", "图 1  四类样本示例（PPT 文字/公式为原始拍摄，纸质/板书示例带人工四角）", 15.2)

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
    figure(doc, "annotation_examples.png", "图 2  人工四角标注检查示例（红框为保存的四角，黄点为顶点顺序）", 15.2)
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
        "MobileNetV3-Large 224 为 78.4%，EfficientNet-B0 为 74.5%，输入从 224 提高到 320 反而降到 78.4%。"
        "因此最终把 MobileNetV3-Small + 224 作为主骨干。"
    )
    body(
        doc,
        "外部预训练权重也做过零样本测试：在 340 张真实数据上仅 54.41%，formula 召回 0%–2.58%，"
        "等于多数类基线。这说明外部裁剪公式图与手机整页拍摄之间存在明显域差，外部数据只能用于辅助训练或"
        "初始化，不能直接部署。"
    )

    heading(doc, "3.3  载体门控与双分支", 2)
    body(
        doc,
        "载体门控沿用 MobileNetV3-Small 二分类结构，输入 160×160，输出 other/screen 两类概率。"
        "训练清单混合 SCB 屏幕、自采 PPT/paper 与外部 A4 数据，共 2,236 张训练、1,000 张外部验证；"
        "自采验证 51 张只做最终检查。门控在外部验证 1,000/1,000、自采验证 51/51 全对，"
        "但训练集审计 338 张中有 2 张错误，说明“高分”不等于“没有难例”。"
    )
    body(
        doc,
        "门控之后是两条内容分支。PPT 分支使用单模型 MobileNetV3-Small；纸质分支使用 3 个种子的 CNN 集成，"
        "对三个 softmax 概率取平均。纸质稿的外部数据域差更大，单模型在 30 张纸质验证上只有 70%–86.67%，"
        "集成可以降低单次训练波动。两条分支都缺失时回退传统 SVM，保证网页在模型文件缺失时仍能分析。"
    )

    heading(doc, "3.4  四角定位模型：OpenCV 与学习回归", 2)
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
    heading(doc, "4  模型架构的排布", 1)
    heading(doc, "4.1  总体架构", 2)
    body(
        doc,
        "当前线上架构可以概括为“一个门控、两条分类分支、两条拉正路径、一个兜底”。"
        "上传图像先做 EXIF 方向校正和长边限制，再进入载体门控；门控输出 PPT 或纸质，"
        "分别选择 OpenCV 分类拉正参数和内容分类模型；学习四角模型独立运行，只负责显示、扫描件和 PDF 的拉正。"
        "两条路径在用户手动应用四角或手动切换载体时可以重新汇合。总体结构如图 3 所示。"
    )
    figure(doc, "architecture.png", "图 3  当前线上模型与双路径拉正结构", 15.4)

    heading(doc, "4.2  载体门控", 2)
    body(
        doc,
        "门控输入为上传原图（长边限制 2,000 像素后缩放至 160×160），默认在 -12°、0°、+12° 三个旋转角度上"
        "做 TTA，对三个 softmax 输出取平均，阈值设为 0.30：P(screen) ≥ 0.30 判为 PPT，否则判为纸质。"
        "阈值 0.30 是空间偏度实验的结果：合成 30°/40° 条件下，门控 TTA + 0.3 把完整链路从 71.4% 提升到 81.0%。"
        "门控只决定分支，不直接决定内容标签。"
    )

    heading(doc, "4.3  内容分类分支", 2)
    body(
        doc,
        "PPT 分支使用 exp-cnn-ppt-dedup-fw：MobileNetV3-Small，输入 224×224，按幻灯片去重后训练 152 张、"
        "验证 21 张，公式类权重 0.5。验证集准确率 95.24%，宏 F1 92.93%。"
        "纸质分支使用 paper-cnn-extctl-01/43/44 三个种子，输入 224×224，训练 894 张、验证 30 张，"
        "三个模型概率平均后验证 80.00%。SVM 兜底使用 1,836 维传统特征，验证 76.47%。"
    )
    table(
        doc,
        ["模块", "骨干/结构", "输入", "训练/验证", "验证指标"],
        [
            ["载体门控", "MobileNetV3-Small 二分类", "160×160", "2,236 / 1,000", "外部 1000/1000；自采 51/51"],
            ["PPT 分类", "MobileNetV3-Small", "224×224", "152 / 21", "95.24% / F1 92.93%"],
            ["纸质分类", "3×MobileNetV3-Small 集成", "224×224", "894 / 30", "80.00%"],
            ["SVM 兜底", "1,836 维特征 + SVM", "拉正图", "236 / 51", "76.47% / F1 75.71%"],
        ],
        "表 2  线上内容分支与兜底模型",
        widths=[2.5, 5.0, 2.3, 2.7, 4.5],
    )

    heading(doc, "4.4  双路径拉正", 2)
    body(
        doc,
        "双路径是本次开发最重要的结构决策。分类路径继续使用 OpenCV 拉正：PPT/纸质均 Canny 50/150（PPT 90/250 仅为检测实验），"
        "面积门槛 0.15–0.98，输出长边 1,600。显示/导出路径使用学习四角：PPT quad-ppt-02、纸质 quad-paper-01，"
        "预测四角后做透视变换，生成矫正图和扫描件。两条路径共享同一张原图和同一套人工四角；"
        "用户手动应用四角后，两条路径都切换到人工四角。"
    )
    body(
        doc,
        "这样做不是“多此一举”，而是因为分类器对拉正分布非常敏感。实测把学习四角直接作为分类输入时，"
        "全链路从 86.27% 降到 82.35%；只把学习四角作为检测失败兜底也降到 84.31%；"
        "按学习四角重训内容模型则降到 PPT 71.43%、纸质 70.00%。定位精度提高并不自动带来分类提高。"
        "把两条路径拆开后，分类器保持训练时的 OpenCV 分布，显示/PDF 则获得更完整的幕布四角，"
        "分类指标不下降。"
    )
    table(
        doc,
        ["路径", "拉正方式", "参数/模型", "用途"],
        [
            ["分类路径", "OpenCV 规则检测", "PPT 90/250；纸质 50/150", "决定 text/formula，保持 86.27%"],
            ["显示/导出", "学习四角回归", "quad-ppt-02；quad-paper-01", "矫正图、扫描件、PDF"],
            ["人工覆盖", "人工四角", "manual_corners / 用户点选", "两条路径统一切换"],
        ],
        "表 3  双路径拉正的分工",
        widths=[2.6, 4.0, 5.2, 5.0],
    )

    heading(doc, "4.5  部署结构", 2)
    body(
        doc,
        "服务使用 FastAPI[3] + Uvicorn，绑定 127.0.0.1:54312，Docker 镜像 docnorm:cpu-arm64 以 CPU 运行。"
        "模型权重不进入 Git，部署时挂载 runs/ 目录；健康检查 /api/health 返回门控、PPT/纸质模型、"
        "SVM、学习四角、quad_policy、quad_display 与 routing_ready。分析接口在线程池中执行，"
        "并发上限 2，上传长边限制 2,000 像素，解码像素上限 6,000 万，避免大图拖死整机。"
    )


def section_versions(doc):
    heading(doc, "5  模型参数与版本更迭", 1)
    heading(doc, "5.1  训练与评估配置", 2)
    body(
        doc,
        "所有版本使用 split_v4 的固定划分，随机种子默认 42；训练只在训练集上更新参数，验证集用于早停和模型选择，"
        "测试集不参与调参。CNN 训练默认冻结骨干 3 轮，分类头学习率 1e-3，解冻后全模型学习率 1e-4，"
        "batch 32，输入 224，增强为默认的随机裁剪、旋转、透视和颜色扰动。PPT 专用模型额外使用--dedupe-inbox"
        " 按幻灯片去重，并把公式类权重乘 0.5；纸质集成使用种子 42/43/44。"
    )
    table(
        doc,
        ["项目", "PPT 分类", "纸质分类", "载体门控", "四角回归"],
        [
            ["骨干", "MobileNetV3-Small", "MobileNetV3-Small", "MobileNetV3-Small", "MobileNetV3-Small"],
            ["输入", "224×224", "224×224", "160×160", "224×224"],
            ["训练/验证", "152 / 21", "894 / 30", "2,236 / 1,000", "153 / 52（PPT）；104 / 29（纸质）"],
            ["轮数/早停", "15 / 5", "6 / 2", "3", "30 / 6"],
            ["关键参数", "公式权重 0.5；按幻灯片去重", "3 种子集成；平衡类权重", "TTA ±12°；阈值 0.3", "SmoothL1；冻结 3 轮"],
            ["验证结果", "95.24% / F1 92.93%", "80.00%", "外部 1000/1000；自采 51/51", "L2 0.1314 / 0.1347"],
        ],
        "表 4  当前主要模型的训练配置",
        widths=[2.6, 4.3, 4.0, 3.0, 4.2],
        font_size=9.5,
    )

    heading(doc, "5.2  版本演进顺序", 2)
    body(
        doc,
        "版本演进不是简单的“指标越高越好”，而是不断修正评估口径、拆分任务和确认上线边界的过程。"
        "表 5 按时间顺序列出关键版本、参数变化和最终决策。"
    )
    table(
        doc,
        ["版本", "数据/时间", "模型与关键参数", "验证结果", "上线决策"],
        [
            ["V0", "v3 236/51/53", "传统特征 1,836 维 + SVM/RF", "SVM 76.47%；RF 72.55%", "保留为兜底"],
            ["V1", "v3", "MobileNetV3-Small 224，未增强", "80.39% / F1 79.03%", "替换传统主模型"],
            ["V2", "v3，修正 11 张标签", "载体门控 + 纸质 3 模型集成 + PPT CNN", "旧标签 88.24%；修正后 84.31%", "接入双分支，旧指标不再作为当前值"],
            ["V3", "v4 338/51/53", "PPT 去重 + 公式权重 0.5（dedup-fw）", "PPT 95.24%；全链路 86.27%", "替换 PPT 分支，当前基线"],
            ["V3.1", "v4", "从旧模型热启动（warm-01）", "95.24% / F1 91.43%", "不替换：F1 略低"],
            ["V4", "v4 + 338 四角", "OpenCV 调参实验；分类回退 PPT/纸质 50/150，90/250 仅检测", "PPT 检测 84.62%；全链路 86.27%", "分类保持 50/150"],
            ["V5", "v4", "学习四角 quad-ppt-02 / quad-paper-01", "52/52、29/29；L2 0.1314/0.1347", "只用于显示/建议，不直接分类"],
            ["V5.1", "v4", "学习四角优先/兜底/重训内容模型", "82.35% / 84.31%；重训 71.43%/70.00%", "全部否决"],
            ["V5.2", "当前", "OpenCV 分类 + 学习四角显示 + 手动重试", "86.27% / F1 86.19%", "当前线上版本"],
        ],
        "表 5  版本演进与上线取舍",
        widths=[1.4, 3.0, 7.0, 4.6, 4.2],
        font_size=9.0,
    )
    figure(doc, "metrics.png", "图 4  验证集 51 张上的版本与分支准确率对比", 14.5)
    body(
        doc,
        "需要特别说明 88.24% 与 84.31% 的关系。88.24% 是标签修正前的旧口径：当时 11 张样本的公式/文字标签"
        "与归档路径不一致。人工复核后，旧模型在修正标签上降到 84.31%，这不是模型退化，而是评估口径变正确了。"
        "后续所有版本都在修正标签上比较，因此当前 86.27% 不能与旧 88.24% 直接拼接。"
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
        "提高到 86.21%，但全链路从 86.27% 降到 84.31%，因为 formula_14 被错误检出并拉正后判成 text。"
        "因此“检出率更高”不等于“端到端更好”。"
    )
    body(
        doc,
        "（5）学习四角。PPT 模型 52/52 覆盖、L2 0.1314；纸质 29/29、L2 0.1347。"
        "但直接替换分类输入时全链路降到 82.35%，按学习四角重训内容模型又因 152 张样本过拟合降到 71.43%"
        "（PPT）和 70.00%（纸质 seed 42）。最终只把学习四角用于显示/PDF，分类器继续看 OpenCV 视图。"
    )

    heading(doc, "5.4  上线取舍与原因", 2)
    body(
        doc,
        "取舍一：为什么当前用 86.27% 而不是旧 88.24%？因为 88.24% 建立在未修正的标签上，"
        "修正后旧模型只有 84.31%；当前 86.27% 与同一口径可比，且 PPT 分支从 90.48% 提升到 95.24%。"
    )
    body(
        doc,
        "取舍二：为什么用 dedup-fw 而不是热启动？两者 PPT 准确率都是 95.24%，但热启动的宏 F1 为 91.43%，"
        "低于 dedup-fw 的 92.93%，说明公式类更不稳；在没有额外收益的情况下选择更平衡的模型。"
    )
    body(
        doc,
        "取舍三：为什么学习四角不做分类主定位？定位 L2 更小，但分类器对拉正后的尺度、裁切和透视变化敏感；"
        "重训又受限于 152/894 张样本和分布差异。把定位与分类解耦，既保留学习四角的显示收益，"
        "又不牺牲分类指标。"
    )
    body(
        doc,
        "取舍四：为什么门控不做自动跨分支切换？实测按“谁置信度高用谁”会把 4 张 PPT 误切到纸质，"
        "全链路降到 80.39%。最终只做 uncertain 标记和手动“按 PPT/纸质重试”，自动指标保持 86.27%。"
    )
    figure(doc, "confusion.png", "图 5  当前路由链路验证集混淆矩阵（文字/公式）", 9.5)
    body(
        doc,
        "单次 21 张验证集不足以支撑 PPT 分支选择，因此补充了 5 折分组交叉验证："
        "按 doc_page_id 分组、按载体×内容分层，每折 200 训练组 / 50 验证组，PPT 与纸质各 5 折 × 3 种子。"
        "PPT 折内均值 70.44% ± 8.24，纸质 88.90% ± 5.29；OOF 分别为 71.71% 和 90.23%。"
        "这说明原验证集 PPT 95.24% 是单点峰值，不能作为稳定泛化指标；纸质 OOF 虽高，但测试只有 72.4%，域差明显。"
        "OOF 阈值把 PPT 提到 75.12%、纸质 90.98%，但原验证集检查降到 84.31%，因此没有直接采用；"
        "用该阈值对测试集仅作诊断时为 69.81%，仍远低于 85%。详见 reports/cv_oof.md。"
    )


def section_problems(doc):
    heading(doc, "6  开发过程中遇到的问题与解决方案", 1)
    body(
        doc,
        "项目遇到的问题大致分为数据、模型、工程和流程四类。表 6 汇总了影响较大的问题、解决方式和验证证据，"
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
            ["模型", "学习四角拉正改变分类输入分布", "分类/显示双路径；不直接替换分类", "82.35%→86.27%"],
            ["工程", "上传大图点击后卡死", "同步端点线程池；并发闸门；像素上限；JPEG 缩放解码", "健康检查 29 ms；上传分析正常"],
            ["工程", "手工四角被误判凹四边形", "凸包规范化；前端自动排序；重选按钮", "任意顺序保存成功"],
            ["工程", "多页 PDF 未逐页校准", "逐页校准门禁；待校准/已校准状态", "导出前拦截未校准页"],
            ["流程", "模型版本与文档数值漂移", "运行日志、模型清单、阶段审计", "102+1 项测试；审计报告"],
        ],
        "表 6  主要问题、解决方案与验证证据",
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
        "旋转 TTA + 0.3 阈值在合成 30°/40° 上把完整链路从 71.4% 提升到 81.0%，但仍有高置信错误"
        "（如 IMG_6178，P(ppt)=0.082）。这类错误无法靠阈值修复，最终用结果卡的手动弹体重试兜底。"
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
        "开发后期最大的风险不是模型，而是“文档写的和代码跑的不一致”。例如 split_v3 与 split_v4、"
        "88.24% 与 84.31%、旧 PPT 模型与 dedup-fw 同时出现在不同文档里。为此增加了运行日志 run.json、"
        "reports/run_index.csv、reports/model_manifest.csv，并在阶段审计中逐项核对数据、模型、网页、测试和文档。"
        "当前审计结论是 M2 通过、M3 未通过、M4 阻塞；详细清单见 reports/stage_audit.md[11]。"
    )


def section_screenshots(doc):
    heading(doc, "7  不同版本产物与测试截图", 1)
    body(
        doc,
        "仓库 docs/record-img/ 保存了开发过程中不同阶段的网页截图，reports/annotation_examples/ 保存了人工四角"
        "目视检查图。本节选取其中隐私风险较低的 PPT/文字页截图，说明界面和结果产物的演进；涉及个人信息的纸质"
        "样本不放入报告。"
    )
    heading(doc, "7.1  早期批量队列与单张结果页", 2)
    body(
        doc,
        "图 6 是较早版本的 PPT 文字页结果页。页面已经具备批量队列、逐张完成状态、原图/矫正图/扫描件三栏、"
        "四角拖动、“应用四角”、PDF 模式与导出按钮。该版本还没有载体徽标、双路径显示切换和手动载体重试；"
        "这些是后续版本补充的。"
    )
    figure(doc, "record_results.png", "图 6  早期版本的批量队列与结果页（左：PPT 文字；右：纸质文字）", 15.0)
    body(
        doc,
        "从截图可以看到，早期结果的矫正图与扫描件已经能把幕布内容拉正，但界面信息密度较高，"
        "结果卡只显示标签和概率，没有解释载体/分支，也没有显示“分类拉正”和“显示拉正”的区别。"
        "后续版本把载体、分支、不确定标记、显示切换拆成独立信息块，减少误读。"
    )

    heading(doc, "7.2  偏度样本的失败与修正", 2)
    body(
        doc,
        "图 7 是空间偏度样本的测试截图，文件名直接标注“偏度-不达预期”。该样本在早期链路中门控或定位不稳定，"
        "说明正面样本的高准确率不能外推到斜拍场景。后续用合成 0°–40° 压力测试定位瓶颈，"
        "引入门控旋转 TTA 与 0.3 阈值，并用学习四角提供失败建议，才把偏度场景的完整链路从 71.4% 提升到 81.0%。"
    )
    figure(doc, "record_skew.png", "图 7  偏度样本测试截图（早期版本，标注为“不达预期”）", 13.0)

    heading(doc, "7.3  当前双路径与显示切换", 2)
    body(
        doc,
        "当前版本在结果卡新增“拉正显示：学习四角 / OpenCV”切换。切换只改变矫正图、扫描件和 PDF 的视图，"
        "分类结果仍由 OpenCV 视图决定；OpenCV 未检出时切到 OpenCV 视图会显示原图，并提示原因。"
        "由于当前截图素材来自早期版本，本节用表 7 记录当前接口和文件证据，截图可在浏览器打开本机服务后补充。"
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
        "表 7  当前双路径接口与产物证据",
        widths=[4.0, 11.0],
        align_center=False,
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
        "PPT/纸质分支；显示链路为学习四角拉正。验证集 51 张的指标为 86.27% / 宏 F1 86.19%，"
        "PPT 分支 95.24%，纸质分支 80.00%，拉正成功 43/51。"
    )
    table(
        doc,
        ["指标", "数值", "说明"],
        [
            ["全链路准确率", "86.27%（44/51）", "验证集；测试集见 8.2"],
            ["宏平均 F1", "86.19%", "文字/公式两类"],
            ["PPT 分支", "95.24%（20/21）", "exp-cnn-ppt-dedup-fw"],
            ["纸质分支", "80.00%（24/30）", "3 模型集成"],
            ["文字召回", "85.71%（24/28）", "当前混淆矩阵"],
            ["公式召回", "86.96%（20/23）", "当前混淆矩阵"],
            ["自动拉正", "43/51", "PPT 19/21；纸质 24/30"],
        ],
        "表 8  当前验证集指标",
        widths=[4.5, 4.5, 6.0],
        align_center=False,
    )
    heading(doc, "8.2  测试集一次性评估", 2)
    body(
        doc,
        "在冻结当前模型与配置后，2026-11-27 对 53 张测试集执行了一次性最终评估。当前链路准确率 67.92% / "
        "宏 F1 67.92%，95% 置信区间 54.72%–81.13%；其中纸质 72.41%、PPT 62.50%。单模型 CNN 为 66.04%，"
        "传统 SVM 为 67.92%，McNemar 检验 p=1.00。测试集未达到 85% 验收线，M3 未通过。"
    )
    table(
        doc,
        ["方法", "准确率", "宏 F1", "说明"],
        [
            ["当前双分支路由", "67.92%（36/53）", "67.92%", "95% CI 54.72%–81.13%"],
            ["单模型 CNN", "66.04%（35/53）", "63.86%", "exp-cnn-05"],
            ["传统 SVM", "67.92%（36/53）", "67.92%", "相同混淆矩阵"],
        ],
        "表 9  测试集一次性评估结果",
        widths=[4.0, 4.5, 3.0, 4.5],
        align_center=False,
    )
    body(
        doc,
        "5 折分组 CV 也给出相同方向：PPT 折内 70.44% ± 8.24、纸质 88.90% ± 5.29，原验证集 95.24% 无法复现。"
        "17 张错误中，至少 5 张 PPT 文字页是明确模型错误；多张纸质笔记同时含大量公式与文字，标签口径存在歧义。"
        "测试集不得再用于调参；应先做双人盲审标签，明确文字/公式边界。若确认标签需要修改，应建立新的测试版本并记录，"
        "而不是直接修改当前测试集。错误案例见 reports/final_test.md 与 reports/figures/test_errors.jpg。"
    )
    heading(doc, "8.3  阶段审计结论", 2)
    body(
        doc,
        "阶段审计的结论是：M2 基线可用通过；M3 测试集评估未通过；M4 交付冻结阻塞。"
        "测试集 67.92% 低于 85%，且置信区间上限 81.13%，不能以样本量解释为达标。"
        "在解决测试标签口径与模型泛化之前，不应签署 M4。"
    )
    body(
        doc,
        "M4 前仍需完成：测试集准确率 ≥85% 且附 95% 置信区间、混淆矩阵、分类别召回和按载体分组；"
        "补齐主对比表（传统/CNN/拉正前后/增强消融）、F3 拉正前后与 F11 网页截图等图表；"
        "新增 reports/repro_check.md 并由非模型作者完成双架构复现核验。"
    )

    heading(doc, "8.4  残余风险", 2)
    body(
        doc,
        "测试集只有 53 张，单样本约 1.9 个百分点，不能以微小差异断言方法优劣；C-03 零样本诊断曾在包含测试集的 "
        "340 张数据上运行过，虽然未用于模型选择，但需要在报告中披露；门控训练集审计仍有 2/338 错误，"
        "高置信错误依赖手动重试；PPT 分类器训练与网页分类均已使用 50/150，90/250 仅保留检测实验。"
        "测试集标签口径与域泛化是当前最大风险，已在 reports/stage_audit.md 中登记。"
    )


def section_conclusion(doc):
    heading(doc, "9  结论", 1)
    body(
        doc,
        "这次开发给出的最重要经验是：在数据规模有限、部署资源有限的课程项目中，模型结构的选择必须和"
        "数据质量、评估口径、前端交互一起考虑。传统基线提供了可复现的起点，MobileNetV3-Small 在 CPU 上"
        "取得了可用的性价比；载体门控把“幕布/纸质”这个混杂因素拆开，双分支让各载体使用更适合的模型；"
        "四角标注不仅改善了训练回退，还让我们发现“定位更准”不等于“分类更好”；最终的双路径拉正把"
        "定位与分类解耦，在验证集 86.27% 的前提下，让显示/PDF 用上了更好的四角；但测试集一次性评估只有 67.92%，"
        "说明验证集与测试集的标签口径/域分布仍有明显差距，这是下一步必须解决的问题。"
    )
    body(
        doc,
        "从工程角度看，上传卡死、非凸四角、PDF 校准、门控高置信错误这些问题都不是“模型精度”问题，"
        "但会直接决定系统是否可用。把它们记录成可复现的脚本、测试和文档，比单次提高一个百分点的指标更有价值。"
        "下一步应在冻结清单完成后运行一次测试集评估，补齐置信区间、主对比表和复现核验，再进入交付阶段。"
    )


def references(doc):
    heading(doc, "参考文献", 1)
    refs = [
        "[1] Howard A, Sandler M, Chu G, et al. Searching for MobileNetV3[C]//Proceedings of the IEEE/CVF International Conference on Computer Vision. 2019: 1314-1324.",
        "[2] Bradski G. The OpenCV Library[J]. Dr. Dobb's Journal of Software Tools, 2000.",
        "[3] FastAPI Documentation. https://fastapi.tiangolo.com/ (accessed 2026-11-27).",
        "[4] SCB-Dataset: A Dataset for Student Classroom Behavior Detection. 公开数据集说明.",
        "[5] SmartDoc 2015 Competition. ICDAR 2015 Document Analysis Competition.",
        "[6] Harley A W, Ufkes A, Derpanis K G. Evaluation of Deep Convolutional Nets for Document Image Classification and Retrieval[C]//ICDAR. 2015.",
        "[7] Marti U V, Bunke H. The IAM-database: an English sentence database for offline handwriting recognition[J]. IJDAR, 2002, 5(1): 39-46.",
        "[8] Deng Y, Kanervisto A, Ling J, et al. Image-to-Markup Generation with Coarse-to-Fine Attention[C]//ICML. 2017.",
        "[9] 本项目. reports/web_integration.md：网页双分支接入与验证集路由评估. 2026-11-27.",
        "[10] 本项目. reports/quad_localization.md：分载体四角模型、端到端接入与门控审计. 2026-11-27.",
        "[11] 本项目. reports/stage_audit.md：阶段门禁审计. 2026-11-27.",
        "[12] 本项目. docs/06-评估与验收方案.md：指标口径、实验矩阵与验收清单. 2026-11-27.",
    ]
    for ref in refs:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.line_spacing = 1.3
        paragraph.paragraph_format.left_indent = Pt(24)
        paragraph.paragraph_format.first_line_indent = Pt(-24)
        paragraph.paragraph_format.space_after = Pt(3)
        run = paragraph.add_run(ref)
        set_run_font(run, size=10.5)


def appendix(doc):
    heading(doc, "附录 A  关键复现命令", 1)
    commands = [
        ("数据校验", "python scripts/check_manifest.py && python scripts/check_dataset.py"),
        ("集成测试", "python -m pytest tests/unit tests/integration -q"),
        ("PPT 分类训练", "python scripts/train_cnn.py --carrier ppt --dedupe-inbox --formula-weight 0.5 --no-enhance --exp-id exp-cnn-ppt-dedup-fw"),
        ("纸质分类训练", "python scripts/train_paper_classifier.py --manifest data/manifests/paper_content_extctl.csv --out runs/paper-cnn-extctl-01 --seed 42"),
        ("四角模型训练", "python scripts/train_ppt_quad.py --carrier ppt --out runs/quad-ppt-02"),
        ("四角评估", "python scripts/eval_ppt_quad.py --carrier ppt --model runs/quad-ppt-02/quad_ppt.pt"),
        ("路由评估", "python scripts/eval_routed_pipeline.py"),
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

    heading(doc, "附录 B  线上模型清单", 1)
    body(
        doc,
        "模型权重不进入 Git，部署时挂载 runs/。完整 SHA-256 见 reports/model_manifest.csv，下表列出角色、路径与指标。"
    )
    table(
        doc,
        ["角色", "路径", "指标"],
        [
            ["载体门控", "runs/carrier-gate-01/screen_gate.pt", "外部 1000/1000；自采 51/51"],
            ["PPT 分类", "runs/exp-cnn-ppt-dedup-fw/cnn.pt", "95.24% / F1 92.93%"],
            ["纸质分类 01", "runs/paper-cnn-extctl-01/paper_cnn.pt", "80.00% / F1 78.47%"],
            ["纸质分类 43", "runs/paper-cnn-extctl-43/paper_cnn.pt", "86.67% / F1 85.00%"],
            ["纸质分类 44", "runs/paper-cnn-extctl-44/paper_cnn.pt", "83.33% / F1 81.68%"],
            ["PPT 四角", "runs/quad-ppt-02/quad_ppt.pt", "52/52；L2 0.1314"],
            ["纸质四角", "runs/quad-paper-01/quad_ppt.pt", "29/29；L2 0.1347"],
            ["SVM 兜底", "runs/exp-20261126-08/svm.joblib", "76.47% / F1 75.71%"],
        ],
        "表 B1  线上模型清单",
        widths=[3.0, 8.5, 4.5],
        font_size=9.5,
        align_center=False,
    )


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
    section_conclusion(doc)
    references(doc)
    appendix(doc)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
