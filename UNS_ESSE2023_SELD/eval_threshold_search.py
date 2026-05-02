"""
閾値を変えながら eval を実行して最適値を探すスクリプト。
uns_esse2023_seld.py と同じディレクトリで実行してください。
"""

import sys
sys.path.insert(0, ".")
from uns_esse2023_seld import *

def evaluate_with_threshold(threshold, cfg=CFG):
    model_path = os.path.join(cfg["output_dir"], "seld_unet_best.pt")
    if not os.path.exists(model_path):
        print(f"[Error] モデルが見つかりません: {model_path}")
        return None

    model = SELDUNet(cfg).to(cfg["device"])
    model.load_state_dict(torch.load(model_path, map_location=cfg["device"]))
    model.eval()

    dataset = UNSESSEDataset(cfg, split=cfg["eval_split"], augment=False)
    loader  = DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0)
    metrics = SELDMetrics(cfg["n_classes"])

    n_pred_total = 0

    with torch.no_grad():
        for batch in loader:
            if len(batch) == 4:
                feat, target, fnames, seg_idxs = batch
                target = target.to(cfg["device"])
            else:
                continue

            feat = feat.to(cfg["device"])
            _, seld_out = model(feat)
            seld_np = seld_out[0].cpu().numpy()

            # 閾値でデコード
            pred_events = decode_accdoa(seld_np, threshold=threshold)
            ref_events  = decode_accdoa(target[0].cpu().numpy(), threshold=0.1)

            n_pred_total += len(pred_events)
            if ref_events:
                metrics.update(pred_events, ref_events, cfg["label_frames"])

    res = metrics.compute()
    print(f"threshold={threshold:.2f} | "
          f"ER={res['ER']:.3f} F1={res['F1']:.3f} "
          f"LE_CD={res['LE_CD']:.1f} LR_CD={res['LR_CD']:.3f} "
          f"SELD={res['SELD']:.3f} | 検出数={n_pred_total}")
    return res


if __name__ == "__main__":
    print("=== 閾値探索 ===")
    print("[Dataset:eval] ロード中 (時間がかかります)...")

    best_seld = float("inf")
    best_th   = 0.5

    for th in [0.1, 0.2, 0.3, 0.4, 0.5]:
        res = evaluate_with_threshold(th)
        if res and res["SELD"] < best_seld:
            best_seld = res["SELD"]
            best_th   = th

    print(f"\n最良の閾値: {best_th} (SELD Score={best_seld:.3f})")
