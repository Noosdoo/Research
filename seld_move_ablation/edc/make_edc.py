import os, sys, numpy as np, h5py
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
OUT=r"C:/Users/satos/research/seld_move_ablation/edc"

def edc_curve(h, sr):
    h=np.asarray(h,float); h=h/(np.max(np.abs(h))+1e-12)
    E=np.flip(np.cumsum(np.flip(h**2)))
    EDC=10*np.log10(E/np.max(E)+1e-12)
    t=np.arange(len(h))/sr
    return EDC,t
def t_x(EDC,t,lo,hi):
    i1=int(np.argmax(EDC<=lo)); i2=int(np.argmax(EDC<=hi))
    if i2<=i1: return None
    p=np.polyfit(t[i1:i2],EDC[i1:i2],1); return -60/p[0]

# --- 1) SpatialScaper: metu measured room (W ch) ---
with h5py.File(r"C:/Users/satos/research/SpatialScaper/datasets/rir_datasets/spatialscaper_RIRs/metu_foa.sofa") as hf:
    ir_ss=hf["Data.IR"][0,0,:]      # pos0, W
sr_ss=48000
# trim leading delay to the direct peak for clean IR view
pk=int(np.argmax(np.abs(ir_ss))); ir_ss=ir_ss[max(0,pk-50):]
EDC_ss,t_ss=edc_curve(ir_ss,sr_ss)
T20_ss=t_x(EDC_ss,t_ss,-5,-25); T30_ss=t_x(EDC_ss,t_ss,-5,-35)

# --- 2) SELD-Data-Generator: simulated shoebox (pra) ---
sys.path.insert(0, r"C:/Users/satos/research/SELD-Data-Generator")
from srir.srir import GenerateSRIR
g=GenerateSRIR(SH_order=1, fs=24000.)
room_dim=[8.0,6.0,3.5]; rt60_set=0.4
g.compute_srir(room_dim, src_pos=[[2.0,2.0,1.5]], rt60=rt60_set, method='ism')
ir_sg=np.asarray(g.rir[0][0]); sr_sg=24000
pk=int(np.argmax(np.abs(ir_sg))); ir_sg=ir_sg[max(0,pk-50):]
EDC_sg,t_sg=edc_curve(ir_sg,sr_sg)
T20_sg=t_x(EDC_sg,t_sg,-5,-25); T30_sg=t_x(EDC_sg,t_sg,-5,-35)

# --- 3) Free-field (self-made): impulse = delta (no room) ---
sr_ff=24000; ir_ff=np.zeros(int(0.6*sr_ff)); ir_ff[5]=1.0
EDC_ff,t_ff=edc_curve(ir_ff,sr_ff)

print("SpatialScaper(metu)  T20=%.2fs T30=%.2fs"%(T20_ss,T30_ss))
print("SELDGEN(shoebox %.2f) T20=%.2fs T30=%.2fs"%(rt60_set,T20_sg,T30_sg))
print("Free-field(self)     T60 = 0 (delta, no decay)")

# ===== Figure 1: EDC comparison =====
plt.figure(figsize=(8,5),facecolor="white")
plt.plot(t_ss,EDC_ss,label="SpatialScaper (metu 実測室)  T60≈%.1fs"%T30_ss,lw=2,color="#d1495b")
plt.plot(t_sg,EDC_sg,label="SELD-Data-Generator (シミュ室)  T60≈%.2fs"%T30_sg,lw=2,color="#3a7ca5")
plt.plot(t_ff,EDC_ff,label="自作 (自由音場)  T60≈0",lw=2,color="#2a9d8f")
plt.axhline(-60,ls="--",c="gray",lw=1); plt.text(0.02,-58,"-60 dB",color="gray")
plt.xlim(0,2.0); plt.ylim(-80,2); plt.grid(alpha=0.3)
plt.xlabel("time [s]"); plt.ylabel("Energy Decay Curve [dB]")
plt.title("残響の比較（エネルギー減衰曲線・W ch）— 既存=部屋 / 自作=自由音場")
plt.legend(loc="upper right",fontsize=10)
plt.tight_layout(); plt.savefig(OUT+"/edc_compare.png",dpi=150); print("saved edc_compare.png")

# ===== Figure 2: impulse responses =====
fig,ax=plt.subplots(1,3,figsize=(13,3.4),facecolor="white")
for a,(ir,sr,ti,c) in zip(ax,[(ir_ss,sr_ss,"SpatialScaper 実測室 (T60≈%.1fs)"%T30_ss,"#d1495b"),
                              (ir_sg,sr_sg,"SELDGEN シミュ室 (T60≈%.2fs)"%T30_sg,"#3a7ca5"),
                              (ir_ff,sr_ff,"自作 自由音場 (尾なし)","#2a9d8f")]):
    tt=np.arange(len(ir))/sr
    a.plot(tt,ir/np.max(np.abs(ir)),c=c,lw=0.7); a.set_xlim(0,min(1.2,len(ir)/sr))
    a.set_title(ti,fontsize=10); a.set_xlabel("time [s]"); a.grid(alpha=0.3)
ax[0].set_ylabel("amplitude (norm)")
plt.suptitle("インパルス応答：既存ツールは反射の尾を引く（=部屋）／自作は単一インパルス（=自由音場）",y=1.02)
plt.tight_layout(); plt.savefig(OUT+"/ir_compare.png",dpi=150,bbox_inches="tight"); print("saved ir_compare.png")
