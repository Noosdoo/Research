import numpy as np, h5py
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
# Japanese font if available
for fp in [r"C:/Windows/Fonts/meiryo.ttc",r"C:/Windows/Fonts/YuGothM.ttc",r"C:/Windows/Fonts/msgothic.ttc"]:
    try: fm.fontManager.addfont(fp); plt.rcParams["font.family"]=fm.FontProperties(fname=fp).get_name(); break
    except: pass
OUT=r"C:/Users/satos/research/seld_move_ablation/edc"
def edc_curve(h,sr):
    h=np.asarray(h,float); h=h/(np.max(np.abs(h))+1e-12)
    E=np.flip(np.cumsum(np.flip(h**2))); EDC=10*np.log10(E/np.max(E)+1e-12)
    return EDC,np.arange(len(h))/sr
def t60(EDC,t,lo=-5,hi=-35):
    i1=int(np.argmax(EDC<=lo)); i2=int(np.argmax(EDC<=hi))
    if i2<=i1: return None
    return -60/np.polyfit(t[i1:i2],EDC[i1:i2],1)[0]

with h5py.File(r"C:/Users/satos/research/SpatialScaper/datasets/rir_datasets/spatialscaper_RIRs/metu_foa.sofa") as hf:
    ir_ss=hf["Data.IR"][0,0,:]
pk=int(np.argmax(np.abs(ir_ss))); ir_ss=ir_ss[max(0,pk-50):]; sr_ss=48000
EDC_ss,t_ss=edc_curve(ir_ss,sr_ss); T_ss=t60(EDC_ss,t_ss)

ir_sg=np.load(OUT+"/sg_ir.npy"); pk=int(np.argmax(np.abs(ir_sg))); ir_sg=ir_sg[max(0,pk-30):]; sr_sg=24000
EDC_sg,t_sg=edc_curve(ir_sg,sr_sg); T_sg=t60(EDC_sg,t_sg)

sr_ff=24000; ir_ff=np.zeros(int(0.6*sr_ff)); ir_ff[5]=1.0; EDC_ff,t_ff=edc_curve(ir_ff,sr_ff)
print("SpatialScaper metu T60=%.2fs ; SELDGEN shoebox T60=%.2fs ; free-field=0"%(T_ss,T_sg))

# Fig1 EDC
plt.figure(figsize=(8,5),facecolor="white")
plt.plot(t_ss,EDC_ss,lw=2,color="#d1495b",label="SpatialScaper（metu 実測室） T60≈%.1f s"%T_ss)
plt.plot(t_sg,EDC_sg,lw=2,color="#3a7ca5",label="SELD-Data-Generator（pra シミュ室） T60≈%.2f s"%T_sg)
plt.plot(t_ff,EDC_ff,lw=2,color="#2a9d8f",label="自作（自由音場） T60≈0")
plt.axhline(-60,ls="--",c="gray",lw=1)
plt.xlim(0,1.5); plt.ylim(-80,2); plt.grid(alpha=0.3)
plt.xlabel("time [s]"); plt.ylabel("Energy Decay Curve [dB]")
plt.title("残響の比較（EDC・W ch）：既存=部屋（T60>0）/ 自作=自由音場（T60≈0）")
plt.legend(loc="upper right"); plt.tight_layout()
plt.savefig(OUT+"/edc_compare.png",dpi=150); print("saved edc_compare.png")

# Fig2 IRs
fig,ax=plt.subplots(1,3,figsize=(13,3.4),facecolor="white")
for a,(ir,sr,ti,c) in zip(ax,[(ir_ss,sr_ss,"SpatialScaper 実測室\nT60≈%.1f s"%T_ss,"#d1495b"),
                              (ir_sg,sr_sg,"SELD-Data-Generator シミュ室\nT60≈%.2f s"%T_sg,"#3a7ca5"),
                              (ir_ff,sr_ff,"自作 自由音場\n尾なし（T60≈0）","#2a9d8f")]):
    tt=np.arange(len(ir))/sr; a.plot(tt,ir/np.max(np.abs(ir)),c=c,lw=0.7)
    a.set_xlim(0,min(1.0,len(ir)/sr)); a.set_title(ti,fontsize=10); a.set_xlabel("time [s]"); a.grid(alpha=0.3)
ax[0].set_ylabel("amplitude (norm)")
plt.suptitle("インパルス応答：既存は反射の尾を引く（部屋）／自作は単一インパルス（自由音場）",y=1.04)
plt.tight_layout(); plt.savefig(OUT+"/ir_compare.png",dpi=150,bbox_inches="tight"); print("saved ir_compare.png")
