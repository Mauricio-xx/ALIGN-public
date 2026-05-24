.subckt five_transistor_ota_sg13g2 vbias vss vdd von vin vip
* Classic 5T OTA ported to IHP SG13G2 130nm.
* mn1: NMOS tail current source (vbias-controlled).
* mn2/mn3: NMOS differential input pair.
* mp4: PMOS diode-connected load (sets mirror reference).
* mp5: PMOS mirror load (output node von).
* Topology from examples/five_transistor_ota_Bulk.
mn1 tail vbias vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn2 von  vin  tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn3 vop  vip  tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp4 von  vop  vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp5 vop  vop  vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends five_transistor_ota_sg13g2
