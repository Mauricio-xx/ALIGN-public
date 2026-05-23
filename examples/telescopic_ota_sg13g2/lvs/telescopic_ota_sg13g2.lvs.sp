* LVS reference netlist for IHP SG13G2 telescopic OTA.
* Mirrors telescopic_ota_sg13g2.sp but with the IHP model names
* (sg13_lv_nmos / sg13_lv_pmos) and effective device width (nf=4
* fingers collapsed into W=2.24u to match ALIGN-generated layout).
* Subckt name matches the GDS top cell TELESCOPIC_OTA_SG13G2_0.

.SUBCKT TELESCOPIC_OTA_SG13G2_0 vbiasn vbiasp1 vbiasp2 vinn vinp voutn voutp id vdd 0
m1  id      id      0       0   sg13_lv_nmos L=0.13u W=2.24u
m2  net10   id      0       0   sg13_lv_nmos L=0.13u W=2.24u
m5  voutn   vbiasn  net8    0   sg13_lv_nmos L=0.13u W=2.24u
m6  voutp   vbiasn  net014  0   sg13_lv_nmos L=0.13u W=2.24u
m8  voutp   vbiasp1 net012  vdd sg13_lv_pmos L=0.13u W=2.24u
m7  voutn   vbiasp1 net06   vdd sg13_lv_pmos L=0.13u W=2.24u
m10 net012  vbiasp2 vdd     vdd sg13_lv_pmos L=0.13u W=2.24u
m9  net06   vbiasp2 vdd     vdd sg13_lv_pmos L=0.13u W=2.24u
m4  net014  vinn    net10   0   sg13_lv_nmos L=0.13u W=2.24u
m3  net8    vinp    net10   0   sg13_lv_nmos L=0.13u W=2.24u
.ENDS TELESCOPIC_OTA_SG13G2_0
