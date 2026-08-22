# -*- coding: utf-8 -*-
"""節ごとに何行使っているかを出す（どこを削れば2ページに入るかの判断用）。"""
import io, re, sys, math, unicodedata

BS = chr(92)
COL = 237.6 / 10.0          # 1段の幅（全角換算）
CAP = 49.2 * 2 * 2          # 2ページぶんの行数


def strip_tex(t):
    t = re.sub(r"(?<!\\)%.*", "", t)
    t = re.sub(re.escape(BS) + r"(textbf|textit|emph)\{([^{}]*)\}", r"\2", t)
    t = re.sub(re.escape(BS) + r"cite\{[^}]*\}", "[9]", t)
    t = re.sub(re.escape(BS) + r"ref\{[^}]*\}", "1", t)
    t = re.sub(r"\$[^$]*\$", "XXXX", t)
    t = t.replace(BS + "%", "%")
    t = re.sub(re.escape(BS) + r"[a-zA-Z@]+\s*", "", t)
    return t.replace("{", "").replace("}", "").replace("~", " ")


def w(t):
    return sum(1.0 if unicodedata.east_asian_width(c) in "WFA"
               else (0.25 if c in " \t" else 0.5) for c in t)


def lines_of(chunk):
    n = 0.0
    n += len(re.findall(re.escape(BS) + r"subsection\{", chunk)) * 1.7
    for tb in re.findall(re.escape(BS) + r"begin\{table\}(.*?)" + re.escape(BS)
                         + r"end\{table\}", chunk, re.S):
        cap = re.search(re.escape(BS) + r"caption\{(.*?)\}\s*\n", tb, re.S)
        n += math.ceil(w(strip_tex(cap.group(1))) / (COL / 0.8)) if cap else 0
        n += len(re.findall(r"\\\\", tb)) * 0.8 + 3.5
    chunk = re.sub(re.escape(BS) + r"begin\{table\}.*?" + re.escape(BS)
                   + r"end\{table\}", "", chunk, flags=re.S)
    n += chunk.count(BS + "begin{equation}") * 3.5
    chunk = re.sub(re.escape(BS) + r"begin\{equation\}.*?" + re.escape(BS)
                   + r"end\{equation\}", "", chunk, flags=re.S)
    for it in re.findall(re.escape(BS) + r"item\s(.*?)(?=" + re.escape(BS) + r"item|"
                         + re.escape(BS) + r"end\{itemize\})", chunk, re.S):
        n += math.ceil(w(strip_tex(it)) / (COL - 1.5)) + 0.3
    chunk = re.sub(re.escape(BS) + r"begin\{itemize\}.*?" + re.escape(BS)
                   + r"end\{itemize\}", "", chunk, flags=re.S)
    chunk = re.sub(re.escape(BS) + r"(sub)?section\{[^}]*\}", "", chunk)
    for para in re.split(r"\n\s*\n", chunk):
        t = strip_tex(para).strip()
        if t:
            n += math.ceil(w(t) / COL)
    return n


s = io.open(sys.argv[1], encoding="utf-8").read()
body = s.split(BS + "begin{document}")[1]
body = body[re.search(re.escape(BS) + r"footnotetext\{[^}]*\}", body).end():]
body, bib = body.split(BS + "begin{thebibliography}", 1)

parts = re.split(r"(" + re.escape(BS) + r"section\{[^}]*\})", body)
rows, total = [], 16.0 + 3.0        # 表題ブロック＋脚注
rows.append(("表題ブロック・脚注", 19.0))
for i in range(1, len(parts), 2):
    title = re.search(r"\{([^}]*)\}", parts[i]).group(1)
    n = 2.4 + lines_of(parts[i + 1])
    rows.append((title, n))
    total += n
nb = 0.0
for e in re.findall(re.escape(BS) + r"bibitem\{[^}]*\}(.*?)(?=" + re.escape(BS)
                    + r"bibitem|$)", bib, re.S):
    nb += math.ceil(w(strip_tex(e)) / (COL / 0.8)) * 0.8
rows.append(("参考文献（%d件）" % len(re.findall(re.escape(BS) + r"bibitem", bib)), nb))
total += nb

print("%-24s %7s %7s" % ("箇所", "行数", "割合"))
for t, n in rows:
    print("%-24s %7.1f %6.0f%%" % (t, n, 100 * n / total))
print("-" * 42)
print("%-24s %7.1f  （2ページ＝%.0f行）" % ("合計", total, CAP))
print("見込み %.2f ページ（旧版較正 ×1.10 込み）" % (total / CAP * 2 * 1.10))
print("2ページに入れるには あと %.0f 行 削る必要がある" % max(0, total - CAP / 1.10))
