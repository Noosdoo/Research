import numpy as np, h5py
from scipy.io import savemat
OUT=r"C:/Users/satos/research/seld_move_ablation/edc"
with h5py.File(r"C:/Users/satos/research/SpatialScaper/datasets/rir_datasets/spatialscaper_RIRs/metu_foa.sofa") as hf:
    ir_ss=hf["Data.IR"][0,0,:].astype(float)
pk=int(np.argmax(np.abs(ir_ss))); ir_ss=ir_ss[max(0,pk-50):]
ir_sg=np.load(OUT+"/sg_ir.npy").astype(float); pk=int(np.argmax(np.abs(ir_sg))); ir_sg=ir_sg[max(0,pk-30):]
ir_ff=np.zeros(int(0.6*24000)); ir_ff[5]=1.0
savemat(OUT+"/irs.mat", {"ir_ss":ir_ss,"sr_ss":48000.0,
                         "ir_sg":ir_sg,"sr_sg":24000.0,
                         "ir_ff":ir_ff,"sr_ff":24000.0})
print("saved irs.mat  ss=%d sg=%d ff=%d"%(len(ir_ss),len(ir_sg),len(ir_ff)))
