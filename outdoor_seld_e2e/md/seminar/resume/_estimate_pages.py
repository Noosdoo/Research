# -*- coding: utf-8 -*-
"""LaTeX 2段組レジュメのページ数を行数から見積もる。

LaTeXが手元に無いので、段幅を「全角何文字ぶんか」で表し、段落ごとに
行数を積む。既知の出力（旧版=3ページ）で較正してから新版に当てる。
"""
import io, re, sys, math, unicodedata

BS = chr(92)


def strip_tex(t):
    """本文として刷られる文字列に近づける。"""
    t = re.sub(r"(?<!\\)%.*", "", t)                       # コメント
    t = re.sub(re.escape(BS) + r"(textbf|textit|emph|mathrm|bm|small|footnotesize)"
               r"\{([^{}]*)\}", r"\2", t)
    t = re.sub(re.escape(BS) + r"cite\{[^}]*\}", "[9]", t)  # [9] 相当の幅
    t = re.sub(re.escape(BS) + r"ref\{[^}]*\}", "1", t)
    t = re.sub(re.escape(BS) + r"label\{[^}]*\}", "", t)
    t = re.sub(r"\$[^$]*\$", "XXXX", t)                     # 数式は4字ぶん
    t = t.replace(BS + "%", "%").replace(BS + "&", "&")
    t = re.sub(re.escape(BS) + r"[a-zA-Z@]+\s*", "", t)     # 残りの命令
    t = t.replace("{", "").replace("}", "").replace("~", " ")
    return t


def width_zw(t):
    """全角換算の幅。"""
    w = 0.0
    for ch in t:
        if ch in " \t":
            w += 0.25
        elif unicodedata.east_asian_width(ch) in ("W", "F", "A"):
            w += 1.0
        else:
            w += 0.5
    return w


def count_lines(tex, col_zw, verbose=False):
    """段組1段あたり col_zw 文字として、必要な行数を返す。"""
    body = tex.split(BS + "begin{document}")[1]
    body = body.split(BS + "end{document}")[0]
    # 表題ブロック（\twocolumn[...]）は全段幅なので別勘定
    m = re.search(re.escape(BS) + r"twocolumn\[(.*?)\n\]", body, re.S)
    head_lines = 0.0
    if m:
        head_lines = 16.0        # 日付・2行の大見出し・氏名・ローマ字＋余白（実測見合い）
        body = body[m.end():]
    body += ""
    total = head_lines + 3.0     # 脚注（所属）

    # 参考文献を切り離す
    bib = ""
    if BS + "begin{thebibliography}" in body:
        body, bib = body.split(BS + "begin{thebibliography}", 1)

    # 表を切り離す
    tables = re.findall(re.escape(BS) + r"begin\{table\}(.*?)" + re.escape(BS) + r"end\{table\}",
                        body, re.S)
    body = re.sub(re.escape(BS) + r"begin\{table\}.*?" + re.escape(BS) + r"end\{table\}",
                  "", body, flags=re.S)
    for t in tables:
        cap = strip_tex(re.search(re.escape(BS) + r"caption\{(.*?)\}\s*\n", t, re.S).group(1))
        rows = len(re.findall(r"\\\\", t))
        total += math.ceil(width_zw(cap) / (col_zw / 0.8)) + rows * 0.8 + 3.5

    # 数式
    n_eq = body.count(BS + "begin{equation}")
    total += n_eq * 3.5
    body = re.sub(re.escape(BS) + r"begin\{equation\}.*?" + re.escape(BS) + r"end\{equation\}",
                  "", body, flags=re.S)

    # 見出し
    total += len(re.findall(re.escape(BS) + r"section\{", body)) * 2.4
    total += len(re.findall(re.escape(BS) + r"subsection\{", body)) * 1.7
    body = re.sub(re.escape(BS) + r"(sub)?section\{[^}]*\}", "", body)

    # itemize（字下げぶん段幅が狭くなる）
    items = re.findall(re.escape(BS) + r"item\s(.*?)(?=" + re.escape(BS) + r"item|"
                       + re.escape(BS) + r"end\{itemize\})", body, re.S)
    for it in items:
        total += math.ceil(width_zw(strip_tex(it)) / (col_zw - 1.5)) + 0.3
    body = re.sub(re.escape(BS) + r"begin\{itemize\}.*?" + re.escape(BS) + r"end\{itemize\}",
                  "", body, flags=re.S)

    # 本文の段落
    for para in re.split(r"\n\s*\n", body):
        txt = strip_tex(para).strip()
        if not txt:
            continue
        total += math.ceil(width_zw(txt) / col_zw)

    # 参考文献（\footnotesize or \small。字が小さいぶん詰まる）
    if bib:
        small = 0.8 if BS + "footnotesize" in bib[:60] else 0.9
        for e in re.findall(re.escape(BS) + r"bibitem\{[^}]*\}(.*?)(?=" + re.escape(BS)
                            + r"bibitem|" + re.escape(BS) + r"end\{thebibliography\})", bib, re.S):
            n = math.ceil(width_zw(strip_tex(e)) / (col_zw / small))
            total += n * small
    return total


def report(path, col_zw, lines_per_col, tag):
    tex = io.open(path, encoding="utf-8").read()
    L = count_lines(tex, col_zw)
    cap = lines_per_col * 2
    print("%-22s 必要 %6.1f 行 / 1ページ %d 行 → %.2f ページ" % (tag, L, cap, L / cap))
    return L / cap


if __name__ == "__main__":
    print("== 較正: 旧版（jsarticle 9pt・実際の出力は3ページ、3ページ目に文献[4]-[9]） ==")
    old = report(sys.argv[1], 240 / 9.0, 48.7, "旧版")
    print("   実際は約 2.15 ページ相当 → 補正係数 %.3f" % (2.15 / old))
    k = 2.15 / old
    print()
    print("== 新版（jarticle 10pt・テンプレート） ==")
    new = report(sys.argv[2], 237.6 / 10.0, 49.2, "新版")
    print("   補正後の見込み: %.2f ページ" % (new * k))
