.subckt telescopic_ota_sg13g2 vbiasn vbiasp1 vbiasp2 vinn vinp voutn voutp id vdd 0
* All devices uniformly sized at NF=2 M=1 so each SCM/CMC/DP collapses to a single
* x1-y1 unit cell. This avoids the multi-tile via-outside-metal placement issue
* that surfaces when the M2 multi-finger strap span doesn't align with the via grid
* (see canvas/remove_duplicates.check_shorts_induced_by_vias). Sizing is symbolic
* only; this example proves the schematic2layout flow, not analog performance.
m1 id id 0 0 nmos_rvt w=560e-9 l=130e-9 nf=2 m=1
m2 net10 id 0 0 nmos_rvt w=560e-9 l=130e-9 nf=2 m=1
m5 voutn vbiasn net8 0 nmos_rvt w=560e-9 l=130e-9 nf=2 m=1
m6 voutp vbiasn net014 0 nmos_rvt w=560e-9 l=130e-9 nf=2 m=1
m8 voutp vbiasp1 net012 vdd pmos_rvt w=560e-9 l=130e-9 nf=2 m=1
m7 voutn vbiasp1 net06 vdd pmos_rvt w=560e-9 l=130e-9 nf=2 m=1
m10 net012 vbiasp2 vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=2 m=1
m9 net06 vbiasp2 vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=2 m=1
m4 net014 vinn net10 0 nmos_rvt w=560e-9 l=130e-9 nf=2 m=1
m3 net8 vinp net10 0 nmos_rvt w=560e-9 l=130e-9 nf=2 m=1
.ends telescopic_ota_sg13g2
** End of subcircuit definition.
