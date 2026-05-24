* Low Dropout Regulator -- IHP SG13G2
* 5T OTA error amplifier + PMOS pass transistor + RSIL feedback divider.
* VOUT = VREF * (1 + R1/R2). Equal resistors give VOUT = 2*VREF.
*
* Mixed-signal: resistor divider requires blackbox GDS (two-pass flow).

.subckt ldo_sg13g2 vout vdd vss vref vbias

* Error amplifier -- 5T OTA
mn_tail tail vbias vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn1 vg   vref tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn2 mir  vfb  tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp1 vg   mir  vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mp2 mir  mir  vdd  vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1

* Pass transistor -- wide PMOS, low dropout
mp_pass vout vg vdd vdd pmos_rvt w=2e-6 l=500e-9 nf=4 m=1

* Feedback resistor divider
R1 vout vfb rsil w=500e-9 l=10e-6 ps=500e-9
R2 vfb  vss rsil w=500e-9 l=10e-6 ps=500e-9

.ends ldo_sg13g2
