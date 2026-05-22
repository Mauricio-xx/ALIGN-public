.subckt current_mirror_ota_sg13g2 id vinn vinp 0 vdd voutp vbiasnd
* Port of examples/current_mirror_ota to IHP SG13G2 (planar 130 nm CMOS).
* 12-MOS 1:1 current-mirror OTA: NMOS input pair (m17/m15) + NMOS tail
* current source (m16/m14) + NMOS output mirror (m11/m10) and a PMOS
* mirror with cascode atop on the VDD side. m20s sits atop m20 sharing
* gate=net16 with a private internal node m20stack between them
* (m20.D=m20stack, m20s.S=m20stack); same for m18/m18s on net27 with
* m18stack. ALIGN's compiler preprocess (align/compiler/preprocess.py
* add_series_devices, lines 308-369) recognises these {D,S}-coupled
* same-model same-gate same-params pairs and collapses each pair into
* one device with STACK=2, dropping the higher-named partner. The PDK
* primitive layout (pdks/IHP_SG13G2_PDK/mos.py:59 gate=(2*gate)*stack)
* draws the stacked form, but KLayout's LVS extraction folds the two
* series fingers into a single device with W=w*nf, L=L -- producing 10
* extracted MOS for the 12 in the user SPICE. The Phase L line-by-line
* translator did not mirror add_series_devices and emitted 12 MOS in
* the .lvs.sp, causing a 12-vs-10 device-count mismatch. Phase N adds
* series-stack merging to the translator (spice_to_ihp_lvs.py) so the
* emitted LVS netlist matches the extracted layout.
* Uniform sizing w=560n l=130n nf=4 m=1 mirrors the OTA / inverter /
* common_source ports.
m17 net16 vinn net24 0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m16 net24 id   0     0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m15 net27 vinp net24 0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m14 id    id   0     0   nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m11 vbiasnd vbiasnd 0 0  nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m10 voutp   vbiasnd 0 0  nmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m21 net16    net16 vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m20 m20stack net16 vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m20s vbiasnd net16 m20stack vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m19 net27    net27 vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m18 m18stack net27 vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
m18s voutp   net27 m18stack vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1
.ends current_mirror_ota_sg13g2
