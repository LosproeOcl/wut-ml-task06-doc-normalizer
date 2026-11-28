#!/usr/bin/env python3
"""生成“投影幕布 PPT 页面”合成示例（试点，不参与训练/评估）。

流程：
1. 用 PIL 渲染 4:3 课件页（文字页 / 公式页，多种真实课程模板）；
2. 从 SCB-Dataset 教师子集取教室背景与 screen 框；
3. 透视贴图 + 投影亮度衰减 + 屏幕纹理 + 反光 + 模糊 + 噪声 + JPEG；
4. 输出 slide/projected 成对示例、manifest 与画廊。

用法：
    PYTHONPATH=src python scripts/build_synth_ppt_pages.py \
      --out data/synthetic/ppt_projection_v1 --n-per-class 12
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import random
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import matplotlib

matplotlib.use("Agg")
from matplotlib import rcParams
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import MathTextParser

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data/synthetic/ppt_projection_v1"
SCB_MANIFEST = ROOT / "data/manifests/scb_screen.csv"
DEFAULT_BG_MANIFEST = ROOT / "data/manifests/synth_backgrounds_v1.csv"

W, H = 1280, 960
MARGIN = 76
DPI = 100

rcParams["mathtext.fontset"] = "stix"
rcParams["mathtext.default"] = "regular"

FONT_SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
FONT_HIRAGINO = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_HEITI = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_TIMES = "/System/Library/Fonts/Supplemental/Times New Roman.ttf"
FONT_MENLO = "/System/Library/Fonts/Menlo.ttc"

# Songti.ttc 内部顺序：0 Black, 1 Bold, 6 Regular
SONGTI = dict(black=0, bold=1, regular=6)
HIRAGINO = dict(regular=0, bold=2)
HEITI = dict(sc=1)


@lru_cache(maxsize=256)
def font(path: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=index)


def songti(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    return font(FONT_SONGTI, size, SONGTI[weight])


def hiragino(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    return font(FONT_HIRAGINO, size, HIRAGINO[weight])


def heiti(size: int) -> ImageFont.FreeTypeFont:
    return font(FONT_HEITI, size, HEITI["sc"])


def times(size: int) -> ImageFont.FreeTypeFont:
    return font(FONT_TIMES, size, 0)


def menlo(size: int) -> ImageFont.FreeTypeFont:
    return font(FONT_MENLO, size, 0)


# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------

PALETTES = {
    "purple": {
        "fg": (248, 247, 255),
        "muted": (219, 214, 248),
        "accent": (255, 213, 128),
        "rule": (255, 255, 255, 120),
        "footer": "模式识别 · 第 3 章",
    },
    "paper": {
        "fg": (30, 28, 26),
        "muted": (92, 85, 76),
        "accent": (139, 30, 30),
        "rule": (120, 110, 95, 140),
        "footer": "资料来源：《模式识别》课程讲义",
    },
    "white": {
        "fg": (26, 34, 51),
        "muted": (96, 106, 122),
        "accent": (24, 122, 78),
        "rule": (190, 197, 205, 180),
        "footer": "机器学习 · 第 4 章",
    },
    "teal": {
        "fg": (250, 246, 232),
        "muted": (214, 226, 215),
        "accent": (240, 180, 90),
        "rule": (240, 230, 205, 120),
        "footer": "数据挖掘 · 第 2 章",
    },
}


def _base_canvas(rng: random.Random, template: str) -> Image.Image:
    nrng = np.random.default_rng(rng.randrange(1 << 30))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    if template == "purple":
        t = 0.72 * (yy / H) + 0.28 * (xx / W)
        c0 = np.array([27, 19, 99], dtype=np.float32)
        c1 = np.array([78, 64, 176], dtype=np.float32)
        arr = c0[None, None, :] + (c1 - c0)[None, None, :] * t[..., None]
        arr += 5.0 * np.sin(xx / 170.0 + yy / 230.0)[..., None]
        arr += 3.0 * np.cos(xx / 90.0)[..., None]
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr, "RGB")
        glow = Image.new("L", (W, H), 0)
        gd = ImageDraw.Draw(glow)
        gd.ellipse([760, -260, 1420, 360], fill=26)
        glow = glow.filter(ImageFilter.GaussianBlur(120))
        img = Image.composite(Image.new("RGB", (W, H), (142, 126, 228)), img, glow)
    elif template == "teal":
        t = 0.65 * (yy / H) + 0.35 * (xx / W)
        c0 = np.array([9, 43, 44], dtype=np.float32)
        c1 = np.array([28, 88, 80], dtype=np.float32)
        arr = c0[None, None, :] + (c1 - c0)[None, None, :] * t[..., None]
        arr += 4.0 * np.sin(yy / 210.0)[..., None]
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        veil = Image.new("L", (W, H), 0)
        ImageDraw.Draw(veil).ellipse([-200, 620, 600, 1100], fill=30)
        veil = veil.filter(ImageFilter.GaussianBlur(150))
        img = Image.composite(Image.new("RGB", (W, H), (66, 120, 104)), img, veil)
    elif template == "paper":
        arr = np.full((H, W, 3), [246, 241, 229], dtype=np.float32)
        low = nrng.normal(0, 1, (12, 16))
        low = np.asarray(Image.fromarray(((low - low.min()) / (np.ptp(low) + 1e-6) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), dtype=np.float32)
        arr += (low - 128.0)[..., None] * 0.05
        arr += nrng.normal(0, 1.6, (H, W, 1))
        shade = 1.0 - 0.035 * (xx / W) - 0.025 * (yy / H)
        arr *= shade[..., None]
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    elif template == "white":
        arr = np.full((H, W, 3), [251, 251, 249], dtype=np.float32)
        arr -= (yy / H)[..., None] * 5.0
        arr += nrng.normal(0, 0.9, (H, W, 1))
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 10], fill=(31, 122, 78))
    else:
        raise ValueError(template)
    return img


def _draw_header(img: Image.Image, template: str, title: str, kicker: str | None = None) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    pal = PALETTES[template]
    if template == "purple":
        f = songti(47, "bold")
        tw = d.textlength(title, font=f)
        d.text(((W - tw) / 2, 58), title, font=f, fill=pal["fg"])
        d.line([(W / 2 - 430, 142), (W / 2 + 430, 142)], fill=pal["rule"], width=2)
        if kicker:
            d.text((W / 2, 164), kicker, font=hiragino(19), fill=pal["muted"], anchor="ma")
    elif template == "paper":
        f = songti(43, "bold")
        d.text((MARGIN, 64), title, font=f, fill=pal["fg"])
        d.line([(MARGIN, 132), (W - MARGIN, 132)], fill=pal["fg"], width=3)
        if kicker:
            d.text((MARGIN, 150), kicker, font=hiragino(19), fill=pal["muted"])
    elif template == "white":
        d.rectangle([MARGIN, 58, MARGIN + 11, 122], fill=pal["accent"])
        d.text((MARGIN + 32, 58), title, font=hiragino(39, "bold"), fill=pal["fg"])
        d.line([(MARGIN, 140), (W - MARGIN, 140)], fill=pal["rule"], width=1)
        if kicker:
            d.text((MARGIN, 156), kicker, font=hiragino(18), fill=pal["muted"])
    elif template == "teal":
        d.text((MARGIN, 62), title, font=hiragino(40, "bold"), fill=pal["fg"])
        d.line([(MARGIN, 134), (MARGIN + 520, 134)], fill=pal["accent"], width=5)
        if kicker:
            d.text((MARGIN, 154), kicker, font=hiragino(19), fill=pal["muted"])


def _draw_footer(img: Image.Image, template: str, page: int) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    pal = PALETTES[template]
    f = hiragino(15)
    d.text((MARGIN, H - 40), pal["footer"], font=f, fill=(*pal["muted"], 180))
    d.text((W - MARGIN, H - 40), f"{page:02d}", font=times(17), fill=(*pal["muted"], 200), anchor="ra")


# ---------------------------------------------------------------------------
# 文本排版
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r"[A-Za-z0-9_\-–—.,:;!?/()\[\]{}%+=<>|&*#@$^~'\"\\]+|.", re.S)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for token in TOKEN_RE.findall(text):
        if token == "\n":
            lines.append(current)
            current = ""
            continue
        trial = current + token
        if draw.textlength(trial, font=f) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = token.lstrip()
    if current:
        lines.append(current)
    return lines or [""]


def body_font(template: str, size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    if template in {"purple", "paper"}:
        return songti(size, weight)
    return hiragino(size, weight)


def draw_paragraph(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    f: ImageFont.FreeTypeFont,
    fill,
    max_width: int,
    line_height: int,
    align: str = "left",
) -> int:
    x, y = xy
    for line in wrap_text(draw, text, f, max_width):
        if align == "center":
            draw.text((x + max_width / 2, y), line, font=f, fill=fill, anchor="ma")
        else:
            draw.text((x, y), line, font=f, fill=fill)
        y += line_height
    return y


def center_y(total_h: float, top: int = 190, bottom: int = 860) -> int:
    return int(top + max(0.0, (bottom - top - total_h) / 2))


def measure_bullets(
    draw: ImageDraw.ImageDraw,
    bullets: list,
    f: ImageFont.FreeTypeFont,
    max_width: int,
    line_height: int,
) -> float:
    total = 0.0
    for item in bullets:
        level, text = (item if isinstance(item, tuple) else (0, item))
        indent = level * 46
        total += len(wrap_text(draw, text, f, max_width - indent - 34)) * line_height
        total += 14 if level == 0 else 6
    return total


def draw_bullets(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    bullets: list,
    f: ImageFont.FreeTypeFont,
    fill,
    accent,
    max_width: int,
    line_height: int,
) -> int:
    for item in bullets:
        level = 0
        text = item
        if isinstance(item, tuple):
            level, text = item
        indent = level * 46
        marker = "•" if level == 0 else "–"
        mf = hiragino(28 if level == 0 else 24)
        draw.text((x + indent, y), marker, font=mf, fill=accent)
        y = draw_paragraph(draw, (x + indent + 34, y), text, f, fill, max_width - indent - 34, line_height)
        y += 14 if level == 0 else 6
    return y


def draw_table(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    headers: list[str],
    rows: list[list[str]],
    widths: list[float],
    f: ImageFont.FreeTypeFont,
    fill,
    header_fill,
    line_fill,
    row_height: int = 48,
    header_height: int = 50,
    header_text_fill=None,
) -> int:
    total = sum(widths)
    xs = [x]
    for w in widths:
        xs.append(xs[-1] + int(w / total * 1050))
    draw.rectangle([xs[0], y, xs[-1], y + header_height], fill=header_fill)
    header_text_fill = header_text_fill or fill
    for i, h in enumerate(headers):
        draw.text(((xs[i] + xs[i + 1]) / 2, y + header_height / 2), h, font=f, fill=header_text_fill, anchor="mm")
    y2 = y + header_height
    for r in rows:
        for i, cell in enumerate(r):
            draw.text(((xs[i] + xs[i + 1]) / 2, y2 + row_height / 2), cell, font=f, fill=fill, anchor="mm")
        y2 += row_height
        draw.line([(xs[0], y2), (xs[-1], y2)], fill=line_fill, width=1)
    for xx in xs:
        draw.line([(xx, y), (xx, y2)], fill=line_fill, width=1)
    draw.line([(xs[0], y), (xs[-1], y)], fill=line_fill, width=1)
    return y2


# ---------------------------------------------------------------------------
# 幻灯片内容
# ---------------------------------------------------------------------------

TEXT_ITEMS = [
    {
        "id": "txt_relation",
        "template": "purple",
        "title": "2. 定义关系模式",
        "layout": "deflist",
        "intro": "关系模式可以形式化地表示为：",
        "rows": [
            ("R", "(U, D, DOM, F)"),
            ("R", "关系名"),
            ("U", "组成该关系的属性名集合"),
            ("D", "U 中属性所来自的域"),
            ("DOM", "属性向域的映象集合"),
            ("F", "属性间数据的依赖关系集合"),
        ],
    },
    {
        "id": "txt_dataset",
        "template": "paper",
        "title": "3.1  实验数据集的构成",
        "layout": "table",
        "headers": ["类别", "训练", "验证", "测试", "合计"],
        "rows": [
            ["PPT·文字", "108", "17", "15", "140"],
            ["PPT·公式", "68", "4", "9", "81"],
            ["纸质·文字", "86", "11", "13", "110"],
            ["纸质·公式", "76", "19", "16", "111"],
            ["合计", "338", "51", "53", "442"],
        ],
        "widths": [2.0, 1.1, 1.1, 1.1, 1.1],
        "note": "注：按载体与内容类型分层抽样；测试集不参与训练与调参。",
    },
    {
        "id": "txt_fisher",
        "template": "purple",
        "title": "1) Fisher 判别法要解决的问题",
        "layout": "bullets",
        "bullets": [
            "应用统计方法解决模式识别问题时，在低维空间里行得通的方法，在高维情况里往往行不通。",
            "因此，降低维数有时就成为处理实际问题的关键。",
            "可以考虑把 d 维空间的样本投影到一条直线上，形成一维空间。",
            "问题是如何找到这条最好的、最易于分类的投影线。",
            "这就是 Fisher 法所要解决的基本问题。",
        ],
    },
    {
        "id": "txt_code",
        "template": "white",
        "title": "3.2  快速排序的实现",
        "layout": "code",
        "language": "Java",
        "code": [
            "public class QuickSort {",
            "    public static void sort(int[] a, int lo, int hi) {",
            "        if (lo >= hi) return;",
            "        int p = partition(a, lo, hi);",
            "        sort(a, lo, p - 1);",
            "        sort(a, p + 1, hi);",
            "    }",
            "",
            "    private static int partition(int[] a, int lo, int hi) {",
            "        int pivot = a[hi];",
            "        int i = lo;",
            "        for (int j = lo; j < hi; j++) {",
            "            if (a[j] < pivot) {",
            "                swap(a, i++, j);",
            "            }",
            "        }",
            "        swap(a, i, hi);",
            "        return i;",
            "    }",
            "}",
        ],
    },
    {
        "id": "txt_vocab",
        "template": "white",
        "title": "Unit 5  Academic Writing",
        "layout": "vocab",
        "kicker": "Words and expressions",
        "rows": [
            ("hypothesis", "n.", "假设；假说"),
            ("empirical", "adj.", "以实验（或经验）为依据的"),
            ("coherence", "n.", "连贯性；一致性"),
            ("paraphrase", "v.", "改述；释义"),
            ("plagiarism", "n.", "剽窃；抄袭"),
            ("citation", "n.", "引用；引文"),
            ("substantiate", "v.", "证实；为……提供证据"),
            ("concise", "adj.", "简明的；简洁的"),
        ],
    },
    {
        "id": "txt_kmeans",
        "template": "teal",
        "title": "算法 4.2  K-Means 聚类",
        "layout": "steps",
        "steps": [
            "随机选择 k 个样本作为初始簇中心；",
            "计算每个样本到各簇中心的距离，将其分配到最近的簇；",
            "重新计算每个簇的均值，作为新的簇中心；",
            "重复步骤 2 与 3，直到簇中心不再变化或达到最大迭代次数；",
            "输出最终的簇划分与簇中心。",
        ],
        "note": "复杂度：O(nkdT)，其中 T 为迭代次数。",
    },
    {
        "id": "txt_compare",
        "template": "white",
        "title": "两种特征归一化方法的比较",
        "layout": "twocol",
        "left_title": "Min-Max 归一化",
        "left_items": [
            "把每个特征缩放到 [0, 1] 区间",
            "受异常值影响较大",
            "适合图像像素、固定量纲特征",
            "不改变特征的分布形状",
        ],
        "right_title": "Z-Score 标准化",
        "right_items": [
            "把每个特征变为均值 0、方差 1",
            "对异常值相对稳健",
            "适合不同量纲的连续特征",
            "保留分布形状，但改变尺度",
        ],
    },
    {
        "id": "txt_cnn",
        "template": "purple",
        "title": "卷积神经网络的结构",
        "layout": "flow",
        "boxes": [
            ("输入", "224×224×3"),
            ("卷积", "3×3, 64"),
            ("池化", "2×2"),
            ("卷积", "3×3, 128"),
            ("全连接", "1000"),
            ("Softmax", "分类输出"),
        ],
        "table": {
            "headers": ["层", "输出尺寸", "参数量"],
            "rows": [
                ["输入", "224×224×3", "0"],
                ["卷积 3×3, 64", "112×112×64", "1,792"],
                ["最大池化 2×2", "56×56×64", "0"],
                ["卷积 3×3, 128", "56×56×128", "73,856"],
                ["全连接", "1000", "102,764,544"],
            ],
            "widths": [3.0, 2.4, 2.0],
        },
        "caption": "示例为单分支小型网络，实际结构可加入批归一化与残差连接。",
    },
    {
        "id": "txt_outline",
        "template": "purple",
        "title": "第 4 章  决策树",
        "layout": "bullets",
        "bullets": [
            (0, "4.1  基本流程"),
            (1, "自顶向下、分而治之的递归建树过程"),
            (0, "4.2  划分选择"),
            (1, "信息增益、增益率与基尼指数"),
            (0, "4.3  剪枝处理"),
            (1, "预剪枝与后剪枝，缓解过拟合"),
            (0, "4.4  连续值与缺失值"),
        ],
    },
    {
        "id": "txt_schedule",
        "template": "paper",
        "title": "实验进度安排",
        "layout": "table",
        "headers": ["周次", "内容", "交付物"],
        "rows": [
            ["第 9 周", "数据采集与清洗", "样本清单、隐私审查"],
            ["第 10 周", "定位与矫正", "四角标注、拉正结果"],
            ["第 11 周", "传统机器学习基线", "SVM / 随机森林对比"],
            ["第 12 周", "轻量深度学习模型", "MobileNetV3 实验"],
            ["第 13 周", "测试与消融", "测试报告、组图"],
        ],
        "widths": [1.2, 3.0, 3.2],
        "note": "每组每周提交一次进度记录；测试集只在最后阶段使用。",
    },
    {
        "id": "txt_refs",
        "template": "paper",
        "title": "参考文献",
        "layout": "refs",
        "refs": [
            "[1] 边肇祺, 张学工. 模式识别（第二版）. 清华大学出版社, 2000.",
            "[2] 周志华. 机器学习. 清华大学出版社, 2016.",
            "[3] Bishop C M. Pattern Recognition and Machine Learning. Springer, 2006.",
            "[4] Goodfellow I, Bengio Y, Courville A. Deep Learning. MIT Press, 2016.",
            "[5] He K, Zhang X, Ren S, et al. Deep Residual Learning for Image Recognition. CVPR, 2016.",
            "[6] Howard A, Sandler M, Chu G, et al. Searching for MobileNetV3. ICCV, 2019.",
        ],
    },
    {
        "id": "txt_summary",
        "template": "teal",
        "title": "本章小结",
        "layout": "bullets",
        "bullets": [
            "模式识别系统的四个基本环节：数据获取、预处理、特征提取与分类决策。",
            "特征选择与降维是缓解“维数灾难”的关键手段。",
            "Fisher 判别分析寻找类间散度大、类内散度小的投影方向。",
            "分类器评估必须使用独立测试集，并报告混淆矩阵与宏平均指标。",
        ],
    },
]

FORMULA_ITEMS = [
    {
        "id": "f_bayes",
        "template": "purple",
        "title": "Bayes 决策规则",
        "intro": "由先验概率与类条件概率密度计算后验概率：",
        "lines": [
            r"P(\omega_i\mid \mathbf{x})=\frac{p(\mathbf{x}\mid \omega_i)P(\omega_i)}{p(\mathbf{x})}",
            r"p(\mathbf{x})=\sum_{j=1}^{c}p(\mathbf{x}\mid \omega_j)P(\omega_j)",
            r"P(\omega_i\mid \mathbf{x})>P(\omega_j\mid \mathbf{x})\ \Rightarrow\ \mathbf{x}\in\omega_i",
            r"R(\alpha_i\mid \mathbf{x})=\sum_{j=1}^{c}\lambda_{ij}P(\omega_j\mid \mathbf{x})",
            r"\alpha^{*}=\mathrm{arg\,min}_{i}\ R(\alpha_i\mid \mathbf{x})",
        ],
        "note": "最小错误率决策等价于最大后验概率决策。",
    },
    {
        "id": "f_fisher",
        "template": "purple",
        "title": "Fisher 线性判别",
        "intro": "准则函数定义为类间散度与类内散度之比：",
        "lines": [
            r"J(\mathbf{w})=\frac{\mathbf{w}^{\top}\mathbf{S}_B\mathbf{w}}{\mathbf{w}^{\top}\mathbf{S}_W\mathbf{w}}",
            r"\mathbf{S}_B=(\mathbf{m}_1-\mathbf{m}_2)(\mathbf{m}_1-\mathbf{m}_2)^{\top}",
            r"\mathbf{S}_W=\sum_{i=1}^{2}\sum_{\mathbf{x}\in\omega_i}(\mathbf{x}-\mathbf{m}_i)(\mathbf{x}-\mathbf{m}_i)^{\top}",
            r"\mathbf{w}^{*}=\mathbf{S}_W^{-1}(\mathbf{m}_1-\mathbf{m}_2)",
        ],
        "note": "w* 的方向与类均值差一致，尺度由类内散度矩阵决定。",
    },
    {
        "id": "f_regression",
        "template": "white",
        "title": "多元线性回归",
        "intro": "最小二乘估计与正规方程：",
        "lines": [
            r"y=\mathbf{w}^{\top}\mathbf{x}+b",
            r"\hat{\mathbf{w}}=(\mathbf{X}^{\top}\mathbf{X})^{-1}\mathbf{X}^{\top}\mathbf{y}",
            r"\mathbf{H}=\mathbf{X}(\mathbf{X}^{\top}\mathbf{X})^{-1}\mathbf{X}^{\top}",
            r"\mathrm{RSS}(\mathbf{w})=\|\mathbf{y}-\mathbf{X}\mathbf{w}\|_2^2",
            r"\nabla_{\mathbf{w}}\mathrm{RSS}=-2\mathbf{X}^{\top}(\mathbf{y}-\mathbf{X}\mathbf{w})=0",
        ],
        "note": "H 称为帽子矩阵，满足 H² = H 且 HX = X。",
    },
    {
        "id": "f_svm",
        "template": "purple",
        "title": "支持向量机的对偶问题",
        "intro": "软间隔 SVM 的原始优化问题：",
        "lines": [
            r"\min_{\mathbf{w},b}\ \frac{1}{2}\|\mathbf{w}\|^2",
            r"\mathrm{s.t.}\quad y_i(\mathbf{w}^{\top}\mathbf{x}_i+b)\geq 1,\ i=1,\ldots,N",
            r"L(\mathbf{w},b,\boldsymbol{\alpha})=\frac{1}{2}\|\mathbf{w}\|^2-\sum_{i=1}^{N}\alpha_i[y_i(\mathbf{w}^{\top}\mathbf{x}_i+b)-1]",
            r"\max_{\boldsymbol{\alpha}}\ \sum_{i=1}^{N}\alpha_i-\frac{1}{2}\sum_{i,j}\alpha_i\alpha_jy_iy_j\mathbf{x}_i^{\top}\mathbf{x}_j",
        ],
        "note": "KKT 条件给出稀疏解：只有支持向量对应的 αi > 0。",
    },
    {
        "id": "f_gaussian",
        "template": "white",
        "title": "多元高斯分布",
        "intro": "d 维高斯密度与马氏距离：",
        "lines": [
            r"p(\mathbf{x})=\frac{1}{(2\pi)^{d/2}|\Sigma|^{1/2}}\exp\left[-\frac{1}{2}(\mathbf{x}-\boldsymbol{\mu})^{\top}\Sigma^{-1}(\mathbf{x}-\boldsymbol{\mu})\right]",
            r"d_M(\mathbf{x},\boldsymbol{\mu})=\sqrt{(\mathbf{x}-\boldsymbol{\mu})^{\top}\Sigma^{-1}(\mathbf{x}-\boldsymbol{\mu})}",
            r"\ln p(\mathbf{x})=-\frac{d}{2}\ln(2\pi)-\frac{1}{2}\ln|\Sigma|-\frac{1}{2}d_M^2",
        ],
        "note": "协方差矩阵 Σ 必须正定；实际计算常用 Cholesky 分解。",
    },
    {
        "id": "f_eigen",
        "template": "paper",
        "title": "特征值与特征分解",
        "intro": "对称矩阵可正交对角化：",
        "lines": [
            r"\mathbf{A}\mathbf{v}_i=\lambda_i\mathbf{v}_i,\quad i=1,\ldots,d",
            r"\mathbf{A}=\mathbf{Q}\Lambda\mathbf{Q}^{\top}",
            r"\mathbf{Q}^{\top}\mathbf{Q}=\mathbf{I}",
            r"\mathrm{tr}(\mathbf{A})=\sum_{i=1}^{d}\lambda_i,\quad |\mathbf{A}|=\prod_{i=1}^{d}\lambda_i",
        ],
        "note": "实对称矩阵的特征向量正交，特征值均为实数。",
    },
    {
        "id": "f_gd",
        "template": "purple",
        "title": "梯度下降与学习率",
        "intro": "以经验风险最小化为目标：",
        "lines": [
            r"\mathcal{L}(\boldsymbol{\theta})=\frac{1}{N}\sum_{i=1}^{N}\ell(y_i,f(\mathbf{x}_i;\boldsymbol{\theta}))",
            r"\boldsymbol{\theta}_{t+1}=\boldsymbol{\theta}_t-\eta\nabla_{\boldsymbol{\theta}}\mathcal{L}(\boldsymbol{\theta}_t)",
            r"\eta_t=\frac{\eta_0}{1+\lambda t}",
            r"\|\nabla\mathcal{L}(\boldsymbol{\theta}_t)\|<\varepsilon",
        ],
        "note": "学习率过大易震荡，过小则收敛慢；常用余弦退火或阶梯衰减。",
    },
    {
        "id": "f_sparse",
        "template": "purple",
        "title": "点到超平面的距离",
        "intro": "超平面方程：",
        "lines": [
            r"\mathbf{w}^{\top}\mathbf{x}+b=0",
            r"d(\mathbf{x}_0,\mathbf{w},b)=\frac{|\mathbf{w}^{\top}\mathbf{x}_0+b|}{\|\mathbf{w}\|}",
        ],
        "note": "分子取绝对值，分母是法向量 w 的欧氏范数。",
        "sparse": True,
    },
    {
        "id": "f_entropy",
        "template": "white",
        "title": "信息熵与互信息",
        "intro": "离散随机变量的不确定性度量：",
        "lines": [
            r"H(X)=-\sum_{i=1}^{n}p(x_i)\log_2 p(x_i)",
            r"H(X,Y)=-\sum_{x,y}p(x,y)\log_2 p(x,y)",
            r"I(X;Y)=H(X)+H(Y)-H(X,Y)",
            r"D_{\mathrm{KL}}(P\|Q)=\sum_{x}p(x)\log\frac{p(x)}{q(x)}",
        ],
        "note": "当对数底为 2 时，熵的单位为比特（bit）。",
    },
    {
        "id": "f_lagrange",
        "template": "white",
        "title": "拉格朗日乘子法",
        "intro": "带不等式与等式约束的优化问题：",
        "lines": [
            r"\min_{\mathbf{x}}\ f(\mathbf{x})",
            r"\mathrm{s.t.}\quad g_i(\mathbf{x})\leq 0,\quad h_j(\mathbf{x})=0",
            r"L(\mathbf{x},\boldsymbol{\lambda},\boldsymbol{\nu})=f(\mathbf{x})+\sum_{i}\lambda_i g_i(\mathbf{x})+\sum_{j}\nu_j h_j(\mathbf{x})",
            r"\nabla_{\mathbf{x}}L=0,\quad \lambda_i g_i(\mathbf{x})=0,\quad \lambda_i\geq 0",
        ],
        "note": "互补松弛条件 λi gi(x) = 0 是 KKT 条件的核心。",
    },
    {
        "id": "f_pca",
        "template": "purple",
        "title": "主成分分析",
        "intro": "对中心化数据做协方差矩阵的特征分解：",
        "lines": [
            r"\mathbf{C}=\frac{1}{N}\sum_{i=1}^{N}(\mathbf{x}_i-\boldsymbol{\mu})(\mathbf{x}_i-\boldsymbol{\mu})^{\top}",
            r"\mathbf{C}\mathbf{u}_j=\lambda_j\mathbf{u}_j,\quad \lambda_1\geq\lambda_2\geq\cdots\geq\lambda_d",
            r"\mathbf{z}=\mathbf{U}_k^{\top}(\mathbf{x}-\boldsymbol{\mu})",
        ],
        "note": "保留前 k 个主成分，使投影误差平方和最小。",
    },
    {
        "id": "f_dense",
        "template": "teal",
        "title": "正则化与稀疏解",
        "intro": "线性模型的梯度与近端算子：",
        "lines": [
            r"\frac{\partial L}{\partial \mathbf{w}}=\mathbf{X}^{\top}(\mathbf{X}\mathbf{w}-\mathbf{y})",
            r"\mathbf{w}\leftarrow\mathbf{w}-\eta\mathbf{X}^{\top}(\mathbf{X}\mathbf{w}-\mathbf{y})",
            r"\mathbf{w}\leftarrow(1-\eta\lambda)\mathbf{w}-\eta\mathbf{X}^{\top}(\mathbf{X}\mathbf{w}-\mathbf{y})",
            r"\|\mathbf{w}\|_1=\sum_{j=1}^{d}|w_j|,\quad \|\mathbf{w}\|_2^2=\sum_{j=1}^{d}w_j^2",
            r"\mathrm{soft}(z,\lambda)=\mathrm{sign}(z)\max(|z|-\lambda,0)",
            r"\hat{\mathbf{w}}=\mathrm{arg\,min}_{\mathbf{w}}\ \frac{1}{2N}\|\mathbf{y}-\mathbf{X}\mathbf{w}\|_2^2+\lambda\|\mathbf{w}\|_1",
        ],
        "note": "L1 正则产生稀疏解，L2 正则使权重整体收缩。",
    },
]


# ---------------------------------------------------------------------------
# 公式排版
# ---------------------------------------------------------------------------

MATH_PARSER = MathTextParser("agg")


def _math_metrics(expr: str, font_px: float) -> tuple[float, float, float]:
    prop = FontProperties(size=font_px * 72.0 / DPI)
    width, height, depth = MATH_PARSER.parse(f"${expr}$", dpi=DPI, prop=prop)[2:5]
    return float(width), float(height), float(depth)


def _split_eq(expr: str) -> tuple[str, str] | None:
    if "\\mathrm{s.t.}" in expr:
        return None
    depth = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "\\":
            i += 2
            continue
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        elif ch == "=" and depth == 0:
            nxt = expr[i + 1 : i + 2]
            prev = expr[i - 1 : i]
            if nxt not in "=>" and prev not in "<>!=":
                return expr[:i].rstrip(), expr[i + 1 :].lstrip()
        i += 1
    return None


def _formula_geometry(lines: list[str], font_px: float) -> tuple[list, float, float, float]:
    splits = [_split_eq(line) for line in lines]
    left_max = right_max = 0.0
    for line, sp in zip(lines, splits):
        if sp is None:
            continue
        lw, _, _ = _math_metrics(sp[0], font_px)
        rw, _, _ = _math_metrics(sp[1], font_px)
        left_max, right_max = max(left_max, lw), max(right_max, rw)
    gap = 46.0
    total = left_max + gap + right_max
    if total > 1050:
        scale = 1050 / total
        font_px *= scale
        left_max *= scale
        right_max *= scale
        gap *= scale
    x_eq = (W - (left_max + gap + right_max)) / 2 + left_max
    return splits, font_px, gap, x_eq


def formula_height(lines: list[str], font_px: float, line_gap: int) -> float:
    splits, font_px, _, _ = _formula_geometry(lines, font_px)
    total = 0.0
    for line, sp in zip(lines, splits):
        if sp is None:
            _, h, d = _math_metrics(line, font_px)
            total += h + d + line_gap
        else:
            _, lh, ld = _math_metrics(sp[0], font_px)
            _, rh, rd = _math_metrics(sp[1], font_px)
            total += max(lh, rh) + max(ld, rd) + line_gap
    return total - line_gap


def draw_formula_block(
    img: Image.Image,
    lines: list[str],
    template: str,
    font_px: float,
    start_y: int,
    numbers: bool = False,
    line_gap: int = 30,
) -> list[int]:
    pal = PALETTES[template]
    color = tuple(c / 255 for c in pal["fg"])
    fig = Figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    fig.patch.set_alpha(0)
    canvas = FigureCanvasAgg(fig)

    splits, font_px, gap, x_eq = _formula_geometry(lines, font_px)

    y = float(start_y)
    baselines: list[int] = []
    for line, sp in zip(lines, splits):
        if sp is None:
            _, h, d = _math_metrics(line, font_px)
            baseline = y + h
            fig.text(W / 2 / W, 1 - baseline / H, f"${line}$", fontsize=font_px * 72.0 / DPI, color=color, ha="center", va="baseline")
            total_h = h + d
        else:
            lw, lh, ld = _math_metrics(sp[0], font_px)
            rw, rh, rd = _math_metrics(sp[1], font_px)
            baseline = y + max(lh, rh)
            fig.text(x_eq / W, 1 - baseline / H, f"${sp[0]}$", fontsize=font_px * 72.0 / DPI, color=color, ha="right", va="baseline")
            fig.text((x_eq + gap / 2) / W, 1 - baseline / H, "$=$", fontsize=font_px * 72.0 / DPI, color=color, ha="center", va="baseline")
            fig.text((x_eq + gap) / W, 1 - baseline / H, f"${sp[1]}$", fontsize=font_px * 72.0 / DPI, color=color, ha="left", va="baseline")
            total_h = max(lh, rh) + max(ld, rd)
        baselines.append(int(round(baseline)))
        y += total_h + line_gap

    canvas.draw()
    layer = Image.fromarray(np.asarray(canvas.buffer_rgba()), "RGBA")
    img.alpha_composite(layer)

    if numbers:
        d = ImageDraw.Draw(img, "RGBA")
        nf = times(20)
        for idx, baseline in enumerate(baselines, 1):
            d.text((W - MARGIN - 18, baseline), f"({idx})", font=nf, fill=(*pal["muted"], 210), anchor="rs")
    return baselines


def render_formula_slide(item: dict, rng: random.Random, page: int) -> Image.Image:
    tpl = item["template"]
    img = _base_canvas(rng, tpl).convert("RGBA")
    _draw_header(img, tpl, item["title"], item.get("kicker"))
    d = ImageDraw.Draw(img, "RGBA")
    pal = PALETTES[tpl]
    top = 200
    if item.get("intro"):
        top = draw_paragraph(d, (MARGIN, top), item["intro"], hiragino(24), (*pal["muted"], 245), W - 2 * MARGIN, 36)
        top += 14
    bottom = 770 if item.get("note") else 850
    font_px = 40.0
    block_h = formula_height(item["lines"], font_px, 34)
    available = bottom - top
    if block_h > available:
        font_px *= available / block_h
        block_h = formula_height(item["lines"], font_px, 34)
    y = top + max(0.0, (available - block_h) / 2)
    draw_formula_block(
        img,
        item["lines"],
        tpl,
        font_px=font_px,
        start_y=int(y),
        numbers=len(item["lines"]) >= 4,
        line_gap=34,
    )
    if item.get("note"):
        note_f = hiragino(22)
        note_y = H - 125
        d.text((W / 2, note_y), item["note"], font=note_f, fill=(*pal["muted"], 235), anchor="ma")
    _draw_footer(img, tpl, page)
    return img.convert("RGB")


# ---------------------------------------------------------------------------
# 文字版式
# ---------------------------------------------------------------------------

CODE_TOKEN = re.compile(
    r'("(?:[^"\\]|\\.)*"|//.*$|\b(?:public|private|class|static|void|int|if|else|for|while|return|new|final)\b|\b\d+\b)'
)


def _draw_code(d: ImageDraw.ImageDraw, item: dict, template: str, top: int = 190) -> None:
    base_y = top
    panel = [MARGIN - 8, base_y - 14, W - MARGIN + 8, H - 80]
    d.rounded_rectangle(panel, radius=8, fill=(246, 247, 249), outline=(218, 222, 228), width=1)
    f = menlo(19)
    line_h = 31
    y = base_y + 4
    for idx, line in enumerate(item["code"], 1):
        d.text((MARGIN + 4, y), f"{idx:2d}", font=menlo(16), fill=(150, 157, 168))
        x = MARGIN + 42
        pos = 0
        for m in CODE_TOKEN.finditer(line):
            if m.start() > pos:
                d.text((x, y), line[pos : m.start()], font=f, fill=(43, 48, 58))
                x += d.textlength(line[pos : m.start()], font=f)
            tok = m.group(0)
            if tok.startswith("//"):
                fill = (120, 132, 148)
            elif tok.startswith('"'):
                fill = (166, 84, 34)
            elif tok[0].isdigit():
                fill = (120, 82, 160)
            else:
                fill = (32, 86, 156)
            d.text((x, y), tok, font=f, fill=fill)
            x += d.textlength(tok, font=f)
            pos = m.end()
        if pos < len(line):
            d.text((x, y), line[pos:], font=f, fill=(43, 48, 58))
        y += line_h


def _draw_flow(d: ImageDraw.ImageDraw, item: dict, template: str, top: int = 330, show_notes: bool = True) -> None:
    pal = PALETTES[template]
    boxes = item["boxes"]
    n = len(boxes)
    bw, bh = 166, 142
    gap = (W - 2 * MARGIN - n * bw) / (n - 1)
    y = top
    centers = []
    for i, (head, sub) in enumerate(boxes):
        x = MARGIN + i * (bw + gap)
        d.rounded_rectangle([x, y, x + bw, y + bh], radius=14, fill=(255, 255, 255, 26), outline=(255, 255, 255, 170), width=2)
        d.text((x + bw / 2, y + 38), head, font=hiragino(25, "bold"), fill=pal["fg"], anchor="mm")
        d.text((x + bw / 2, y + 82), sub, font=hiragino(17), fill=pal["muted"], anchor="mm")
        centers.append((x, y, bw, bh))
        if i < n - 1:
            x1 = x + bw + 6
            x2 = x + bw + gap - 6
            cy = y + bh / 2
            d.line([(x1, cy), (x2, cy)], fill=(255, 255, 255, 180), width=3)
            d.polygon([(x2, cy), (x2 - 12, cy - 7), (x2 - 12, cy + 7)], fill=(255, 255, 255, 180))
    if show_notes:
        d.text((W / 2, y + bh + 74), "特征图尺寸逐层减小，通道数逐层增加", font=hiragino(21), fill=(*pal["muted"], 235), anchor="ma")
        d.text((W / 2, y + bh + 116), "参数量主要集中在全连接层，约占 80% 以上", font=hiragino(19), fill=(*pal["muted"], 210), anchor="ma")


def render_text_slide(item: dict, rng: random.Random, page: int) -> Image.Image:
    tpl = item["template"]
    img = _base_canvas(rng, tpl)
    _draw_header(img, tpl, item["title"], item.get("kicker"))
    d = ImageDraw.Draw(img, "RGBA")
    pal = PALETTES[tpl]
    layout = item["layout"]
    y = 200

    if layout == "deflist":
        total_h = len(item["rows"]) * 82 + (58 if item.get("intro") else 0)
        y = center_y(total_h, 190, 850)
        if item.get("intro"):
            y = draw_paragraph(d, (MARGIN, y), item["intro"], hiragino(25), (*pal["muted"], 245), W - 2 * MARGIN, 40)
            y += 18
        term_f = songti(31, "bold")
        desc_f = body_font(tpl, 27)
        for term, desc in item["rows"]:
            d.text((MARGIN + 24, y), term, font=term_f, fill=pal["accent"])
            d.text((MARGIN + 200, y + 4), desc, font=desc_f, fill=pal["fg"])
            y += 82
    elif layout == "bullets":
        bf = body_font(tpl, 29)
        total_h = measure_bullets(d, item["bullets"], bf, W - 2 * MARGIN - 40, 52)
        y = center_y(total_h, 190, 850)
        y = draw_bullets(d, MARGIN + 10, y, item["bullets"], bf, pal["fg"], pal["accent"], W - 2 * MARGIN - 40, 52)
    elif layout == "table":
        f = body_font(tpl, 24)
        total_h = 58 + len(item["rows"]) * 58 + (50 if item.get("note") else 0)
        y = center_y(total_h, 190, 850)
        dark = tpl in {"purple", "teal"}
        y = draw_table(
            d,
            MARGIN,
            y,
            item["headers"],
            item["rows"],
            item["widths"],
            f,
            pal["fg"],
            header_fill=pal["accent"] if dark else (235, 226, 208),
            line_fill=(176, 165, 146) if not dark else (*pal["muted"], 90),
            row_height=58,
            header_height=58,
            header_text_fill=(28, 28, 28) if dark else pal["fg"],
        )
        if item.get("note"):
            d.text((MARGIN, y + 26), item["note"], font=hiragino(20), fill=pal["muted"])
    elif layout == "code":
        total_h = len(item["code"]) * 31 + 30
        _draw_code(d, item, tpl, center_y(total_h, 185, 870))
    elif layout == "vocab":
        total_h = len(item["rows"]) * 62 + 34
        y = center_y(total_h, 190, 850)
        d.line([(MARGIN, y), (W - MARGIN, y)], fill=pal["rule"], width=2)
        y += 16
        for word, pos, gloss in item["rows"]:
            d.text((MARGIN + 8, y), word, font=times(26), fill=pal["fg"])
            d.text((MARGIN + 360, y + 4), pos, font=times(21), fill=pal["accent"])
            d.text((MARGIN + 470, y + 2), gloss, font=hiragino(23), fill=pal["muted"])
            y += 62
    elif layout == "steps":
        f = hiragino(25)
        total_h = sum(len(wrap_text(d, text, f, W - MARGIN - (MARGIN + 62) - 40)) * 38 + 26 for text in item["steps"])
        y = center_y(total_h + (36 if item.get("note") else 0), 190, 850)
        for i, text in enumerate(item["steps"], 1):
            d.ellipse([MARGIN + 6, y + 2, MARGIN + 42, y + 38], fill=pal["accent"])
            d.text((MARGIN + 24, y + 19), str(i), font=heiti(19), fill=(20, 30, 30), anchor="mm")
            y = draw_paragraph(d, (MARGIN + 62, y), text, f, pal["fg"], W - MARGIN - (MARGIN + 62) - 40, 38)
            y += 26
        if item.get("note"):
            d.text((MARGIN + 62, y + 18), item["note"], font=hiragino(20), fill=pal["muted"])
    elif layout == "twocol":
        panel_w = (W - 2 * MARGIN - 40) // 2
        y = center_y(560, 190, 860)
        for side, x in [("left", MARGIN), ("right", MARGIN + panel_w + 40)]:
            title = item[f"{side}_title"]
            items = item[f"{side}_items"]
            d.rounded_rectangle([x, y, x + panel_w, y + 560], radius=10, fill=(245, 247, 246), outline=(208, 214, 211), width=1)
            d.rectangle([x, y, x + panel_w, y + 62], fill=(31, 122, 78) if side == "left" else (54, 92, 140))
            d.text((x + panel_w / 2, y + 31), title, font=hiragino(25, "bold"), fill="white", anchor="mm")
            yy = y + 92
            for it in items:
                d.text((x + 30, yy), "•", font=hiragino(26), fill=(31, 122, 78) if side == "left" else (54, 92, 140))
                yy = draw_paragraph(d, (x + 58, yy), it, hiragino(21), (40, 48, 56), panel_w - 90, 32)
                yy += 26
    elif layout == "flow":
        table = item.get("table")
        total_h = 142 + (58 + len(table["rows"]) * 46 + 50 if table else 110)
        top = center_y(total_h, 190, 850)
        _draw_flow(d, item, tpl, top, show_notes=not table)
        if table:
            ty = top + 142 + 46
            ty = draw_table(
                d,
                MARGIN + 60,
                ty,
                table["headers"],
                table["rows"],
                table["widths"],
                body_font(tpl, 20),
                pal["fg"],
                header_fill=pal["accent"],
                line_fill=(*pal["muted"], 90),
                row_height=46,
                header_height=46,
                header_text_fill=(28, 28, 28),
            )
            if item.get("caption"):
                d.text((W / 2, ty + 34), item["caption"], font=hiragino(18), fill=(*pal["muted"], 220), anchor="ma")
    elif layout == "refs":
        f = body_font(tpl, 22)
        total_h = 0.0
        for ref in item["refs"]:
            total_h += len(wrap_text(d, ref, f, W - 2 * MARGIN - 34)) * 34 + 24
        y = center_y(total_h, 185, 850)
        for ref in item["refs"]:
            lines = wrap_text(d, ref, f, W - 2 * MARGIN - 34)
            d.text((MARGIN, y), lines[0], font=f, fill=pal["fg"])
            yy = y + 34
            for line in lines[1:]:
                d.text((MARGIN + 34, yy), line, font=f, fill=pal["fg"])
                yy += 34
            y = yy + 24
    else:
        raise ValueError(layout)

    _draw_footer(img, tpl, page)
    return img


# ---------------------------------------------------------------------------
# 投影合成
# ---------------------------------------------------------------------------

def homography(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> np.ndarray:
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.extend([u, v])
    h = np.linalg.solve(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))
    return np.append(h, 1.0).reshape(3, 3)


def warp_slide(slide: Image.Image, quad: list[tuple[float, float]], size: tuple[int, int], border: int = 14) -> Image.Image:
    w, h = slide.size
    canvas = Image.new("RGBA", (w + 2 * border, h + 2 * border), (0, 0, 0, 0))
    canvas.paste(slide.convert("RGBA"), (border, border))
    src = [(border, border), (border + w, border), (border + w, border + h), (border, border + h)]
    hmat = homography(src, quad)
    inv = np.linalg.inv(hmat)
    coeffs = (inv / inv[2, 2]).flatten()[:8]
    return canvas.transform(size, Image.PERSPECTIVE, tuple(coeffs), resample=Image.BICUBIC)


def _quad_from_bbox(
    bbox: tuple[float, float, float, float],
    size: tuple[int, int],
    rng: random.Random,
    base_quad: list[tuple[float, float]] | None = None,
) -> list[tuple[float, float]]:
    Wb, Hb = size
    if base_quad is not None:
        pts = [(float(x) * Wb, float(y) * Hb) for x, y in base_quad]
        cx = sum(p[0] for p in pts) / 4
        cy = sum(p[1] for p in pts) / 4
        scale = rng.uniform(1.004, 1.014)
        pts = [(cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in pts]
        jx, jy = Wb * 0.0015, Hb * 0.002
        pts = [
            (min(max(x + rng.uniform(-jx, jx), 0), Wb - 1), min(max(y + rng.uniform(-jy, jy), 0), Hb - 1))
            for x, y in pts
        ]
        x1, x2 = min(p[0] for p in pts), max(p[0] for p in pts)
        y1, y2 = min(p[1] for p in pts), max(p[1] for p in pts)
        if x1 <= 1.5:
            pts = [(0.0 if x <= 1.5 else x, y) for x, y in pts]
        if x2 >= Wb - 2.5:
            pts = [(float(Wb - 1) if x >= Wb - 2.5 else x, y) for x, y in pts]
        if y1 <= 1.5:
            pts = [(x, 0.0 if y <= 1.5 else y) for x, y in pts]
        if y2 >= Hb - 2.5:
            pts = [(x, float(Hb - 1) if y >= Hb - 2.5 else y) for x, y in pts]
        return pts

    x1, y1, x2, y2 = bbox
    x1, x2 = x1 * Wb, x2 * Wb
    y1, y2 = y1 * Hb, y2 * Hb
    bw, bh = x2 - x1, y2 - y1
    expand_x = rng.uniform(0.003, 0.012) * bw
    expand_y = rng.uniform(0.003, 0.012) * bh
    x1, x2 = x1 - expand_x, x2 + expand_x
    y1, y2 = y1 - expand_y, y2 + expand_y
    jx, jy = 0.010 * bw, 0.012 * bh
    pts = [
        (x1 + rng.uniform(-jx, jx), y1 + rng.uniform(-jy, jy)),
        (x2 + rng.uniform(-jx, jx), y1 + rng.uniform(-jy, jy)),
        (x2 + rng.uniform(-jx, jx), y2 + rng.uniform(-jy, jy)),
        (x1 + rng.uniform(-jx, jx), y2 + rng.uniform(-jy, jy)),
    ]
    # 轻微梯形：底部略宽或顶部略窄
    top_scale = rng.uniform(0.985, 1.012)
    bottom_scale = rng.uniform(0.985, 1.012)
    cx = (x1 + x2) / 2
    pts = [
        (cx + (pts[0][0] - cx) * top_scale, pts[0][1]),
        (cx + (pts[1][0] - cx) * top_scale, pts[1][1]),
        (cx + (pts[2][0] - cx) * bottom_scale, pts[2][1]),
        (cx + (pts[3][0] - cx) * bottom_scale, pts[3][1]),
    ]
    pts = [(min(max(x, 0), Wb - 1), min(max(y, 0), Hb - 1)) for x, y in pts]
    # 屏幕贴边时把对应边吸到画幅边缘，避免露出旧课件残边
    if x1 <= 1.5:
        pts[0] = (0.0, pts[0][1])
        pts[3] = (0.0, pts[3][1])
    if x2 >= Wb - 2.5:
        pts[1] = (float(Wb - 1), pts[1][1])
        pts[2] = (float(Wb - 1), pts[2][1])
    if y1 <= 1.5:
        pts[0] = (pts[0][0], 0.0)
        pts[1] = (pts[1][0], 0.0)
    if y2 >= Hb - 2.5:
        pts[2] = (pts[2][0], float(Hb - 1))
        pts[3] = (pts[3][0], float(Hb - 1))
    return pts


def _gain_map(size: tuple[int, int], quad: list[tuple[float, float]], rng: random.Random) -> np.ndarray:
    Wb, Hb = size
    cx = sum(p[0] for p in quad) / 4
    cy = sum(p[1] for p in quad) / 4
    rx = max(40.0, (max(p[0] for p in quad) - min(p[0] for p in quad)) / 2)
    ry = max(40.0, (max(p[1] for p in quad) - min(p[1] for p in quad)) / 2)
    yy, xx = np.mgrid[0:Hb, 0:Wb].astype(np.float32)
    r2 = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    vignette = 1.04 - 0.16 * np.clip(r2, 0, 1.6)
    angle = rng.uniform(-0.6, 0.6)
    linear = 1.0 + rng.uniform(-0.05, 0.05) * np.cos(angle) * (xx / Wb - 0.5)
    return np.clip(vignette * linear, 0.7, 1.15).astype(np.float32)


def project_slide(
    bg: Image.Image,
    slide: Image.Image,
    quad: list[tuple[float, float]],
    rng: random.Random,
    plate_bottom: float = 1.018,
) -> Image.Image:
    Wb, Hb = bg.size
    nrng = np.random.default_rng(rng.randrange(1 << 30))
    warped = warp_slide(slide, quad, (Wb, Hb))
    arr = np.asarray(warped).astype(np.float32)
    rgb = arr[..., :3] / 255.0

    gain = _gain_map((Wb, Hb), quad, rng)[..., None]
    rgb *= gain

    # 投影仪偏色与对比度下降
    tint = np.array([rng.uniform(0.97, 1.03), rng.uniform(0.98, 1.01), rng.uniform(0.96, 1.02)], dtype=np.float32)
    rgb *= tint[None, None, :]
    contrast = rng.uniform(0.82, 0.93)
    brightness = rng.uniform(0.89, 0.99)
    rgb = (rgb - 0.5) * contrast + 0.5 + (brightness - 1.0)
    gray = rgb.mean(axis=2, keepdims=True)
    rgb = gray + (rgb - gray) * rng.uniform(0.88, 0.96)

    # 屏幕纹理 + 摩尔纹
    yy, xx = np.mgrid[0:Hb, 0:Wb].astype(np.float32)
    period = rng.uniform(2.2, 4.2)
    texture = 1.0 + 0.010 * np.sin(2 * np.pi * xx / period) + 0.006 * np.sin(2 * np.pi * yy / (period * 1.3))
    theta = rng.uniform(-0.5, 0.5)
    moire = 1.0 + rng.uniform(0.004, 0.012) * np.sin(2 * np.pi * (xx * np.cos(theta) + yy * np.sin(theta)) / rng.uniform(5.0, 9.0))
    rgb *= (texture * moire)[..., None]

    # 顶灯/窗户反光
    sx, sy = rng.uniform(0.2, 0.9) * Wb, rng.uniform(0.1, 0.6) * Hb
    sigma = rng.uniform(0.12, 0.28) * Wb
    sheen = np.exp(-(((xx - sx) ** 2 + (yy - sy) ** 2) / (2 * sigma**2))).astype(np.float32)
    rgb += (sheen * rng.uniform(0.04, 0.10))[..., None]

    # 噪声
    rgb += nrng.normal(0, rng.uniform(0.004, 0.012), (Hb, Wb, 1)).astype(np.float32)
    rgb = np.clip(rgb, 0, 1)

    arr[..., :3] = rgb * 255.0
    warped = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    warped = warped.filter(ImageFilter.GaussianBlur(rng.uniform(0.65, 1.45)))

    mask = warped.getchannel("A")

    # 先铺一块略大于屏幕的白色底板，盖住旧课件边缘残留
    cx = sum(p[0] for p in quad) / 4
    cy = sum(p[1] for p in quad) / 4
    plate_pts = []
    for x, y in quad:
        sy = plate_bottom if y > cy else 1.018
        plate_pts.append((cx + (x - cx) * 1.018, cy + (y - cy) * sy))
    plate_mask = Image.new("L", (Wb, Hb), 0)
    ImageDraw.Draw(plate_mask).polygon(plate_pts, fill=255)
    plate_mask = plate_mask.filter(ImageFilter.GaussianBlur(1.2))
    bg = Image.composite(Image.new("RGB", (Wb, Hb), (242, 240, 232)), bg, plate_mask)

    # 屏幕外溢光
    glow = mask.filter(ImageFilter.GaussianBlur(40))
    glow_color = Image.new("RGB", (Wb, Hb), (245, 242, 230))
    bg = Image.composite(glow_color, bg, glow.point(lambda v: int(v * 0.10)))

    out = bg.convert("RGBA")
    out.alpha_composite(warped)
    out = out.convert("RGB")

    # 围绕屏幕裁一张 4:3 近景，贴近自采 PPT 照片的取景
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    bw, bh = maxx - minx, maxy - miny
    scale = rng.uniform(1.32, 1.62)
    cw, ch = bw * scale, bh * scale
    if cw / ch < 4 / 3:
        cw = ch * 4 / 3
    else:
        ch = cw * 3 / 4
    cx = (minx + maxx) / 2 + rng.uniform(-0.04, 0.04) * bw
    cy = (miny + maxy) / 2 + rng.uniform(-0.04, 0.04) * bh
    cw, ch = min(cw, Wb), min(ch, Hb)
    if cw / ch < 4 / 3:
        cw = min(Wb, ch * 4 / 3)
    else:
        ch = min(Hb, cw * 3 / 4)
    x1 = int(round(min(max(cx - cw / 2, 0), Wb - cw)))
    y1 = int(round(min(max(cy - ch / 2, 0), Hb - ch)))
    crop = out.crop((x1, y1, x1 + int(cw), y1 + int(ch))).resize((1280, 960), Image.LANCZOS)
    crop = crop.filter(ImageFilter.GaussianBlur(rng.uniform(0.15, 0.45)))
    carr = np.asarray(crop).astype(np.float32)
    carr += nrng.normal(0, rng.uniform(1.2, 3.0), carr.shape[:2] + (1,)).astype(np.float32)
    crop = Image.fromarray(np.clip(carr, 0, 255).astype(np.uint8), "RGB")
    return crop


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def load_backgrounds(path: Path | None = None) -> list[dict]:
    if path is not None and path.is_file():
        rows = []
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                p = Path(row["path"])
                if not p.is_absolute():
                    p = ROOT / p
                if not p.is_file():
                    continue
                quad = None
                if row.get("quad"):
                    try:
                        quad = [tuple(map(float, pt)) for pt in json.loads(row["quad"])]
                    except (ValueError, TypeError):
                        quad = None
                rows.append(
                    {
                        "background_id": row["background_id"],
                        "path": p,
                        "bbox": (float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])),
                        "quad": quad,
                        "source": row.get("source", ""),
                        "orig_label": row.get("orig_label", ""),
                        "group": row.get("doc_page_id", ""),
                    }
                )
        if len(rows) < 4:
            raise SystemExit(f"背景清单可用行不足: {path} -> {len(rows)}")
        return rows

    wanted = {
        "111_000056.jpg", "111_000060.jpg", "111_000061.jpg",
        "111_000952.jpg", "111_000953.jpg", "111_000954.jpg",
        "111_001266.jpg", "116_001726.jpg", "132_001287.jpg", "133_000892.jpg",
    }
    rows = []
    with SCB_MANIFEST.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if Path(row["path"]).name not in wanted:
                continue
            p = ROOT / row["path"]
            if not p.is_file():
                continue
            with Image.open(p) as im:
                if im.size != (1920, 1080):
                    continue
            rows.append(
                {
                    "background_id": Path(row["path"]).stem,
                    "path": p,
                    "bbox": (float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])),
                    "quad": None,
                    "source": "SCB-Dataset-teacher",
                    "orig_label": "screen",
                    "group": "",
                }
            )
    rows.sort(key=lambda r: r["path"].name)
    if len(rows) < 6:
        raise SystemExit(f"可用教室背景不足：{len(rows)}")
    return rows


def build_gallery(out: Path, records: list[dict]) -> None:
    cards = []
    for r in records:
        rel_slide = r["slide_path"]
        rel_proj = r["path"]
        cards.append(
            f"""
    <article class="card">
      <div class="pair">
        <figure><img src="{html.escape(rel_slide)}" alt="slide"><figcaption>课件原图</figcaption></figure>
        <figure><img src="{html.escape(rel_proj)}" alt="projected"><figcaption>投影合成</figcaption></figure>
      </div>
      <div class="meta">
        <span class="badge {r['label']}">{r['label']}</span>
        <span>{html.escape(r['content_id'])}</span>
        <span class="tpl">{html.escape(r['template'])}</span>
      </div>
    </article>"""
        )
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>合成投影 PPT 示例 v1</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; padding: 28px 32px 60px; font: 14px/1.5 -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif; background: #f3f4f6; color: #1f2937; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  p.lead {{ color: #4b5563; margin: 0 0 24px; max-width: 980px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(520px, 1fr)); gap: 22px; }}
  .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
  .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: #e5e7eb; }}
  figure {{ margin: 0; background: #111827; }}
  figure img {{ display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; }}
  figcaption {{ font-size: 11px; color: #d1d5db; padding: 4px 8px; background: #1f2937; }}
  .meta {{ display: flex; gap: 10px; align-items: center; padding: 8px 10px; font-size: 12px; color: #4b5563; }}
  .badge {{ padding: 1px 7px; border-radius: 999px; color: #fff; font-weight: 600; }}
  .badge.text {{ background: #2563eb; }}
  .badge.formula {{ background: #b45309; }}
  .tpl {{ margin-left: auto; color: #9ca3af; }}
</style>
</head>
<body>
<h1>合成投影 PPT 示例 · v1</h1>
<p class="lead">左为 1280×960 课件原图，右为贴入 SCB 教室幕布后的合成结果。仅为合成效果试点，不进入训练集，也不用于评估。</p>
<div class="grid">{''.join(cards)}
</div>
</body>
</html>
"""
    (out / "gallery.html").write_text(page, encoding="utf-8")


def preview_subset(records: list[dict], per_label: int = 12) -> list[dict]:
    text = [r for r in records if r["label"] == "text"][:per_label]
    formula = [r for r in records if r["label"] == "formula"][:per_label]
    return text + formula


def build_preview(out: Path, records: list[dict], name: str, cols: int = 6) -> Path:
    picks = preview_subset(records)
    thumb_w, thumb_h = 300, 225
    pad = 10
    rows = math.ceil(len(picks) / cols)
    sheet = Image.new("RGB", (cols * (thumb_w + pad) + pad, rows * (thumb_h + 34) + pad), (28, 30, 36))
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(picks):
        with Image.open(out / r["path"]) as im:
            im = im.convert("RGB")
            im.thumbnail((thumb_w, thumb_h))
        x = pad + (i % cols) * (thumb_w + pad)
        y = pad + (i // cols) * (thumb_h + 34)
        sheet.paste(im, (x, y))
        tag = f"{r['label']} · {r['content_id']}"
        d.text((x + 2, y + thumb_h + 8), tag, font=hiragino(14), fill=(225, 228, 235))
    path = out / name
    sheet.save(path, quality=88)
    return path


def build_layout_sheet(out: Path, records: list[dict], name: str = "layouts.jpg") -> Path:
    picks = preview_subset(records)
    thumb_w, thumb_h = 400, 300
    pad = 10
    rows = math.ceil(len(picks) / 4)
    sheet = Image.new("RGB", (4 * (thumb_w + pad) + pad, rows * (thumb_h + 30) + pad), (28, 30, 36))
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(picks):
        with Image.open(out / r["slide_path"]) as im:
            im = im.convert("RGB").resize((thumb_w, thumb_h), Image.LANCZOS)
        x = pad + (i % 4) * (thumb_w + pad)
        y = pad + (i // 4) * (thumb_h + 30)
        sheet.paste(im, (x, y))
        d.text((x + 2, y + thumb_h + 7), f"{r['label']} · {r['content_id']}", font=hiragino(13), fill=(225, 228, 235))
    path = out / name
    sheet.save(path, quality=90)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--n-per-class", type=int, default=12)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--limit-text", type=int, default=0)
    parser.add_argument("--limit-formula", type=int, default=0)
    parser.add_argument(
        "--background-manifest",
        type=Path,
        default=None,
        help="背景清单；缺省用内置 SCB 背景（兼容 v1）",
    )
    parser.add_argument("--id-prefix", default="syn-ppt", help="样本 ID 前缀")
    parser.add_argument("--plate-bottom", type=float, default=1.018, help="底板向下扩展比例，用于盖住屏幕底部旧内容")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    (out / "slides").mkdir(parents=True, exist_ok=True)
    (out / "projected").mkdir(parents=True, exist_ok=True)

    background_path = args.background_manifest
    if background_path is not None and not background_path.is_absolute():
        background_path = ROOT / background_path
    backgrounds = load_backgrounds(background_path)
    text_items = TEXT_ITEMS[: args.limit_text or len(TEXT_ITEMS)]
    formula_items = FORMULA_ITEMS[: args.limit_formula or len(FORMULA_ITEMS)]

    templates = ["purple", "paper", "white", "teal"]
    if args.n_per_class % len(templates) != 0:
        raise SystemExit("--n-per-class 必须能被 4 整除，才能做模板×类别平衡")
    per_cell = args.n_per_class // len(templates)
    plan: list[tuple[str, dict]] = []
    for template in templates:
        for label, items in (("text", text_items), ("formula", formula_items)):
            for i in range(per_cell):
                item = dict(items[i % len(items)])
                item["template"] = template
                plan.append((label, item))
    rng.shuffle(plan)

    bg_pool = backgrounds[:]
    rng.shuffle(bg_pool)
    records = []
    for idx, (label, item) in enumerate(plan):
        seed = rng.randrange(1, 10**9)
        local = random.Random(seed)
        page = 12 + idx
        if label == "text":
            slide = render_text_slide(item, local, page)
        else:
            slide = render_formula_slide(item, local, page)
        sample_id = f"{args.id_prefix}-{idx:03d}"
        slide_rel = f"slides/{sample_id}.png"
        slide.save(out / slide_rel, optimize=True)

        bg_info = bg_pool[idx % len(bg_pool)]
        bg = Image.open(bg_info["path"]).convert("RGB")
        bg.thumbnail((1920, 1440), Image.LANCZOS)
        quad = _quad_from_bbox(bg_info["bbox"], bg.size, local, bg_info.get("quad"))
        projected = project_slide(bg, slide, quad, local, plate_bottom=args.plate_bottom)
        proj_rel = f"projected/{sample_id}.jpg"
        projected.save(out / proj_rel, quality=local.randint(76, 90), optimize=True)

        records.append(
            {
                "sample_id": sample_id,
                "path": proj_rel,
                "slide_path": slide_rel,
                "label": label,
                "content_id": item["id"],
                "template": item["template"],
                "background": bg_info["path"].name,
                "background_id": bg_info["background_id"],
                "background_source": bg_info["source"],
                "background_orig_label": bg_info["orig_label"],
                "background_group": bg_info.get("group", ""),
                "image_source": "synthetic",
                "label_source": "layout_generator",
                "width": 1280,
                "height": 960,
                "seed": seed,
            }
        )

    with (out / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    build_gallery(out, records)
    preview = build_preview(out, records, "preview.jpg")
    layouts = build_layout_sheet(out, records)

    print(f"生成 {len(records)} 组（text {sum(r['label']=='text' for r in records)} / formula {sum(r['label']=='formula' for r in records)}）")
    print(f"输出目录：{out}")
    print(f"预览：{preview}")
    print(f"版式：{layouts}")
    print(f"画廊：{out / 'gallery.html'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
