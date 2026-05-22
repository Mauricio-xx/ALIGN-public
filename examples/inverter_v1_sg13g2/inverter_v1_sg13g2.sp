.subckt inverter_v1_sg13g2 vin vout vdd 0
* Port of examples/inverter_v1 to IHP SG13G2 (planar 130 nm CMOS).
* Sizing copied from telescopic_ota_sg13g2 primitives (w=560n nf=4 m=1)
* so we reuse already-validated Switch primitive shape variants. The
* original FinFET sizing (w=270n l=20n nfin=6) is not applicable to
* SG13G2 because L=20n violates the minimum gate length and `nfin` is
* FinFET-only. `vss` renamed to `0` to follow the ALIGN convention
* used in the OTA example. Effective W after finger folding is
* 560n * 4 = 2.24u for each device.
mp1 vout vin vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
mn1 vout vin 0    0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends inverter_v1_sg13g2
