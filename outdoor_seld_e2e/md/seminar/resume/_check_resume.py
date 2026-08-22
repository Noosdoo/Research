# -*- coding: utf-8 -*-
"""夏ゼミレジュメの自己点検（講座の指示に対する確認）"""
import io, re, sys

p = sys.argv[1]
s = io.open(p, encoding="utf-8").read()
body = s.split(r"\begin{document}")[1]
body_nc = "\n".join(l for l in body.split("\n") if not l.lstrip().startswith("%"))

print("== 句読点の統一（講座: 「、。」か「，．」のどちらかに統一） ==")
for ch, name in [("、", "読点 、"), ("。", "句点 。")]:
    n = body_nc.count(ch)
    print("   %s の数: %d  %s" % (name, n, "★混在している" if n else "OK"))
bad = re.findall(r"[ぁ-んァ-ヶ一-龥][.]", body_nc)
print("   和文の直後に半角ピリオド: %d %s" % (len(bad), bad[:5] if bad else "OK"))

print("== 引用と参考文献（講座: 参考文献は後ろにつける） ==")
cites = set(re.findall(re.escape("\\cite") + r"\{([^}]*)\}", s))
items = re.findall(re.escape("\\bibitem") + r"\{([^}]*)\}", s)
print("   引用キー %d 種 / 文献 %d 件" % (len(cites), len(items)))
print("   本文から引かれていない文献:", sorted(set(items) - cites) or "なし")
print("   文献が無い引用:", sorted(cites - set(items)) or "なし")
print("   文献の重複:", [k for k in set(items) if items.count(k) > 1] or "なし")
print("   文献は末尾にあるか:",
      "OK" if s.index("\\begin{thebibliography}") > s.rindex("\\section{") else "★本文より前")

print("== 図表（講座: 表は上にキャプション／必ず本文で言及） ==")
labs = set(re.findall(re.escape("\\label") + r"\{([^}]*)\}", s))
refs = set(re.findall(re.escape("\\ref") + r"\{([^}]*)\}", s))
print("   本文で言及していない表:", sorted(labs - refs) or "なし（すべて言及済み）")
print("   対応する表が無い参照:", sorted(refs - labs) or "なし")
for i, m in enumerate(re.finditer(r"\\begin\{table\}(.*?)\\end\{table\}", s, re.S), 1):
    t = m.group(1)
    ci, ti = t.find("\\caption"), t.find("\\begin{tabular}")
    print("   表%d のキャプション位置:" % i, "表の上 OK" if 0 <= ci < ti else "★表の下")

print("== 構造 ==")
ok = True
for env in ("document", "center", "flushright", "itemize", "equation",
            "table", "tabular", "thebibliography"):
    b, e = s.count("\\begin{%s}" % env), s.count("\\end{%s}" % env)
    if b != e:
        ok = False
    print("   %-16s begin=%d end=%d %s" % (env, b, e, "OK" if b == e else "★不一致"))
print("   波括弧の差:", s.count("{") - s.count("}"), "(テンプレートと同じなら問題なし)")
secs = re.findall(re.escape("\\section") + r"\{([^}]*)\}", s)
print("   節構成:", " / ".join("%d.%s" % (i, t) for i, t in enumerate(secs, 1)))

print("== 分量のめやす ==")
prose = re.sub(r"\\begin\{table\}.*?\\end\{table\}", "", body_nc, flags=re.S)
prose = prose.split("\\begin{thebibliography}")[0]
n = len(re.findall("[ぁ-んァ-ヶ一-龥ー，．（）]", prose))
print("   本文の和文字数（表・文献を除く）: %d" % n)
print("   ※ 10pt・段幅8.35cm では 1段あたり約23字×49行。2ページの本文枠は概算2,100字前後")
