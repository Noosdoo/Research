# -*- coding: utf-8 -*-
"""OpenStreetMap の生データ → デモ用の配置図（layout 行）・道路の折れ線（車の経路用）・確認用 PNG（2026-09-03）。

対象: 東京理科大学 野田キャンパス 正門前の交差点（本人依頼「実際に日本の地図を入手して再現したい」）。
データ: OpenStreetMap（© OpenStreetMap contributors, ODbL）。Overpass API で取得した JSON を
        out/joycon_demo_v2/map/osm_tus_noda.json に保存して使う（再取得不要）。

座標系: 原点 = 指定した緯度経度（正門前の交差点）、x = 歩行者の前方、y = 左（FOA/デモの規約）。
        heading_deg は歩行者が向く方位（北=0・東=90・時計回り）。

出力（out/joycon_demo_v2/map/）:
  <name>_layout.csv   : ScenarioVisualizer が描く行。map,1 / road,x1,y1,x2,y2,width,kind / bldg,cx,cy,w,d,angle,height /
                        water,x1,y1,x2,y2,width / rail,x1,y1,x2,y2 / poi,x,y,kind
  <name>_roads.json   : 道路の折れ線（歩行者座標・m）。scenario JSON の "geom":"path" の points に使う
  <name>_preview.png  : 上から見た図（確認用）

使い方: python scripts/_osm_map_layout.py [--lat 35.917258 --lon 139.906206 --heading 270 --radius 130 --name tus_noda_seimon]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MAPDIR = ROOT / "out/joycon_demo_v2/map"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROAD_W = {"tertiary": 7.0, "secondary": 8.0, "primary": 9.0, "unclassified": 5.5, "residential": 5.0,
          "service": 3.5, "living_street": 4.0, "pedestrian": 3.0, "footway": 1.6, "path": 1.2,
          "cycleway": 2.0, "steps": 1.5, "track": 3.0}
CAR_ROADS = {"tertiary", "secondary", "primary", "unclassified", "residential", "living_street", "service"}


def arg(name, default):
    if name in sys.argv:
        return type(default)(sys.argv[sys.argv.index(name) + 1])
    return default


def main() -> int:
    lat0 = arg("--lat", 35.917258)      # 正門前の交差点（OSM の 4 差路ノード付近）
    lon0 = arg("--lon", 139.906206)
    heading = arg("--heading", 270.0)   # 歩行者の向き（既定: 西向き＝交差点に向かって立つ）
    radius = arg("--radius", 130.0)
    name = arg("--name", "tus_noda_seimon")
    src = Path(arg("--src", str(MAPDIR / "osm_tus_noda.json")))
    d = json.load(open(src, encoding="utf-8"))
    els = d["elements"]

    cosl = math.cos(math.radians(lat0))
    h = math.radians(heading)

    def to_frame(lat, lon):
        e = (lon - lon0) * 111320.0 * cosl      # 東
        n = (lat - lat0) * 111320.0             # 北
        # 前方 x = 方位 heading の単位ベクトルとの内積、左 y = その左
        x = e * math.sin(h) + n * math.cos(h)
        y = -e * math.cos(h) + n * math.sin(h)
        return x, y

    rows = [("map", "1", "", "", "", "", "", "")]
    roads = []
    n_road = n_bldg = n_water = n_rail = n_poi = 0
    for e in els:
        t = e.get("tags", {})
        if e["type"] == "way" and "geometry" in e:
            pts = [to_frame(p["lat"], p["lon"]) for p in e["geometry"]]
            near = any(math.hypot(x, y) <= radius for x, y in pts)
            if not near:
                continue
            if "highway" in t:
                kind = t["highway"]
                wdt = float(t.get("width", 0) or 0) or ROAD_W.get(kind, 3.0)
                lanes = t.get("lanes")
                if lanes and kind in CAR_ROADS:
                    wdt = max(wdt, 3.25 * float(lanes))
                for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
                    rows.append(("road", f"{x1:.1f}", f"{y1:.1f}", f"{x2:.1f}", f"{y2:.1f}", f"{wdt:.1f}", kind, ""))
                    n_road += 1
                if kind in CAR_ROADS:
                    roads.append({"id": e["id"], "kind": kind, "name": t.get("name", ""), "lanes": lanes,
                                  "oneway": t.get("oneway", "no"), "points": [[round(x, 1), round(y, 1)] for x, y in pts]})
            elif "building" in t:
                P = np.array(pts)
                if len(P) < 3:
                    continue
                c = P.mean(axis=0)
                Q = P - c
                cov = Q.T @ Q
                ev_, evec = np.linalg.eigh(cov)
                ax = evec[:, 1]                       # 長軸
                ang = math.degrees(math.atan2(ax[1], ax[0]))
                R = np.array([[ax[0], ax[1]], [-ax[1], ax[0]]])
                L = Q @ R.T
                w = float(L[:, 0].max() - L[:, 0].min())
                dd = float(L[:, 1].max() - L[:, 1].min())
                lv = t.get("building:levels")
                hgt = 3.2 * float(lv) if lv and lv.replace(".", "").isdigit() else (float(t.get("height", 0) or 0) or 6.0)
                rows.append(("bldg", f"{c[0]:.1f}", f"{c[1]:.1f}", f"{w:.1f}", f"{dd:.1f}", f"{ang:.1f}", f"{hgt:.1f}", t.get("name", "")))
                n_bldg += 1
            elif "waterway" in t or t.get("natural") == "water":
                wdt = float(t.get("width", 0) or 0) or (12.0 if t.get("waterway") == "river" else 3.0)
                for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
                    rows.append(("water", f"{x1:.1f}", f"{y1:.1f}", f"{x2:.1f}", f"{y2:.1f}", f"{wdt:.1f}", t.get("name", ""), ""))
                    n_water += 1
            elif t.get("railway") in ("rail", "light_rail", "tram"):
                for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
                    rows.append(("rail", f"{x1:.1f}", f"{y1:.1f}", f"{x2:.1f}", f"{y2:.1f}", "", t.get("name", ""), ""))
                    n_rail += 1
        elif e["type"] == "node" and "lat" in e:
            x, y = to_frame(e["lat"], e["lon"])
            if math.hypot(x, y) > radius:
                continue
            kind = None
            if t.get("highway") == "traffic_signals" or t.get("crossing") == "traffic_signals":
                kind = "signal"
            elif t.get("highway") == "crossing":
                kind = "crossing"
            elif t.get("barrier") == "gate":
                kind = "gate"
            elif t.get("highway") == "bus_stop":
                kind = "bus_stop"
            if kind:
                rows.append(("poi", f"{x:.1f}", f"{y:.1f}", kind, t.get("name", ""), "", "", ""))
                n_poi += 1

    MAPDIR.mkdir(parents=True, exist_ok=True)
    with open(MAPDIR / f"{name}_layout.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("type,a,b,c,d,e,f,g\n")
        for r in rows:
            f.write(",".join(str(v).replace(",", " ") for v in r) + "\n")
    (MAPDIR / f"{name}_roads.json").write_text(json.dumps(
        {"origin": {"lat": lat0, "lon": lon0, "heading_deg": heading}, "frame": "x=前方(m) y=左(m)",
         "source": "OpenStreetMap (c) OpenStreetMap contributors, ODbL", "roads": roads},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"origin ({lat0}, {lon0}) heading {heading}°  radius {radius} m")
    print(f"road segs {n_road} / buildings {n_bldg} / water {n_water} / rail {n_rail} / poi {n_poi} / car roads {len(roads)}")

    # ---- 確認用 PNG（上から。x=前方を上に、y=左を左に）
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        fig, ax = plt.subplots(figsize=(9, 9))
        for r in rows:
            if r[0] == "bldg":
                cx, cy, w, dd, ang, hg = map(float, r[1:7])
                rect = Rectangle((-w / 2, -dd / 2), w, dd, color="#c9b8a8", alpha=0.9)
                tr = matplotlib.transforms.Affine2D().rotate_deg(ang).translate(cx, cy)
                # 描画座標: 横軸 = -y（左が左に見えるように）, 縦軸 = x
                tr2 = matplotlib.transforms.Affine2D().rotate_deg(-ang).translate(-cy, cx)
                rect.set_transform(matplotlib.transforms.Affine2D().rotate_deg(-ang - 0).translate(-cy, cx) + ax.transData)
                ax.add_patch(rect)
        for r in rows:
            if r[0] in ("road", "water", "rail"):
                x1, y1, x2, y2 = map(float, r[1:5])
                if r[0] == "road":
                    wdt = float(r[5]); kind = r[6]
                    col = "#444" if kind in CAR_ROADS else "#999"
                    lw = max(1.0, wdt * 0.9)
                elif r[0] == "water":
                    col, lw = "#7fb3ff", max(2.0, float(r[5]) * 0.9)
                else:
                    col, lw = "#222", 2.0
                ax.plot([-y1, -y2], [x1, x2], color=col, lw=lw, solid_capstyle="round", zorder=2)
        for r in rows:
            if r[0] == "poi":
                x, y, kind = float(r[1]), float(r[2]), r[3]
                m = {"signal": ("o", "red"), "crossing": ("s", "white"), "gate": ("^", "orange"), "bus_stop": ("D", "blue")}[kind]
                ax.plot(-y, x, marker=m[0], color=m[1], ms=7, mec="k", zorder=5)
        ax.plot(0, 0, marker="*", color="yellow", ms=16, mec="k", zorder=6)
        ax.arrow(0, 0, 0, 12, width=1.2, color="yellow", ec="k", zorder=6)
        for rd in roads:
            if rd["name"]:
                P = rd["points"]; mid = P[len(P) // 2]
                ax.text(-mid[1], mid[0], rd["name"], fontsize=8, color="k", ha="center")
        ax.set_xlim(-radius, radius); ax.set_ylim(-radius, radius); ax.set_aspect("equal")
        ax.set_facecolor("#e6efe0")
        ax.set_xlabel("← 左 (m)   右 →"); ax.set_ylabel("前方 (m)")
        ax.set_title(f"{name}  origin=({lat0:.6f},{lon0:.6f}) heading={heading:.0f}°  ★=歩行者 / ▲=門 / ●=信号 / □=横断歩道 / ◆=バス停")
        fig.tight_layout()
        fig.savefig(MAPDIR / f"{name}_preview.png", dpi=110)
        print("->", MAPDIR / f"{name}_preview.png")
    except Exception as ex:  # noqa: BLE001
        print("PNG skipped:", ex)
    print("->", MAPDIR / f"{name}_layout.csv", "/", MAPDIR / f"{name}_roads.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
