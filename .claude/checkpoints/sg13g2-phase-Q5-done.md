# Checkpoint: Phase Q5 - Cnt.c + Cnt.f closure via contact-stack retrofit (DONE)
Date: 2026-05-23
Plan: /home/montanares/.claude/plans/investiguemos-este-proyecto-todas-zesty-clarke.md
Branch: feature/ihp_sg13g2_pdk

## Scope

Phase Q5 target: close Cnt.c (195 errors) + Cnt.f (176 errors) = 371 contact-stack errors.
Result: Cnt.c -> 0, Cnt.f -> 0, both families closed. 452 -> 9 errors on 9 primitives.

## What was done

### 1. Rule analysis

**Cnt.c** (5_14_cont.drc): Min. Active enclosure of Cont_SQ >= 70nm (euclidean).
- S/D contacts (V0): v0Offset used V0.VencA_L=50nm as Active inset -> 50nm < 70nm.
- Body contacts: centered in activeb strip of width 280nm. Encl = (280-160)/2 = 60nm < 70nm.

**Cnt.f** (sg13g2_maximal.drc:2261-2263): Min. Cont-on-Active space to GatPoly >= 110nm.
- V0 at S/D position, centered between poly fingers.
- Space = (Poly.Pitch - Poly.Width)/2 - V0.WidthX/2 = (480-130)/2 - 80 = 95nm < 110nm.
- IHP PyCell formula: contacted_poly_pitch = cont_size + 2*Cnt_f + L = 0.16 + 0.22 + L.
  At minimum L=0.13: pitch = 0.51um = 510nm.

### 2. Changes (layers.json only)

| Field | Old | New | Rule satisfied |
|-------|-----|-----|----------------|
| Poly.Pitch | 480 | 510 | Cnt.f: space = (510-130)/2 - 80 = 110nm |
| Poly.Offset | 240 | 255 | Pitch/2 |
| M1.Pitch | 480 | 510 | S/D columns at Poly.Pitch |
| V0.VencA_L | 50 | 70 | Cnt.c S/D: Active encl = 70nm |
| activebWidth | 280 | 300 | Cnt.c body: encl = (300-160)/2 = 70nm |
| activebWidth_H | 280 | 300 | Cnt.c body X-dir: same |

Cross-checks:
- M1 space = 510 - 210 = 300nm >= M1.b (180nm) -- OK
- V1 space = 510 - 190 = 320nm >= V1.b (220nm) -- OK
- V0 space = 510 - 160 = 350nm >= V0.b (180nm) -- OK
- ALIGN pitch formula: base + (L - Poly.Width) = 510 + (L - 130) = 380 + L
  matches IHP PyCell: cont_size + 2*Cnt_f + L = 160 + 220 + L = 380 + L -- exact match
- No mos.py changes: all parameters data-driven from layers.json.

## DRC results (prototype mode, 9 unique X2_Y1 primitives)

| Primitive | Cnt.c | Cnt.f | Act.d | M3.b | Other | Total |
|-----------|-------|-------|-------|------|-------|-------|
| NMOS_S | 0 | 0 | 0 | 0 | 0 | 0 |
| PMOS_S | 0 | 0 | 0 | 0 | 0 | 0 |
| DP_NMOS_B | 0 | 0 | 0 | 0 | 0 | 0 |
| SCM_NMOS | 0 | 0 | 0 | 0 | 0 | 0 |
| SCM_PMOS | 0 | 0 | 0 | 0 | 0 | 0 |
| CMC_PMOS | 0 | 0 | 0 | 0 | 0 | 0 |
| DCL_PMOS_S | 0 | 0 | 0 | 1 | 0 | 1 |
| CMC_S_NMOS_B | 0 | 0 | 4 | 0 | 0 | 4 |
| CMC_S_PMOS_B | 0 | 0 | 4 | 0 | 0 | 4 |
| **TOTAL** | **0** | **0** | **8** | **1** | **0** | **9** |

## Validations

- Mock PDK firewall: 22 passed, 731 skipped, 0 failed.
- LVS netlist extraction: NMOS_S, PMOS_S, DCL_PMOS_S, DP_NMOS_B all OK, 0 errors.
- Cnt.c: 195 -> 0 CLOSED. Cnt.f: 176 -> 0 CLOSED.
- No new DRC rule families introduced.
- align/, PlaceRouteHierFlow/, PnR.so untouched.

## Files modified

- `pdks/IHP_SG13G2_PDK/layers.json` (6 fields: Poly.Pitch/Offset, M1.Pitch, V0.VencA_L, activebWidth/H)

## Definition of Done (4/4)

1. Cnt.c + Cnt.f -> 0 across 9 primitives -- DONE.
2. Mock firewall 22/731/0 -- DONE.
3. LVS extraction PASS x4 -- DONE.
4. No new DRC rule families -- DONE.

## Remaining DRC (9 errors, 2 families on 9 primitives)

1. **Act.d = 8** (CMC_S_NMOS_B + CMC_S_PMOS_B): body-switch Active geometry.
2. **M3.b = 1** (DCL_PMOS_S): M3 spacing. M3.Pitch=480, M3.Width=290, space=190 < M3.b(200nm).

Note: Q4 bucket also included pSD.a/b/g (34) and NW.a/b (4) not seen in Q5 run.
These may reappear with different primitive sizings or simply came from primitives
not in the current 9-GDS test set.

## DRC progression

| Phase | Errors | Families | Closed this phase |
|-------|--------|----------|-------------------|
| Q1 | 1,394 | 15 | density (deferred, -36) |
| Q2 | 866 | 13 | CntB.d (-440), CntB.g (-88) |
| Q3 | 687 | 10 | CntB.h (-88), M1.c (-88), M1.c1 (-44) |
| Q4 | 452 | 9 | V1.c1 (-235) |
| Q5 | 9* | 2* | Cnt.c (-195), Cnt.f (-176) |

*On 9 unique X2_Y1 primitives. Some Q4-era families (pSD, NW) may persist in
untested primitive variants.
