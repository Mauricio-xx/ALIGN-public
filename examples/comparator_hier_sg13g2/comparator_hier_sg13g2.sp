* Hierarchical comparator with clock buffer and NAND ready output.
* 3-level hierarchy: clk_inv / nand_half (leaves) -> nand_rdy (mid) -> top.
* IHP SG13G2 130nm, w=560n l=130n nf=4 m=1.
* Ported from examples/comparator1 (dual-input simplified to single-input).

.subckt clk_inv a vdd vss z
mn0 z a vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp1 z a vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends clk_inv

.subckt nand_half a b z vdd vss
mn0 z   a mid vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn1 mid b vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp2 z   b vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends nand_half

.subckt nand_rdy a b vdd vss z
xi0 a b z vdd vss nand_half
xi1 b a z vdd vss nand_half
.ends nand_rdy

.subckt comparator_hier_sg13g2 inp inn clk outp outn rdy vdd vss
mn0  outp outn net_dp vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn1  outn outp net_dn vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn2  net_dp inp net_tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn3  net_dn inn net_tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn4  net_tail ock vss  vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp5  outp ock vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp6  outn ock vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp7  outp outn vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp8  outn outp vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
xi_ck0 clk   vdd vss clk_n clk_inv
xi_ck1 clk_n vdd vss ock   clk_inv
xi_rdy outp  outn vdd vss rdy nand_rdy
.ends comparator_hier_sg13g2
