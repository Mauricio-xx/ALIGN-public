.subckt telescopic_ota_sg13g2 vbiasn vbiasp1 vbiasp2 vinn vinp voutn voutp id vdd 0
* All devices uniformly sized at NF=4 M=1, W=560n (fin=W/active_pitch=2). The
* Phase G fix in pdks/IHP_SG13G2_PDK/mos.py (_connectNets strap-end pitch math)
* removed the multi-tile via-outside-metal issue that earlier required nf=2.
* nf=4 was chosen over nf=2 so each primitive ships with both a tall X1_Y2 and
* a wide X2_Y1 shape variant (CMC_S_* near-square), giving the placer more
* options. End-to-end schematic2layout still stops in the C++ ILP placer
* (PnR.placer.Placer.PlacementCoreAspectRatio_ILP infeasibility, see Phase H
* checkpoint); fixing that is upstream of pdks/ and tracked as Phase I deuda.
* Sizing is symbolic; this example exercises topology + primitive generation,
* not analog performance.
m1 id id 0 0 nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m2 net10 id 0 0 nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m5 voutn vbiasn net8 0 nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m6 voutp vbiasn net014 0 nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m8 voutp vbiasp1 net012 vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m7 voutn vbiasp1 net06 vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m10 net012 vbiasp2 vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m9 net06 vbiasp2 vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m4 net014 vinn net10 0 nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m3 net8 vinp net10 0 nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends telescopic_ota_sg13g2
** End of subcircuit definition.
