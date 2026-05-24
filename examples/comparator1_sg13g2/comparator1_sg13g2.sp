* comparator1 ported to IHP SG13G2 130nm.
* 4-level hierarchy from examples/comparator1:
*   INVERTER_1, INVERTER_2 (leaves) -> NAND_1 (leaf) ->
*   NAND (mid, 2x NAND_1) -> comparator (core, 12T + inv + nand) ->
*   comparator1_sg13g2 (wrapper, 1x comparator).
* Dual-input Strong Arm topology: two differential pairs (AN/AP, BN/BP)
* share cross-coupled PMOS/NMOS regeneration and clock-gated tail switches.
* Parametric sizing removed; all devices w=560n l=130n nf=4 m=1.

.subckt inverter_1 a vdd vss z
mn0 z a vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp1 z a vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends inverter_1

.subckt inverter_2 a vdd vss z
mn0 z a vss vss nmos_rvt w=560e-9 l=130e-9 nf=8 m=1
mp1 z a vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=8 m=1
.ends inverter_2

.subckt nand_1 a b z vdd vss
mn1 z   a mid vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn3 mid b vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp4 z   b vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends nand_1

.subckt nand a b vdd vss z
xi0 a b z vdd vss nand_1
xi1 b a z vdd vss nand_1
.ends nand

.subckt comparator an ap bn bp cki on op rdy vdd vss ock
mn0  op  on  net65 vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn1  on  op  net61 vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn2  net65 bn net67 vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn3  net67 ock vss  vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn4  net61 bp net67 vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn5  net65 an net60 vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn6  net60 ock vss  vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn7  net61 ap net60 vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp8  op  ock vdd   vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp9  on  ock vdd   vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp10 op  on  vdd   vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp11 on  op  vdd   vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
xi5 cki vdd vss net019 inverter_1
xi4 net019 vdd vss ock inverter_2
xi2 op on vdd vss rdy nand
.ends comparator

.subckt comparator1_sg13g2 an ap bn bp cki on op rdy vdd vss ock
xi1 an ap bn bp cki on op rdy vdd vss ock comparator
.ends comparator1_sg13g2
