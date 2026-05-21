## Fully differential Telescopic OTA - IHP SG13G2 130nm planar port

Port of `examples/telescopic_ota` to the IHP SG13G2 PDK. The schematic is structurally
identical to the original (10 MOS devices, cascode + diff pair + current mirrors) but
`l` was bumped from 20 nm (the FinFET14 native length) to 130 nm to land in the SG13G2
LV process window. Models `nmos_rvt` / `pmos_rvt` are aliases of `nfet` / `pfet`
declared in `pdks/IHP_SG13G2_PDK/models.sp`.

### Run end-to-end

```bash
python -m align.schematic2layout examples/telescopic_ota_sg13g2 \
    -p pdks/IHP_SG13G2_PDK \
    -w /tmp/sg13_ota_run
```

### DRC the generated GDS

```bash
export IHP_PDK_ROOT=/path/to/IHP-Open-PDK
bash pdks/IHP_SG13G2_PDK/tools/sg13g2_drc.sh \
    /tmp/sg13_ota_run/3_pnr/Results/TELESCOPIC_OTA_SG13G2_0.gds
```

`--mode maximal` runs the full deck; the default `minimal` runs only the foundry
precheck subset.
