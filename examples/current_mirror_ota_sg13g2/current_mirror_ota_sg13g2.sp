.subckt current_mirror_ota_sg13g2 id vinn vinp 0 vdd voutp vbiasnd
* Port of examples/current_mirror_ota to IHP SG13G2 (planar 130 nm CMOS).
* 10-MOS 1:1 current-mirror OTA: NMOS input pair (m17/m15) + NMOS tail
* current source (m16/m14) + NMOS output mirror (m11/m10) and a PMOS
* 1:1 mirror (m21 diode + m20 mirror, and m19 diode + m18 mirror) on
* the VDD side. The original FinFET netlist included cascode stack
* transistors m20s and m18s sitting atop m20/m18 with the SAME gate
* (net16/net27) -- a "double-channel" mirror that ALIGN's preprocess
* recognises as a series stack (align/compiler/preprocess.py
* add_series_devices) and collapses into one device with STACK=2 by
* dropping m20s/m18s. The resulting layout therefore contains only the
* base mirror transistor, while the unmodified LVS schematic still
* lists the stack partner -- producing a 10-vs-12 mismatch on the PMOS
* side. The Phase L translator does not mirror this preprocess
* transformation (deuda item: "translator: stack/parallel merge to
* mirror align.compiler.preprocess"). To keep Phase M atomic, the
* cascode atop transistors are dropped here -- the resulting circuit
* exercises the same primitives (SCM_PMOS/SCM_NMOS/DP_NMOS_B) without
* the stack-merge pitfall. Uniform sizing w=560n l=130n nf=4 m=1
* mirrors the OTA / inverter / common_source ports.
m17 net16 vinn net24 0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m16 net24 id   0     0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m15 net27 vinp net24 0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m14 id    id   0     0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m11 vbiasnd vbiasnd 0 0  nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m10 voutp   vbiasnd 0 0  nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m21 net16 net16 vdd vdd  pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m20 vbiasnd net16 vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m19 net27 net27 vdd vdd  pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m18 voutp net27 vdd vdd  pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends current_mirror_ota_sg13g2
