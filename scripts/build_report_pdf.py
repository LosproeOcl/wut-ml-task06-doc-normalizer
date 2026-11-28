"""把开发者报告 DOCX 转成版式可控的 PDF（pandoc HTML + Chrome headless，两遍生成目录）。

第一遍生成 PDF 并定位各章起始页；第二遍把页码写入目录（目录条目来自 DOCX 的
Word TOC 域缓存，DOCX 打开时可自动更新）。pandoc 会丢失 Word 分页符，因此
在 HTML 中显式插入分页标记。

用法：python3 scripts/build_report_pdf.py
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "docs/16-开发历程报告.docx"
PDF = ROOT / "docs/16-开发历程报告.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
table { border-collapse: collapse; border-top: 1.6pt solid #000; border-bottom: 1.6pt solid #000; margin: 8px auto; }
thead th { border-bottom: 0.8pt solid #000 !important; }
th, td { border: none !important; padding: 3px 8px; word-break: break-all; overflow-wrap: anywhere; }
table { width: 100%; max-width: 100%; table-layout: fixed; }
tr { border: none !important; page-break-inside: avoid; break-inside: avoid; }
p, li, td, th { text-align: left !important; }
code, pre { white-space: pre-wrap; word-break: break-all; }
blockquote { margin: 0; padding: 0; border: none; }
.toc p { margin: 0; line-height: 1.2; }
"""

BREAK = '<div style="page-break-before: always; break-before: page;"></div>\n'
HEADINGS = [
    "1 引言", "2 数据集的选择与处理", "3 模型类型的选择",
    "4 模型架构设计与模块排布", "5 模型参数与版本更迭",
    "6 开发过程中遇到的问题与解决方案", "7 不同版本产物与测试截图",
    "8 当前上线状态与阶段审计", "9 小组分工与量化贡献", "10 结论",
    "参考文献", "附录 A 关键复现命令", "附录 B 线上模型清单",
    "附录 C 产出文档索引与在线资源", "附录 D 部署、测试、使用与数据集获取（检查者指南）",
]
TOC_TITLES = [
    "1  引言", "2  数据集的选择与处理", "3  模型类型的选择",
    "4  模型架构设计与模块排布", "5  模型参数与版本更迭",
    "6  开发过程中遇到的问题与解决方案", "7  不同版本产物与测试截图",
    "8  当前上线状态与阶段审计", "9  小组分工与量化贡献", "10  结论",
    "参考文献", "附录 A  关键复现命令", "附录 B  线上模型清单",
    "附录 C  产出文档索引与在线资源", "附录 D  部署、测试、使用与数据集获取",
]


def tokens_pattern(title: str, wrapper: str = "strong") -> re.Pattern:
    tokens = [re.escape(t) for t in title.split()]
    body = r"\s*".join(tokens)
    return re.compile(rf"<p><{wrapper}>{body}</{wrapper}></p>")


def build_html(toc_pages: dict[str, int] | None) -> str:
    tmp = Path(tempfile.mkdtemp(prefix="report_pdf_"))
    html_path = tmp / "report.html"
    subprocess.run(
        ["pandoc", str(DOCX), "-o", str(html_path), "--standalone", "--embed-resources"],
        check=True,
    )
    text = html_path.read_text()
    text = text.replace("</head>", f"<style>{CSS}</style></head>")
    for title in ["摘 要", "目 录"] + HEADINGS:
        matches = list(tokens_pattern(title).finditer(text))
        if matches:
            index = matches[-1].start()
            text = text[:index] + BREAK + text[index:]
    # 目录用紧凑样式
    toc_head = "<p><strong>目 录</strong></p>"
    toc_index = text.find(toc_head)
    intro_index = text.rfind("<p><strong>1 引言</strong></p>")
    if toc_index != -1 and intro_index != -1 and intro_index > toc_index:
        text = text[:intro_index] + "</div>\n" + text[intro_index:]
        insert_at = toc_index + len(toc_head)
        text = text[:insert_at] + '<div class="toc">' + text[insert_at:]
    # 在指定大图前强制分页，避免被上一页表格挤到页底裁切
    for caption in ["图 9", "图 13(b)", "图 13(c)", "图 20"]:
        caption_index = text.find(f"<p>{caption}")
        if caption_index == -1:
            continue
        image_index = text.rfind("<p><img", 0, caption_index)
        if image_index != -1:
            text = text[:image_index] + BREAK + text[image_index:]
    if toc_pages:
        for title in TOC_TITLES:
            pattern = tokens_pattern(title, wrapper="span")
            pattern_plain = re.compile(
                r"<p>" + r"\s*".join(re.escape(t) for t in title.split()) + r"</p>"
            )
            key = re.sub(r"\s+", "", title)
            page = toc_pages.get(key) or toc_pages.get(key + "（检查者指南）")
            if page:
                text = pattern_plain.sub(f"<p>{title}　…… {page}</p>", text, count=1)
    html_path.write_text(text)
    return str(html_path)


def print_pdf(html_path: str, out: Path) -> None:
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={out}", f"file://{html_path}"],
        check=True,
        capture_output=True,
    )


def heading_pages(pdf: Path) -> dict[str, int]:
    doc = pymupdf.open(pdf)
    mapping: dict[str, int] = {}
    for title in HEADINGS:
        target = re.sub(r"\s+", "", title)
        for index, page in enumerate(doc, start=1):
            text = re.sub(r"\s+", "", page.get_text())
            if text.startswith(target):
                mapping[target] = index
                break
    return mapping


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="report_pdf_") as tmp:
        tmp_path = Path(tmp)
        pages: dict[str, int] = {}
        final_pdf = tmp_path / "final.pdf"
        for attempt in range(1, 5):
            html_path = build_html(pages or None)
            candidate = tmp_path / f"pass{attempt}.pdf"
            print_pdf(html_path, candidate)
            actual = heading_pages(candidate)
            final_pdf = candidate
            if actual == pages:
                break
            pages = actual
        PDF.write_bytes(final_pdf.read_bytes())
    print(f"saved {PDF} ({PDF.stat().st_size} bytes), toc entries={len(pages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
