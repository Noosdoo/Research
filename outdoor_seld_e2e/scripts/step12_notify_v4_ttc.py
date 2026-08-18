# -*- coding: utf-8 -*-
"""通知規則 v4 — **到達時間(TTC)で鳴らす**（2026-08-18 新規。v3.4は残す）。

## なぜ作るか

v3.4 までの通知は **推定距離のしきい値だけ**で判定していた:

    if d <= 1.5: 強 / elif d <= 3.2: 中 / else: 抑制

これは**速度を一切見ていない**。結果として:

  - 時速50kmのトラックが20m先から接近 → 「距離3.2m超＝安全」で黙る。
    3m以内に入って初めて鳴るが、そのときは通過 0.2 秒前
  - 遠ざかっている車にも（距離が近ければ）鳴りうる

中間発表で「トラックが来る3秒前に検知できても使えない」という指摘を受けた箇所であり、
**リードタイムが相手の速さに反比例して縮む**のが構造的な問題だった。

## v4 の規則

距離の系列 d(t) から接近速度 v = −ḋ を推定し、**危険域に入るまでの時間**で判定する:

    TTC = (d − r_danger) / v        （v > 0 = 接近中のときのみ）
    TTC <= TTC_WARN(既定2.5s) かつ CONFIRM フレーム連続 → 警告

  - 遠くても速ければ鳴る（速さによらずリードタイムが一定になる）
  - **遠ざかっている（v <= 0）相手には鳴らさない**
  - 2.5秒は既存の根拠（人間の知覚反応時間・AASHTO / 車載FCW約2.6秒）をそのまま使う

距離しきい値は完全には捨てず、**保険**として残す（速度推定が使えないほど d が
不安定なとき、または既に危険域内にいるときは距離規則で鳴らす）。

## 速度推定

d(t) は推定値なのでノイズが乗る。直近 VEL_WIN フレームの**最小二乗直線の傾き**を
ḋ とする（単純差分より頑健）。窓が埋まるまでは判定しない＝**検知遅れが
0.2秒（v3.4の2フレーム確認）から VEL_WIN×0.1 秒へ増える**。これは
「数フレーム待つ代わりに数秒のリードを得る」トレードオフであり、評価で定量する。

## 使い方

    python scripts/step12_notify_v4_ttc.py <pred_val_all.csv> <出力dir> [--rule ttc|dist|both]

v3.4 と同一の入力・同一の出力形式なので、既存の採点・比較にそのまま乗る。
`--rule dist` は v3.4 相当の距離規則（回帰確認用）。既定は `both`（両方出して比較）。
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FPS = 10.0
CAR = 4
DIST_CLASSES = {4, 6, 7}          # car / kick / bike（距離を持つクラス）

# ---- v3.4 から引き継ぐ設計定数（変更しない）----
T3, T2, SUPP = 1.5, 3.0, 3.2      # 強/中の距離しきい値・抑制境界
AZ_MATCH = 25.0                   # エピソード統合の方位幅
LINK_DEG = 60.0                   # v3.4のトリガ連結幅
CONFIRM = 2                       # 距離規則の確認フレーム数

# ---- v4 で新規に導入する定数（事前に決めて固定する）----
TTC_WARN = 2.5        # [s] 警告を出す到達時間。人間の知覚反応時間（既存根拠）
TTC_CAUTION = 4.0     # [s] 注意段の到達時間
R_DANGER = 1.5        # [m] 危険域の半径。強トリガの距離しきい値と同じ値を使う
VEL_WIN = 5           # [frame] 速度推定の窓（0.5s）。短いとノイズ、長いと遅れる
V_MIN = 0.5           # [m/s] これ未満の接近速度は「接近していない」とみなす
D_MAX_TTC = 30.0      # [m] これより遠い推定距離ではTTCを信用しない（誤差が大きい）


def cdiff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def closing_speed(dseq, j, win=VEL_WIN):
    """フレーム j までの直近 win フレームの距離から接近速度[m/s]を推定する。

    最小二乗直線の傾き ḋ を取り、v = −ḋ（正なら接近）を返す。
    窓内のサンプルが足りなければ None（＝まだ判定しない）。
    """
    ds = [dseq.get(k) for k in range(j - win + 1, j + 1)]
    if any(d is None for d in ds) or len(ds) < win:
        return None
    t = np.arange(win) / FPS
    slope = np.polyfit(t, np.asarray(ds, dtype=float), 1)[0]
    return -float(slope)


def ttc_of(d, v, r_danger=R_DANGER):
    """危険域(半径 r_danger)に入るまでの秒数。接近していなければ None。"""
    if v is None or v < V_MIN:
        return None
    if d > D_MAX_TTC:
        return None
    return max(0.0, (d - r_danger) / v)


def track_series(pred_clip, cls, nframes, link_deg=LINK_DEG):
    """1クラスぶんの (frame -> 最寄り距離, 方位) 系列を作る。

    同一物体の対応付けは v3.4 と同じ「前フレームと方位±link_deg で連結」の近似。
    複数候補があるフレームは**最も近いもの**を採る（危険側に倒す）。
    """
    d_at, az_at, prev_az = {}, {}, None
    for j in range(nframes):
        cand = [(a, d) for (c, a, d) in pred_clip.get(j, [])
                if c == cls and d is not None]
        if not cand:
            prev_az = None
            continue
        if prev_az is not None:
            linked = [(a, d) for a, d in cand if cdiff(a, prev_az) <= link_deg]
            if linked:
                cand = linked
        a, d = min(cand, key=lambda x: x[1])
        d_at[j], az_at[j], prev_az = d, a, a
    return d_at, az_at


def _trigger_stream(d_at, az_at, nframes, cond):
    """cond(j, d) が CONFIRM フレーム連続で True になったフレームを列挙する。

    v3.4 と同じく **段ごとに独立した列**を作る（強と中を1本のカウンタで混ぜない）。
    混ぜると「強→中へ変化した瞬間に中で発火」のような、v3.4に無い挙動が出る。
    """
    hits, run = [], 0
    for j in range(nframes):
        d = d_at.get(j)
        if d is None or not cond(j, d):
            run = 0
            continue
        run += 1
        if run >= CONFIRM:
            hits.append((j, az_at[j], d))
    return hits


def _episodes_with_upgrade(mid_hits, strong_hits):
    """中トリガ列をエピソード化し、内部に強トリガがあれば強へ昇格（v3.4と同一）。

    返り値: [(発火フレーム, 方位, tier, 発火時の推定距離)]（エピソード先頭が発火時刻）
    """
    strong_fr = {j for j, _a, _d in strong_hits}
    out = []
    for ep in group_episodes([(j, a, "中", None, None, d) for j, a, d in mid_hits]):
        inside = [f for f in ep if f[0] in strong_fr]
        if inside:
            j, a, _t, _tt, _v, d = inside[0]      # 強成立の因果時刻で鳴らす
            out.append((j, a, "強", d))
        else:
            j, a, _t, _tt, _v, d = ep[0]
            out.append((j, a, "中", d))
    return out


def fires_ttc(d_at, az_at, nframes):
    """v4: 到達時間で発火。強＝TTC≤TTC_WARN または既に危険域内、
    中＝TTC≤TTC_CAUTION または距離が抑制境界内。返り値は
    [(発火フレーム, 方位, tier, 発火時の推定距離)]。"""
    def _ttc(j, d):
        return ttc_of(d, closing_speed(d_at, j))

    strong = _trigger_stream(d_at, az_at, nframes,
                             lambda j, d: (_ttc(j, d) is not None
                                           and _ttc(j, d) <= TTC_WARN) or d <= T3)
    mid = _trigger_stream(d_at, az_at, nframes,
                          lambda j, d: (_ttc(j, d) is not None
                                        and _ttc(j, d) <= TTC_CAUTION) or d <= SUPP)
    return _episodes_with_upgrade(mid, strong)


def fires_dist(d_at, az_at, nframes):
    """v3.4相当（比較の土台）: 距離しきい値のみ・強/中は独立列。"""
    strong = _trigger_stream(d_at, az_at, nframes, lambda j, d: d <= T3)
    mid = _trigger_stream(d_at, az_at, nframes, lambda j, d: d <= SUPP)
    return _episodes_with_upgrade(mid, strong)


def group_episodes(fires):
    """連続フレーム＆方位±AZ_MATCH でエピソード化（v3.4と同一規則）。"""
    eps = []
    for f in fires:
        if eps and f[0] - eps[-1][-1][0] <= 1 and cdiff(f[1], eps[-1][-1][1]) <= AZ_MATCH:
            eps[-1].append(f)
        else:
            eps.append([f])
    return eps


def load_pred(path: Path):
    out = defaultdict(lambda: defaultdict(list))
    for line in open(path, encoding="utf-8"):
        p = line.strip().split(",")
        if len(p) >= 7:
            clip, k, c, az, d = p[0], int(p[1]), int(p[2]), float(p[4]), float(p[6])
        elif len(p) == 6:
            clip, k, c, az, d = p[0], int(p[1]), int(p[2]), float(p[3]), float(p[5])
        else:
            continue
        out[clip][k].append((c, az, d))
    return dict(out)


def run_rule(pred, rule: str, nframes: int = 100):
    """clip -> cls -> [episode] を返す。episodeの先頭が発火時刻。"""
    fn = fires_ttc if rule == "ttc" else fires_dist
    res = {}
    for clip, frames in pred.items():
        per_cls = {}
        for cls in DIST_CLASSES:
            d_at, az_at = track_series(frames, cls, nframes)
            if not d_at:
                continue
            eps = fn(d_at, az_at, nframes)   # 既にエピソード単位
            if eps:
                per_cls[cls] = eps
        res[clip] = per_cls
    return res


def main() -> int:
    pred_path = Path(sys.argv[1])
    outdir = Path(sys.argv[2])
    rule = "both"
    if "--rule" in sys.argv:
        rule = sys.argv[sys.argv.index("--rule") + 1]
    outdir.mkdir(parents=True, exist_ok=True)
    pred = load_pred(pred_path)

    rules = ["dist", "ttc"] if rule == "both" else [rule]
    R = [f"# 通知 v4（TTC規則） pred={pred_path.name}", "",
         f"- 定数: TTC_WARN={TTC_WARN}s / TTC_CAUTION={TTC_CAUTION}s / "
         f"R_DANGER={R_DANGER}m / VEL_WIN={VEL_WIN}fr({VEL_WIN/FPS:.1f}s) / "
         f"V_MIN={V_MIN}m/s / D_MAX_TTC={D_MAX_TTC}m",
         f"- 引き継ぎ: T3={T3} T2={T2} SUPP={SUPP} AZ_MATCH={AZ_MATCH} "
         f"LINK_DEG={LINK_DEG} CONFIRM={CONFIRM}", ""]
    summary = {}
    for r in rules:
        res = run_rule(pred, r)
        n_ep = sum(len(e) for c in res.values() for e in c.values())
        n_strong = sum(1 for c in res.values() for e in c.values()
                       for ep in e if ep[2] == "強")
        # 発火時の距離の分布（速い相手をどれだけ遠くで捕まえたか）
        d_fire = [ep[3] for c in res.values() for e in c.values() for ep in e]
        summary[r] = dict(n_ep=n_ep, n_strong=n_strong, d_fire=d_fire, res=res)
        R += [f"## 規則 {r}",
              f"- エピソード {n_ep:,}（うち強 {n_strong:,}）",
              (f"- 発火時の推定距離: 中央 {np.median(d_fire):.2f}m / "
               f"最大 {max(d_fire):.2f}m / >3.2mで発火 "
               f"{100*np.mean(np.array(d_fire) > SUPP):.1f}%"
               if d_fire else "- 発火なし"), ""]
    if len(rules) == 2:
        a, b = summary["dist"], summary["ttc"]
        R += ["## 距離規則 → TTC規則 の変化", "",
              f"- エピソード数 {a['n_ep']:,} → {b['n_ep']:,}",
              f"- 発火時距離の中央 {np.median(a['d_fire']):.2f}m → "
              f"{np.median(b['d_fire']):.2f}m",
              "- **発火時距離が伸びていれば「速い相手を早く捕まえられている」証拠**", ""]
    (outdir / "notify_v4.md").write_text("\n".join(R), encoding="utf-8")
    print("\n".join(R))
    print("->", outdir / "notify_v4.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
