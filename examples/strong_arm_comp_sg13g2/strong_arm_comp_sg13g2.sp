.subckt strong_arm_comp_sg13g2 clk vdd vin vip von vop vss
* Strong Arm dynamic comparator ported to IHP SG13G2 130nm.
* Topology from examples/high_speed_comparator.
*
* mn0: NMOS tail current source (clk-gated evaluation).
* mn1/mn2: NMOS differential input pair.
* mn3/mn4: NMOS cross-coupled regeneration latch.
* mp5/mp6: PMOS cross-coupled regeneration latch.
* mp7/mp8: PMOS precharge switches for intermediate nodes.
* mp9/mp10: PMOS precharge switches for output nodes.
* mp11/mn13: output buffer (inverter) for vop.
* mp12/mn14: output buffer (inverter) for von.
mn0  vcom clk  vss  vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn1  vin_d vin vcom vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn2  vip_d vip vcom vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn3  vin_o vip_o vin_d vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn4  vip_o vin_o vip_d vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp5  vin_o vip_o vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp6  vip_o vin_o vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp7  vin_d clk  vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp8  vip_d clk  vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp9  vin_o clk  vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp10 vip_o clk  vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp11 vop vip_o vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn13 vop vip_o vss  vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp12 von vin_o vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn14 von vin_o vss  vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends strong_arm_comp_sg13g2
