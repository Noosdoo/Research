# -*- coding: utf-8 -*-
"""検証スライド「通知はいつ・どれだけ届くか」（2026-08-20）。

## 方針: 初見の聴衆に向けて書く

聞き手は全員この研究を初めて見る。**「前のやり方」「改良した」は内輪の話**であって、
聴衆には関係がない。before/after を並べると、知らない旧方式の説明から始める羽目になり、
限られた時間を自分の開発史に使ってしまう。

したがってこの1枚は **いまのシステムがどう動くか**だけを述べる:

  - 危険な車が一番近づく 0.80秒前に警告が届く
  - 1.5m以内まで近づく危険な車の 85.0% に警告が届いた
  - 安全な車の 85.2% は鳴らさずに済んだ

8/4のゼミでいただいた「3秒前に検知できても使えない」という指摘への答えでもあるが、
**それはスライドに書かず、口頭で添える**。指摘した本人は0.8秒の意味が分かる。

出力: md/seminar/図_検証_通知層_簡潔_2026-08-20.pptx
"""
from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

W, H = 960, 540
INK = RGBColor(0x16, 0x23, 0x3A)
INK2 = RGBColor(0x3A, 0x46, 0x58)
MUTED = RGBColor(0x66, 0x70, 0x7F)
HAIR = RGBColor(0xD9, 0xDA, 0xD2)
RED = RGBColor(0xC4, 0x43, 0x2B)
GREEN = RGBColor(0x2F, 0x7D, 0x6D)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CHIP = RGBColor(0xF3, 0xF3, 0xEF)
JP = "游ゴシック"

prs = Presentation()
prs.slide_width, prs.slide_height = Emu(int(W * 12700)), Emu(int(H * 12700))
sl = prs.slides.add_slide(prs.slide_layouts[6])


def _font(run, size, bold, color):
    f = run.font
    f.name, f.size, f.bold = JP, Pt(size), bold
    f.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", JP)


def box(x, y, w, h):
    tb = sl.shapes.add_textbox(Emu(int(x * 12700)), Emu(int(y * 12700)),
                               Emu(int(w * 12700)), Emu(int(h * 12700)))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tb


def para(tf, runs, size=13, bold=False, color=INK2, align=PP_ALIGN.LEFT,
         first=False, line=1.3, space=2):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment, p.line_spacing, p.space_after = align, line, Pt(space)
    for text, kw in ([(runs, {})] if isinstance(runs, str) else runs):
        r = p.add_run()
        r.text = text
        _font(r, kw.get("size", size), kw.get("bold", bold), kw.get("color", color))
    return p


def rect(x, y, w, h, fill=None, line=None, lw=1.0, shape=MSO_SHAPE.RECTANGLE):
    s = sl.shapes.add_shape(shape, Emu(int(x * 12700)), Emu(int(y * 12700)),
                            Emu(int(w * 12700)), Emu(int(h * 12700)))
    s.shadow.inherit = False
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(lw)
    tf = s.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(12)
    tf.margin_top = tf.margin_bottom = Pt(9)
    tf.vertical_anchor = MSO_ANCHOR.TOP
    return s


def line(x1, y1, x2, y2, color, w=2.0, arrow=False):
    c = sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Emu(int(x1 * 12700)),
                                Emu(int(y1 * 12700)), Emu(int(x2 * 12700)),
                                Emu(int(y2 * 12700)))
    c.shadow.inherit = False
    c.line.color.rgb = color
    c.line.width = Pt(w)
    if arrow:
        ln = c.line._get_or_add_ln()
        ln.append(ln.makeelement(qn("a:tailEnd"),
                                 {"type": "triangle", "w": "med", "len": "med"}))
    return c


def label(x, y, w, text, size=11, color=MUTED, align=PP_ALIGN.LEFT, bold=False):
    tb = box(x, y, w, 20)
    tb.text_frame.word_wrap = False
    para(tb.text_frame, text, size=size, bold=bold, color=color, align=align,
         first=True, space=0)


# ============ 見出し ============
line(54, 96, W - 54, 96, INK, 1.5)
tb = box(54, 40, 860, 48)
para(tb.text_frame, "検 証 ― 通 知 は い つ ・ ど れ だ け 届 く か",
     size=26, bold=True, color=INK, first=True, space=0)

# ============ 図: 警告から最接近までの余裕 ============
X0, X1 = 300, 812                 # X1 = 車が一番近づく位置
AY = 218
FIRE = X0 + 96                    # 警告が鳴る位置
label(54, 108, 420, "危険な車が近づいてくるとき、警告はいつ届くか",
      size=13.5, color=INK2, bold=True)

line(X0, AY, X1 + 40, AY, INK, 3.0, arrow=True)
label(X1 + 6, AY + 16, 120, "時間", size=11, color=MUTED)

# 車が一番近づく瞬間
line(X1, AY - 56, X1, AY + 30, MUTED, 1.5)
rect(X1 - 13, AY - 13, 26, 26, fill=RED, shape=MSO_SHAPE.OVAL)
label(X1 - 90, AY - 82, 180, "車が一番近づく", size=13.5, color=RED,
      align=PP_ALIGN.CENTER, bold=True)

# 警告
line(FIRE, AY - 56, FIRE, AY + 30, MUTED, 1.5)
rect(FIRE - 13, AY - 13, 26, 26, fill=GREEN, shape=MSO_SHAPE.OVAL)
label(FIRE - 90, AY - 82, 180, "警告が届く", size=13.5, color=GREEN,
      align=PP_ALIGN.CENTER, bold=True)

# 余裕の帯
rect(FIRE, AY + 40, X1 - FIRE, 34, fill=CHIP, line=GREEN, lw=1.5)
label(FIRE, AY + 47, X1 - FIRE, "0.80 秒 の 余 裕", size=16, color=GREEN,
      align=PP_ALIGN.CENTER, bold=True)
label(FIRE, AY + 80, X1 - FIRE, "（中央値）", size=11, color=MUTED,
      align=PP_ALIGN.CENTER)

# ============ 数字 ============
NUMS = [
    (54, ["1.5m以内まで近づく危険な車のうち", "警告が届いた割合"], "85.0 %"),
    (365, ["3.2mより遠くを通る安全な車のうち", "鳴らさずに済んだ割合"], "85.2 %"),
    (676, ["静音なキックボードのうち", "警告が届いた割合"], "88.7 %"),
]
for x, ttl, num in NUMS:
    c = rect(x, 356, 230, 104, fill=WHITE, line=HAIR)
    for i, t in enumerate(ttl):
        para(c.text_frame, t, size=11.5, color=INK2, first=(i == 0), space=1)
    para(c.text_frame, num, size=27, bold=True, color=GREEN,
         align=PP_ALIGN.CENTER, space=0)
label(54, 476, 860,
      "学習にも検証にも使っていない1,800クリップで、1回だけ採点した値",
      size=11.5, color=MUTED)
label(54, 502, 860,
      "「全部鳴らす」でも「近づくまで黙る」でもなく、鳴らす相手と鳴らす時刻を選ぶ",
      size=13.5, color=INK, bold=True)

out = ROOT / "md/seminar/図_検証_通知層_簡潔_2026-08-20.pptx"
try:
    prs.save(out)
except PermissionError:
    out = out.with_name(out.stem + "_新" + out.suffix)
    prs.save(out)
    print("※ 元ファイルが開かれていたため別名で保存した")
print(f"saved: {out} ({out.stat().st_size // 1024} KB)")
