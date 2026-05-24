* Differential pair with PMOS current mirror load.
* 2-level hierarchy: cm_pmos_load leaf inside diff_pair_hier_sg13g2.
* IHP SG13G2 130nm, w=560n l=130n nf=4 m=1.

.subckt cm_pmos_load out_d out_m vdd
mp0 out_d out_d vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp1 out_m out_d vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends cm_pmos_load

.subckt diff_pair_hier_sg13g2 vin vip voutn voutp vbias vdd vss
mn0 tail vbias vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn1 voutn vin  tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn2 voutp vip  tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
xi_load voutn voutp vdd cm_pmos_load
.ends diff_pair_hier_sg13g2
