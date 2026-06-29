import h5py, numpy as np
f="datasets/rir_datasets/spatialscaper_RIRs/metu_foa.sofa"
with h5py.File(f,"r") as h:
    IR=h["Data.IR"][:]           # (244,4,96000)
    sr=float(h["Data.SamplingRate"][0])
print("IR",IR.shape,"sr",sr,"IRlen=%.2fs"%(IR.shape[2]/sr))
def edc_t60(h_, sr):
    h_=h_/ (np.max(np.abs(h_))+1e-12)
    E=np.flip(np.cumsum(np.flip(h_**2)))
    EDC=10*np.log10(E/np.max(E)+1e-12)
    t=np.arange(len(h_))/sr
    i1=np.argmax(EDC<=-5); i2=np.argmax(EDC<=-35)
    if i2<=i1: return None,EDC,t
    p=np.polyfit(t[i1:i2],EDC[i1:i2],1)
    return -60/p[0],EDC,t
# W channel (ch0), a few positions
t60s=[]
for idx in [0,60,120,180,243]:
    w=IR[idx,0,:]
    T60,EDC,t=edc_t60(w,sr)
    t60s.append(T60)
    print(f"pos{idx:3d}: T60={T60:.3f}s  (peak@{np.argmax(np.abs(w))/sr*1000:.0f}ms)")
print("mean T60 (W) = %.3f s"%np.nanmean([x for x in t60s if x]))
