.subckt common_source_sg13g2 vin vop vdd 0
* Port of examples/common_source to IHP SG13G2 (planar 130 nm CMOS).
* Topology: NMOS common-source amplifier (mn0) with PMOS active load
* (mp0) diode-connected to VDD. Power/ground rails renamed from
* vcc/vss to vdd/0 following the SG13G2 example convention. Sizing
* mirrors the inverter / OTA primitives (w=560n l=130n nf=4 m=1) so we
* reuse already-validated Switch primitive shape variants. The
* original FinFET sizing (nfin=4 nf=2 m=4, no L/W) is FinFET-only.
mp0 vop vop vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn0 vop vin 0   0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends common_source_sg13g2
