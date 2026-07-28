import sys, re
from collections import Counter

def parse(word):
    tokens = re.findall(r"([A-Za-z])\s*(\^?-1|['-])?", word.replace(" ", ""))
    return [(ch, -1 if inv else +1) for ch, inv in tokens if ch]

def classify(word):
    edges = parse(word); n = len(edges)
    cnt = Counter(ch for ch, _ in edges)
    bad = [ch for ch, c in cnt.items() if c != 2]
    if bad:
        return f"エラー: ラベル {bad} が2回ずつ現れていません"
    # --- 向き付け可能性 ---
    sign, orientable = {}, True
    for ch, s in edges:
        if ch in sign and sign[ch] == s:
            orientable = False
        sign[ch] = s
    # --- 頂点数 V (Union-Find) ---
    parent = list(range(n))
    def find(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]; v = parent[v]
        return v
    def union(u, v):
        parent[find(u)] = find(v)
    occ = {}
    for i, (ch, s) in enumerate(edges):
        tail, head = (i, (i+1) % n) if s == +1 else ((i+1) % n, i)
        if ch in occ:
            t0, h0 = occ[ch]
            union(t0, tail); union(h0, head)
        else:
            occ[ch] = (tail, head)
    V = len({find(v) for v in range(n)}); E = n // 2; F = 1
    chi = V - E + F
    # --- 分類 ---
    if orientable:
        name = "S^2 (球面)" if chi == 2 else f"T^2({(2-chi)//2})"
    else:
        name = f"P^2({2-chi})"
    return (f"表示式: {word}\n  V={V}, E={E}, F={F}, χ=V-E+F={chi}\n"
            f"  向き付け可能性: {'可能' if orientable else '不可能(同符号の組あり)'}\n"
            f"  ⇒ この閉曲面は {name}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(classify(sys.argv[1]))
    else:
        for w in ["aa'", "abab", "aabb", "aba'b'", "aabcb'c'", "abcda'ce'be'd'"]:
            print(classify(w)); print()