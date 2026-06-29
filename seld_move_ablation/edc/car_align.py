import numpy as np, h5py, soundfile as sf
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy.signal import fftconvolve, resample_poly
for fp in [r"C:/Windows/Fonts/meiryo.ttc",r"C:/Windows/Fonts/YuGothM.ttc"]:
    try: fm.fontManager.addfont(fp); plt.rcParams["font.family"]=fm.FontProperties(fname=fp).get_name(); break
    except: pass
OUT="seld_move_ablation/edc"; SR=24000
def nrm(x): return 0.97*x/(np.max(np.abs(x))+1e-9)
# room IRs (same as before)
with h5py.File("SpatialScaper/datasets/rir_datasets/spatialscaper_RIRs/metu_foa.sofa") as hf:
    ir_ss=hf["Data.IR"][0,0,:].astype(float)
ir_ss=resample_poly(ir_ss/np.max(np.abs(ir_ss)),24000,48000)
ir_sg=np.load(OUT+"/sg_ir.npy").astype(float); ir_sg/=np.max(np.abs(ir_sg))
# dry car 233472 : loud 2.5s excerpt, hard cut → tail可視
car,sr=sf.read("SELD-Data-Generator/srir/ambisonics_dependencies/car_demos/car_dry_mono.wav")
car=np.atleast_1d(car); car=resample_poly(car,SR,sr) if sr!=SR else car
# pick the loudest 2.5s window
w=int(2.5*SR); env=np.convolve(car**2,np.ones(w)/w,'same'); c0=max(0,int(np.argmax(env)-w//2))
exc=nrm(car[c0:c0+w])
dry=np.concatenate([exc, np.zeros(int(4.0*SR))])
wet_ss=nrm(fftconvolve(dry,ir_ss)[:len(dry)])
wet_sg=nrm(fftconvolve(dry,ir_sg)[:len(dry)])
sf.write(OUT+"/car_dry.wav",dry,SR)
sf.write(OUT+"/car_metu.wav",wet_ss,SR)        # SpatialScaper 実測室
sf.write(OUT+"/car_seldgen.wav",wet_sg,SR)     # SELDGEN シミュ室
# remove old actual-output copies to avoid confusion
import os
for f in ["car_SELDGEN.wav","car_SpatialScaper.wav"]:
    p=os.path.join(OUT,f);  os.path.exists(p) and os.remove(p)

# ===== 図：同じ車・鳴り止み後の残響尾（zoom）=====
t=np.arange(len(dry))/SR; tcut=w/SR
fig,ax=plt.subplots(3,1,figsize=(8,6),sharex=True,facecolor="white")
for a,(y,ti,c) in zip(ax,[(dry,"乾き 元音源 233472（残響なし）","#555555"),
                          (wet_ss,"SpatialScaper 実測室（metu, T60≈3.3s）","#d1495b"),
                          (wet_sg,"SELD-Data-Generator シミュ室（pra, T60≈0.5s）","#3a7ca5")]):
    a.plot(t,y,c=c,lw=0.6); a.axvline(tcut,color="k",ls=":",lw=1)
    a.set_xlim(tcut-0.3, tcut+3.5); a.set_ylim(-1,1); a.grid(alpha=0.3)
    a.set_title(ti,fontsize=10,loc="left"); a.set_ylabel("amp")
ax[-1].set_xlabel("time [s]   （点線＝車が鳴り止む瞬間。以降の“尾”が部屋の残響）")
plt.suptitle("同じ車を各ツールの部屋に通す：鳴り止み後に残響の尾（既存=部屋）",y=0.99)
plt.tight_layout(); plt.savefig(OUT+"/car_reverb_tail.png",dpi=150); print("saved car_reverb_tail.png")
print("audio: car_dry / car_metu / car_seldgen .wav  (同一: 車233472)")
