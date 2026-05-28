* IHP CMP7345 Strong-Arm Latch Comparator (KrzysztofHerman/IHP__CMP7345)
* Hierarchical netlist for ALIGN. Original uses CC subcircuits with
* W=1u ng=1 unit cells x8; here we use W=1u nf=8 m=1 (same effective
* W=8u) because ALIGN's PnR handles the CC interleaving internally
* via exact_patterns.

** Differential input pair -- most critical for offset
.subckt dp_nmos dp dq tail vss
mn1 dp  vp tail vss nmos_rvt w=1000e-9 l=260e-9 nf=8 m=1
mn2 dq  vn tail vss nmos_rvt w=1000e-9 l=260e-9 nf=8 m=1
.ends dp_nmos

** NMOS cross-coupled regeneration latch
.subckt ccn_nmos outp outn sp sn vss
mn3 outp outn sp vss nmos_rvt w=1000e-9 l=260e-9 nf=8 m=1
mn4 outn outp sn vss nmos_rvt w=1000e-9 l=260e-9 nf=8 m=1
.ends ccn_nmos

** PMOS cross-coupled regeneration latch
.subckt ccp_pmos outp outn vdd
mp5 outp outn vdd vdd pmos_rvt w=1000e-9 l=260e-9 nf=4 m=1
mp6 outn outp vdd vdd pmos_rvt w=1000e-9 l=260e-9 nf=4 m=1
.ends ccp_pmos

** PMOS precharge switch pair (clock-gated reset)
.subckt rst_pmos a b clk vdd
ms1 a clk vdd vdd pmos_rvt w=750e-9 l=130e-9 nf=4 m=1
ms2 b clk vdd vdd pmos_rvt w=750e-9 l=130e-9 nf=4 m=1
.ends rst_pmos

** Top-level comparator
.subckt cmp7345_sg13g2 clk vdd vp vn vout1 vout2 vss
mn7   tail clk  vss vss nmos_rvt w=1000e-9 l=130e-9 nf=6 m=1
xdp   p    q    tail vss dp_nmos
xccn  vout1 vout2 p q vss ccn_nmos
xccp  vout1 vout2 vdd ccp_pmos
xrsti p    q    clk vdd rst_pmos
xrsto vout1 vout2 clk vdd rst_pmos
.ends cmp7345_sg13g2
