# Checkpoint: Phase Q4 - V1.c1 closure via M1.Width bump (DONE)
Date: 2026-05-23
Plan: /home/montanares/.claude/plans/investiguemos-este-proyecto-todas-zesty-clarke.md
Branch: feature/ihp_sg13g2_pdk

## Scope

Phase Q4 target: close V1.c1 (235 errors, M1 endcap enclosure of V1).
Result: V1.c1 -> 0, single family closed. 687 -> 452 errors (34% reduction).

## What was done

### 1. Rule analysis

V1.c1 (sg13g2_maximal.drc:2451-2457) is a combined rule:
- V1.c: M1 enclosure of V1 >= 10nm on ALL sides
- V1.c1: M1 endcap enclosure >= 50nm on at least ONE pair of opposite sides
  (via KLayout `one_side_allowed, two_opposite_sides_allowed` parameters)

M1 runs vertically. Its Y-extension past V1 = m1_updated stoppoint - V1.WidthY/2
= 145 - 95 = 50nm. This satisfies the 50nm endcap requirement in Y.

The X-direction (perpendicular to M1) only needs V1.c = 10nm.
Required: M1.Width >= V1.WidthX + 2*10 = 190 + 20 = 210nm.

### 2. Single-field fix

`pdks/IHP_SG13G2_PDK/layers.json`: M1.Width 160 -> 210.

Validations:
- M1 space = 480 - 210 = 270nm >= M1.b (180nm IHP min) -- OK
- M1.Width = 210nm >= M1.a (160nm IHP min width) -- OK
- V0 coverage: M1 at 210 covers V0 at 160 by (210-160)/2 = 25nm each side -- OK
- V1 coverage: M1 at 210 covers V1 at 190 by (210-190)/2 = 10nm each side -- OK

No mos.py changes needed: m1_updated and m1_gate both read M1.Width from
layers.json dynamically. Stoppoints depend on V1 dimensions, not M1 width.

## DRC results (prototype mode, 4 GDSes)

| Rule    | Q3 TOTAL | Q4 TOTAL | Delta  | Status           |
|---------|----------|----------|--------|------------------|
| V1.c1   |      235 |        0 |   -235 | CLOSED (primary) |
| Cnt.c   |      195 |      195 |      0 |                  |
| Cnt.f   |      176 |      176 |      0 |                  |
| M3.b    |       39 |       39 |      0 |                  |
| pSD.b   |       20 |       20 |      0 |                  |
| pSD.a   |       10 |       10 |      0 |                  |
| Act.d   |        4 |        4 |      0 |                  |
| pSD.g   |        4 |        4 |      0 |                  |
| NW.a    |        2 |        2 |      0 |                  |
| NW.b    |        2 |        2 |      0 |                  |
| **SUM** |  **687** |  **452** | **-235** | **34% reduction** |

## Validations

- Mock PDK firewall: 22 passed, 731 skipped, 0 failed.
- LVS: inverter PASS, common_source PASS, telescopic_ota PASS, current_mirror_ota PASS.
- No new DRC rule families.
- align/, PlaceRouteHierFlow/, PnR.so untouched.

## Files modified

- `pdks/IHP_SG13G2_PDK/layers.json` (M1.Width 160 -> 210)

## Definition of Done (4/4)

1. V1.c1 -> 0 across 4 GDSes -- DONE.
2. Mock firewall 22/731/0 -- DONE.
3. 4-circuit LVS PASS -- DONE.
4. No new DRC rule families -- DONE.

## Phase Q+ deuda (post-Q4, 452 errors, 9 families)

1. **Cnt.c + Cnt.f (Q5, 371 errors)**: contact-stack retrofit.
2. **M3.b (Q6, 39 errors)**: engine-side M3.Pitch audit.
3. **pSD/NW/Act (Q7, 38 errors)**: PMOS region drawing.
4. **Density (Q_signoff)**: fill-cell generation.
5. Carryover: Docker rebuild, Mock harmonisation, symmetric OTA, router
   cleanup, AspectRatio auto-relax, translator nested-subckt, pytest scaffold.

## DRC progression

| Phase | Errors | Families | Closed this phase                         |
|-------|--------|----------|-------------------------------------------|
| Q1    |  1,394 |       15 | density (deferred, -36)                   |
| Q2    |    866 |       13 | CntB.d (-440), CntB.g (-88)              |
| Q3    |    687 |       10 | CntB.h (-88), M1.c (-88), M1.c1 (-44)    |
| Q4    |    452 |        9 | V1.c1 (-235)                              |
