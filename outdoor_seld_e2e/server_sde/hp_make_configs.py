# -*- coding: utf-8 -*-
"""④ハイパラ感度測定の experiment yaml を生成する（2026-09-02）。

基準= configs/experiment/outdoor_siren_v12.yaml（batch8 / lr3e-4 / StepLR(60,0.1) / 100ep）。
armごとに **差分だけ** 変えた outdoor_siren_v12_hp_<arm>.yaml を書く。
宣言= md/design/再学習④_ハイパラ感度_方針宣言_2026-09-02.md §2。

実行場所: PSELDNets リポジトリ直下（configs/ がある所）
    .venv/bin/python ~/research/outdoor_seld_e2e/server_sde/hp_make_configs.py
"""
import os
import sys

assert os.path.isdir("configs/experiment"), "PSELDNets 直下で実行してください"

BASE = """# @package _global_
# ④ハイパラ感度 arm={arm}: {note}
defaults:
 - override /data: outdoor_siren_v12.yaml
 - override /loss: multi_accdoa.yaml
 - _self_

task_name: outdoor_siren_v12

model:
  batch_size: {batch}
  kwargs:
    pretrained_path: {pretrained}
    audioset_pretrain: false
  optimizer:
    kwargs: {{lr: {lr}}}
  lr_scheduler:
    method: {sched}
    kwargs: {sched_kw}

trainer:
  max_epochs: {epochs}
  check_val_every_n_epoch: 5
"""

OFFICIAL = "ckpts/mACCDOA-HTSAT-0.567.ckpt"
D = dict(batch=8, pretrained=OFFICIAL, lr=0.0003, sched="StepLR",
         sched_kw="{step_size: 60, gamma: 0.1}", epochs=100)

# Stage B（基準学習）
ARMS = {
    "lr1e-4": dict(D, lr=0.0001, note="lr 1e-4（StepLR60 → 1e-5）"),
    "cos": dict(D, sched="CosineAnnealingLR", sched_kw="{T_max: 100, eta_min: 3.0e-6}",
                note="CosineAnnealingLR(T_max=100, eta_min=3e-6)"),
    "2step": dict(D, sched="MultiStepLR", sched_kw="{milestones: [40, 70], gamma: 0.1}",
                  note="MultiStepLR [40,70] = 3e-4→3e-5→3e-6"),
    "short": dict(D, epochs=40, sched_kw="{step_size: 20, gamma: 0.1}",
                  note="40ep・StepLR(20)（100epは無駄か）"),
    "bs32": dict(D, batch=32, note="batch 32（lrそのまま）"),
    # 公式ckptから直接（sbatch側で SDE_INIT_CKPT を空にする＝ヘッド乱数初期化）
    "scratch": dict(D, note="warm-start連鎖なし・公式ckptから100ep"),
    # Stage C（因果ft）— pretrained_path は sbatch 側で w3 ep099 に上書きする
    "cseed": dict(D, note="因果ft ft2同一レシピ・seed違い（フロア）"),
    "clr3e-5": dict(D, lr=0.00003, note="因果ft lr 3e-5"),
    "clr1e-4": dict(D, lr=0.0001, note="因果ft lr 1e-4"),
    "crep8": dict(D, epochs=25, sched_kw="{step_size: 15, gamma: 0.1}",
                  note="因果ft REPEAT=8・25ep・StepLR(15)（総サンプル数=REPEAT2×100ep）"),
    # 追試（宣言§7・2026-09-03）
    "clr1e-4s2": dict(D, lr=0.0001, note="因果ft lr1e-4 の別seed再現（seedはsbatch側）"),
    "clr1e-4r8": dict(D, lr=0.0001, epochs=25, sched_kw="{step_size: 15, gamma: 0.1}",
                      note="因果ft lr1e-4 × REPEAT8・25ep・StepLR(15)"),
    "clr1e-4e150": dict(D, lr=0.0001, epochs=150, sched_kw="{step_size: 90, gamma: 0.1}",
                        note="因果ft lr1e-4 × 150ep・StepLR(90)"),
}


def main():
    want = sys.argv[1:] or list(ARMS)
    for arm in want:
        cfg = ARMS[arm]
        path = f"configs/experiment/outdoor_siren_v12_hp_{arm}.yaml"
        with open(path, "w", encoding="utf-8") as f:
            f.write(BASE.format(arm=arm, **cfg))
        print("wrote", path)


if __name__ == "__main__":
    main()
