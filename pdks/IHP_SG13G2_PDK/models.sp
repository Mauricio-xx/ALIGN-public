.model nfet nmos l=1 w=1 nf=1 m=1  stack=1 parallel=1
.model pfet pmos l=1 w=1 nf=1 m=1  stack=1 parallel=1
.model nmos_rvt nmos l=1 w=1 nf=1 m=1  stack=1 parallel=1
.model pmos_rvt pmos l=1 w=1 nf=1 m=1  stack=1 parallel=1
.model nfet_3p3V nmos l=1 w=1 nf=1 m=1  stack=1 parallel=1
.model pfet_3p3V pmos l=1 w=1 nf=1 m=1  stack=1 parallel=1
.model nmosHV nmos l=1 w=1 nf=1 m=1  stack=1 parallel=1
.model pmosHV pmos l=1 w=1 nf=1 m=1  stack=1 parallel=1
.model resistor res r=1
.model capacitor cap l=1 w=1 m=1
.model inductor ind ind=1
* NPN BJTs (IHP SG13G2)
.model npn13g2  npn we=1 le=1 nx=1 m=1
.model npn13g2l npn we=1 le=1 nx=1 m=1
.model npn13g2v npn we=1 le=1 nx=1 m=1
* PNP BJT
.model pnpmpa pnp w=1 l=1 m=1
* Poly resistors (2-terminal for P&R; substrate implicit)
.model rsil  res w=1 l=1 ps=1 m=1
.model rppd  res w=1 l=1 ps=1 b=0 m=1
.model rhigh res w=1 l=1 ps=1 b=0 m=1
* MIM capacitors
.model cap_cmim cap w=1 l=1 m=1
.model rfcmim   cap w=1 l=1 m=1
