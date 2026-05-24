* Bandgap voltage reference -- IHP SG13G2
* Simplified Widlar-style: PMOS current mirror + diode-connected NPNs
* with degeneration resistors providing PTAT compensation.
*
* VREF ~ VBE + (kT/q)*ln(N)*(R2/R1) where N = area ratio (Q2 has 8x Nx)
*
.subckt bandgap_ref_sg13g2 vref vdd vss
* PMOS current mirror
mp1 n1 n1 vdd vdd pmos_rvt w=2e-6 l=500e-9 nf=4 m=1
mp2 vref n1 vdd vdd pmos_rvt w=2e-6 l=500e-9 nf=4 m=1
* NPN BJTs -- Q1 is 1x, Q2 is 1x (area ratio via separate Nx in blackbox)
Q1 n1 n1 n2 npn13g2
Q2 vref vref n3 npn13g2
* Degeneration resistors
R1 n2 vss rsil w=500e-9 l=5e-6 ps=500e-9
R2 n3 vss rsil w=500e-9 l=20e-6 ps=500e-9
.ends bandgap_ref_sg13g2
