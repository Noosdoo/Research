import numpy as np, h5py, soundfile as sf
from scipy.signal import fftconvolve, resample_poly
OUT=r"C:/Users/satos/research/seld_move_ablation/edc"
SR=24000
def norm(x): return 0.97*x/(np.max(np.abs(x))+1e-9)

# --- room IRs ---
with h5py.File(r"C:/Users/satos/research/SpatialScaper/datasets/rir_datasets/spatialscaper_RIRs/metu_foa.sofa") as hf:
    ir_ss=hf["Data.IR"][0,0,:].astype(float)   # 48k
ir_ss=ir_ss/np.max(np.abs(ir_ss))
sf.write(OUT+"/metu_ir.wav", norm(ir_ss), 48000)      # 実測室IR（クリック＋ホール残響）
ir_sg=np.load(OUT+"/sg_ir.npy").astype(float)         # 24k
sf.write(OUT+"/seldgen_ir.wav", norm(ir_sg), 24000)   # シミュ室IR（小部屋残響）

# --- 共通SRへ ---
ir_ss24=resample_poly(ir_ss, 24000, 48000)

# --- 乾いた音（カラクション=鋭い立下り）で残響を聞かせる ---
kla="C:/Users/satos/research/seld_move_ablation/sources/Klaxon"
import glob,os
cand=sorted(glob.glob(kla+"/*.wav"))
dry=None
for f in cand:                      # 1〜3秒くらいの鋭い音を選ぶ
    x,sr=sf.read(f); x=np.mean(np.atleast_2d(x.T),axis=0) if x.ndim>1 else x
    if sr!=SR: x=resample_poly(x,SR,sr)
    if 0.5<len(x)/SR<4: dry=x; src=os.path.basename(f); break
if dry is None:  # fallback: dry car 2秒
    x,sr=sf.read("../SELD-Data-Generator/srir/ambisonics_dependencies/car_demos/car_dry_mono.wav")
    x=resample_poly(np.atleast_1d(x),SR,sr); dry=x[int(8*SR):int(10*SR)]; src="car_dry(2s)"
dry=norm(dry)
pad=np.concatenate([dry, np.zeros(int(3.5*SR))])      # 鳴り終わり後に残響が出る余白
wet_ss=norm(fftconvolve(pad, ir_ss24)[:len(pad)])
wet_sg=norm(fftconvolve(pad, ir_sg )[:len(pad)])
sf.write(OUT+"/demo_dry.wav",     pad,    SR)
sf.write(OUT+"/demo_metu.wav",    wet_ss, SR)
sf.write(OUT+"/demo_seldgen.wav", wet_sg, SR)
print("source:",src,"  saved: metu_ir, seldgen_ir, demo_dry/metu/seldgen .wav")
