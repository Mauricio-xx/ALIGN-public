.subckt telescopic_ota_sg13g2 vbiasn vbiasp1 vbiasp2 vinn vinp voutn voutp id vdd 0
* All devices uniformly sized at NF=4 M=1, W=560n. nf=4 gives the placer
* both a tall X1_Y2 and wide X2_Y1 shape variant per primitive.
* Explicit V-axis SymmetricBlocks in .const.json define the 5 differential
* pairs for proper analog symmetry. Sizing is symbolic; this example
* exercises topology + primitive generation, not analog performance.
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
