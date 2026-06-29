import numpy as np, h5py, soundfile as sf
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
for fp in [r"C:/Windows/Fonts/meiryo.ttc",r"C:/Windows/Fonts/YuGothM.ttc"]:
    try: fm.fontManager.addfont(fp); plt.rcParams["font.family"]=fm.FontProperties(fname=fp).get_name(); break
    except: pass
OUT="seld_move_ablation/edc"
def edc(h,sr):
    h=np.asarray(h,float); h=h/(np.max(np.abs(h))+1e-12)
    E=np.flip(np.cumsum(np.flip(h**2))); return 10*np.log10(E/np.max(E)+1e-12),np.arange(len(h))/sr
def t60(E,t):
    i1=int(np.argmax(E<=-5)); i2=int(np.argmax(E<=-25)); return -60/np.polyfit(t[i1:i2],E[i1:i2],1)[0], t[i2]
with h5py.File("SpatialScaper/datasets/rir_datasets/spatialscaper_RIRs/metu_foa.sofa") as hf:
    a=hf["Data.IR"][0,0,:]
pk=int(np.argmax(np.abs(a))); a=a[max(0,pk-50):]; Ea,ta=edc(a,48000); Ta,xend=t60(Ea,ta)
b=np.load(OUT+"/sg_ir.npy"); pk=int(np.argmax(np.abs(b))); b=b[max(0,pk-30):]; Eb,tb=edc(b,24000); Tb,_=t60(Eb,tb)
plt.figure(figsize=(8,5),facecolor="white")
plt.plot(ta,Ea,lw=2,color="#d1495b",label="SpatialScaper（metu 実測室） T60≈%.1f s"%Ta)
plt.plot(tb,Eb,lw=2,color="#3a7ca5",label="SELD-Data-Generator（pra シミュ室） T60≈%.2f s"%Tb)
plt.axvspan(0,xend,color="#ffe08a",alpha=0.3,label="測定に使う綺麗な区間(-5〜-25dB)\n→傾き×3で60dBに換算")
plt.axhline(-60,ls="--",c="gray",lw=1); plt.text(1.05,-58,"-60 dB",color="gray",fontsize=9)
plt.xlim(0,1.5); plt.ylim(-80,2); plt.grid(alpha=0.3)
plt.xlabel("time [s]"); plt.ylabel("Energy Decay Curve [dB]")
plt.title("残響時間 T60（ISO 3382 / T20法で外挿）：既存はどちらも「部屋」")
plt.legend(loc="upper right",fontsize=9); plt.tight_layout()
plt.savefig(OUT+"/edc_compare.png",dpi=150); print("metu=%.2f pra=%.2f  saved edc_compare.png"%(Ta,Tb))
