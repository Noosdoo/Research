"""
DCASE 2020 Task3 ラベル変換スクリプト
  入力: frame, class, track, azimuth, elevation  (10fps = 0.1秒/フレーム)
  出力: onset_sec, offset_sec, class_idx, azimuth_deg, elevation_deg
"""
import os, glob

LABEL_HOP_SEC = 0.1   # DCASE 2020 フレーム分解能

def convert_file(in_path, out_path):
    # フレームごとのイベントを読む
    events = []
    with open(in_path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            parts = line.split(',')
            if len(parts) < 5: continue
            frame = int(parts[0])
            cls   = int(parts[1])
            track = int(parts[2])
            az    = float(parts[3])
            el    = float(parts[4])
            events.append((frame, cls, track, az, el))

    if not events:
        open(out_path, 'w').close()
        return

    # (class, track) ごとに連続フレームをグループ化 → onset/offset
    events.sort(key=lambda x: (x[2], x[1], x[0]))  # track, class, frame でソート

    segments = []
    i = 0
    while i < len(events):
        frame, cls, track, az, el = events[i]
        onset = frame
        az_sum, el_sum, count = az, el, 1
        j = i + 1
        while j < len(events):
            nf, nc, nt, naz, nel = events[j]
            if nc == cls and nt == track and nf == frame + count:
                az_sum += naz; el_sum += nel; count += 1; frame = nf
            else:
                break
            j += 1
        offset = onset + count
        avg_az = az_sum / count
        avg_el = el_sum / count
        segments.append((onset * LABEL_HOP_SEC, offset * LABEL_HOP_SEC,
                         cls, avg_az, avg_el))
        i = j

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        for onset, offset, cls, az, el in segments:
            f.write(f"{onset:.3f},{offset:.3f},{cls},{az:.1f},{el:.1f}\n")


if __name__ == '__main__':
    base     = r'C:\Users\satos\research\TAU-NIGENS2020'
    in_dir   = os.path.join(base, 'metadata_dev', 'metadata_dev')
    out_dir  = os.path.join(base, 'labels_converted')

    csvs = sorted(glob.glob(os.path.join(in_dir, '*.csv')))
    print(f"{len(csvs)} 件のラベルを変換中...")
    for p in csvs:
        fname   = os.path.basename(p)
        out_p   = os.path.join(out_dir, fname)
        convert_file(p, out_p)
    print(f"変換完了 → {out_dir}")
