"""把开发者报告 DOCX 转成版式可控的 PDF（pandoc HTML + Chrome headless）。

pandoc 会丢失 Word 的分页符，并可能把缩进段落转成 blockquote。本脚本在 HTML
中显式插入分页标记，并统一三线表/代码块样式，使 PDF 与 DOCX 的分页一致。

用法：python3 scripts/build_report_pdf.py
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "docs/16-开发者视角开发历程报告.docx"
PDF = ROOT / "docs/16-开发者视角开发历程报告.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
table { border-collapse: collapse; border-top: 1.6pt solid #000; border-bottom: 1.6pt solid #000; margin: 8px auto; }
thead th { border-bottom: 0.8pt solid #000 !important; }
th, td { border: none !important; padding: 3px 8px; }
tr { border: none !important; page-break-inside: avoid; break-inside: avoid; }
p, li, td, th { text-align: left !important; }
code, pre { white-space: pre-wrap; word-break: break-all; }
blockquote { margin: 0; padding: 0; border: none; }
.toc p { margin: 0; line-height: 1.2; }
"""

BREAK = '<div style="page-break-before: always; break-before: page;"></div>\n'
HEADINGS = [
    "摘 要", "目 录",
    "1 引言", "2 数据集的选择与处理", "3 模型类型的选择",
    "4 模型架构设计与模块排布", "5 模型参数与版本更迭",
    "6 开发过程中遇到的问题与解决方案", "7 不同版本产物与测试截图",
    "8 当前上线状态与阶段审计", "9 小组分工与量化贡献", "10 结论",
    "参考文献", "附录 A 关键复现命令", "附录 B 线上模型清单",
    "附录 C 产出文档索引与在线资源", "附录 D 部署、测试、使用与数据集获取（检查者指南）",
]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="report_pdf_"))
    html = tmp / "report.html"
    pdf = tmp / "report.pdf"
    subprocess.run(
        ["pandoc", str(DOCX), "-o", str(html), "--standalone", "--embed-resources"],
        check=True,
    )
    text = html.read_text()
    text = text.replace("</head>", f"<style>{CSS}</style></head>")
    for title in HEADINGS:
        tokens = [re.escape(token) for token in title.split()]
        pattern = re.compile(
            r"<p><strong>" + r"\s*".join(tokens) + r"</strong></p>"
        )
        matches = list(pattern.finditer(text))
        if matches:
            index = matches[-1].start()
            text = text[:index] + BREAK + text[index:]
    # 目录条目用紧凑样式，避免溢出到第二页
    toc_head = "<p><strong>目 录</strong></p>"
    toc_index = text.find(toc_head)
    intro_needle = "<p><strong>1 引言</strong></p>"
    intro_index = text.rfind(intro_needle)
    if toc_index != -1 and intro_index != -1 and intro_index > toc_index:
        text = text[:intro_index] + "</div>\n" + text[intro_index:]
        insert_at = toc_index + len(toc_head)
        text = text[:insert_at] + '<div class="toc">' + text[insert_at:]
    html.write_text(text)
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf}", f"file://{html}"],
        check=True,
        capture_output=True,
    )
    PDF.write_bytes(pdf.read_bytes())
    print(f"saved {PDF} ({PDF.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
