import soundfile as sf, numpy as np, h5py, os
root="C:/Users/satos/research/SpatialScaper"
sg="C:/Users/satos/research/SELD-Data-Generator/srir/ambisonics_dependencies/car_demos"
files={"dry_source":sg+"/car_dry_mono.wav",
 "SELDGEN_wet":sg+"/seldgen/car_seld_foa.wav",
 "SpatialScaper_wet":sg+"/spatialscaper/car_demo.wav"}
for k,f in files.items():
    if os.path.exists(f):
        x,sr=sf.read(f); x=np.asarray(x)
        print(f"{k:18s} sr={sr} shape={x.shape} dur={len(x)/sr:.2f}s")
    else: print(f"{k:18s} MISSING")
print("\n--- metu_foa.sofa ---")
with h5py.File(root+"/datasets/rir_datasets/spatialscaper_RIRs/metu_foa.sofa","r") as h:
    for key in h.keys():
        v=h[key]
        try: print(f"  {key}: shape={v.shape} dtype={v.dtype}")
        except Exception: print(f"  {key}: grp")
