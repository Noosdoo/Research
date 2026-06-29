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
def t60_T20(E,t):
    i1=int(np.argmax(E<=-5)); i2=int(np.argmax(E<=-25))   # T20
    return -60/np.polyfit(t[i1:i2],E[i1:i2],1)[0]
with h5py.File("SpatialScaper/datasets/rir_datasets/spatialscaper_RIRs/metu_foa.sofa") as hf:
    a=hf["Data.IR"][0,0,:]
pk=int(np.argmax(np.abs(a))); a=a[max(0,pk-50):]; Ea,ta=edc(a,48000); Ta=t60_T20(Ea,ta)
b=np.load(OUT+"/sg_ir.npy"); pk=int(np.argmax(np.abs(b))); b=b[max(0,pk-30):]; Eb,tb=edc(b,24000); Tb=t60_T20(Eb,tb)
print("metu T60(T20)=%.2fs  pra T60(T20)=%.2fs"%(Ta,Tb))
# EDC図
plt.figure(figsize=(8,5),facecolor="white")
plt.plot(ta,Ea,lw=2,color="#d1495b",label="SpatialScaper（metu 実測室） T60≈%.1f s"%Ta)
plt.plot(tb,Eb,lw=2,color="#3a7ca5",label="SELD-Data-Generator（pra シミュ室） T60≈%.2f s"%Tb)
plt.axvspan(0,ta[int(np.argmax(Ea<=-25))],color="#ffe08a",alpha=0.25,label="T20評価区間(-5〜-25dB)")
plt.axhline(-60,ls="--",c="gray",lw=1); plt.xlim(0,1.5); plt.ylim(-80,2); plt.grid(alpha=0.3)
plt.xlabel("time [s]"); plt.ylabel("Energy Decay Curve [dB]")
plt.title("既存ツールの空間化はどちらも「部屋」（T60>0／T20法）")
plt.legend(loc="upper right",fontsize=9); plt.tight_layout()
plt.savefig(OUT+"/edc_compare.png",dpi=150); print("saved edc_compare.png")
# car残響尾図（ラベルだけ更新）
dry,_=sf.read(OUT+"/car_dry.wav"); met,_=sf.read(OUT+"/car_metu.wav"); sld,_=sf.read(OUT+"/car_seldgen.wav")
SR=24000; t=np.arange(len(dry))/SR; tc=2.5
fig,ax=plt.subplots(3,1,figsize=(8,6),sharex=True,facecolor="white")
for A,(y,ti,c) in zip(ax,[(dry,"乾き 元音源 233472（残響なし）","#555555"),
                          (met,"SpatialScaper 実測室（metu, T60≈%.1fs）"%Ta,"#d1495b"),
                          (sld,"SELD-Data-Generator シミュ室（pra, T60≈%.2fs）"%Tb,"#3a7ca5")]):
    A.plot(t,y,c=c,lw=0.6); A.axvline(tc,color="k",ls=":",lw=1)
    A.set_xlim(tc-0.3,tc+3.5); A.set_ylim(-1,1); A.grid(alpha=0.3); A.set_title(ti,fontsize=10,loc="left"); A.set_ylabel("amp")
ax[-1].set_xlabel("time [s]   （点線＝車が鳴り止む瞬間。以降の尾＝部屋の残響）")
plt.suptitle("同じ車を各ツールの部屋に通す：鳴り止み後に残響の尾（既存=部屋）",y=0.99)
plt.tight_layout(); plt.savefig(OUT+"/car_reverb_tail.png",dpi=150); print("saved car_reverb_tail.png")
