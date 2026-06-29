import numpy as np, pyroomacoustics as pra
# minimal robust shoebox: single omni mic, ism only, explicit float64
rt60=0.4; room_dim=[8.0,6.0,3.5]
e_abs,max_order=pra.inverse_sabine(rt60,room_dim); max_order=min(max_order,30)
room=pra.ShoeBox(room_dim,fs=24000,materials=pra.Material(e_abs),max_order=max_order)
room.add_source([2.0,2.0,1.5])
mic=np.array([[4.0],[3.0],[1.6]],dtype=np.float64)
room.add_microphone_array(pra.MicrophoneArray(mic,room.fs))
try:
    room.compute_rir()
    h=np.asarray(room.rir[0][0],float)
    print("OK pra rir len=%d (%.2fs)"%(len(h),len(h)/24000))
    np.save(r"C:/Users/satos/research/seld_move_ablation/edc/sg_ir.npy",h)
except Exception as e:
    print("PRA_FAIL:",type(e).__name__,str(e)[:120])
