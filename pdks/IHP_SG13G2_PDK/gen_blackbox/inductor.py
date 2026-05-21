"""Spiral inductor generator using IHP inductors/inductor2/inductor3 PyCells.

The three IHP variants share the same `inductors_code.py` base; the
subclasses just bind a `model` and a minimum `DMIN`:
    inductor2  -> 2 terminals (LA, LB),       DMIN = 15.48u, NR >= 1
    inductor3  -> 3 terminals (LA, LB, LC),   DMIN = 25.84u, NR >= 2

The PyCell writes pin rectangles on TopMetal1.pin (126/2) or
TopMetal2.pin (134/2):
    inductor2 nr_r==1 -> both pins on TM2.pin
    inductor2 nr_r>1  -> both pins on TM1.pin
    inductor3         -> LC on TM2.pin (centered), LA/LB on TM1.pin (+-x)

ALIGN's gds2lefjson keys ports off `pya.Text` labels coincident with
polygons on a "Label" datatype declared in layers.json. layers.json for
SG13G2 declares TM1/TM2 with Label=25 and Pin=2. We:
    1. enumerate pin-datatype boxes from both TM1 and TM2
    2. sort by centroid.x
    3. for 2 boxes -> [LA, LB]; for 3 boxes -> [LA, LC, LB]
    4. inject a pya.Text on the same layer's Label datatype at each centroid
    5. re-emit each pin box on the TOP cell (so flattening is irrelevant)
"""

from __future__ import annotations

from pathlib import Path

from .klayout_runner import KLayoutRunError, fmt_micron, run_klayout_script


_INDUCTOR_SCRIPT = '''
import pya

layout = pya.Layout()
layout.technology_name = "sg13g2"

params = {pcell_params}
pcell = layout.create_cell("{pcell}", "SG13_dev", params)
if pcell is None:
    raise SystemExit("{pcell} PyCell instantiation returned None")

top = layout.create_cell("{cell_name}")
top.insert(pya.DCellInstArray(pcell, pya.DTrans()))

TM1_GDS = 126
TM2_GDS = 134
LABEL_DT = 25
PIN_DT = 2

pcell_actual = layout.cell(top.each_inst().__next__().cell_index)

tm1_pin_li = layout.find_layer(TM1_GDS, PIN_DT)
tm2_pin_li = layout.find_layer(TM2_GDS, PIN_DT)


def _good_boxes(cell, li):
    out = []
    if li is None:
        return out
    for sh in cell.shapes(li).each():
        b = sh.bbox()
        if b.width() > 0 and b.height() > 0:
            out.append(b)
    return out


pin_boxes = []
for b in _good_boxes(pcell_actual, tm1_pin_li):
    pin_boxes.append((b, TM1_GDS))
for b in _good_boxes(pcell_actual, tm2_pin_li):
    pin_boxes.append((b, TM2_GDS))

expected = {expected_pins}
if len(pin_boxes) != expected:
    raise SystemExit(
        "expected " + str(expected) + " pin boxes on TM1/TM2 datatype 2, got " + str(len(pin_boxes))
    )

pin_boxes.sort(key=lambda p: p[0].center().x)
if expected == 2:
    names = ["LA", "LB"]
else:
    names = ["LA", "LC", "LB"]

tm1_label_out = layout.layer(TM1_GDS, LABEL_DT)
tm1_pin_out   = layout.layer(TM1_GDS, PIN_DT)
tm2_label_out = layout.layer(TM2_GDS, LABEL_DT)
tm2_pin_out   = layout.layer(TM2_GDS, PIN_DT)

for (box, src_gds), name in zip(pin_boxes, names):
    if src_gds == TM1_GDS:
        label_li = tm1_label_out
        pin_li = tm1_pin_out
    else:
        label_li = tm2_label_out
        pin_li = tm2_pin_out
    top.shapes(label_li).insert(pya.Text(name, pya.Trans(box.center().x, box.center().y)))
    top.shapes(pin_li).insert(box)

opts = pya.SaveLayoutOptions()
opts.write_context_info = False
layout.write("{out_gds}", opts)
print("OK {pcell} -> {out_gds}")
'''


_VARIANT_INFO = {
    "inductor2": {"pins": 2, "dmin_um": 15.48, "min_nr": 1, "default_nr": 1},
    "inductor3": {"pins": 3, "dmin_um": 25.84, "min_nr": 2, "default_nr": 2},
}


def _ind_name(pcell: str, w: float, s: float, d: float, nr: int) -> str:
    return (
        f"{pcell.upper()}_W{fmt_micron(w)}_S{fmt_micron(s)}_D{fmt_micron(d)}_NR{nr}"
    )


def _gen_inductor(
    pcell: str,
    w: float,
    s: float,
    d: float,
    nr: int,
    out_dir: str | Path,
    name: str | None = None,
) -> Path:
    info = _VARIANT_INFO[pcell]
    nr = int(nr)
    if nr < info["min_nr"]:
        raise ValueError(
            f"{pcell} requires nr_r >= {info['min_nr']}, got {nr}"
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if name is None:
        name = _ind_name(pcell, w, s, d, nr)
    out_gds = out_dir / f"{name}.gds"

    pcell_params = {
        "model": pcell,
        "w": f"{w*1e6}u",
        "s": f"{s*1e6}u",
        "d": f"{d*1e6}u",
        "nr_r": nr,
    }

    script = _INDUCTOR_SCRIPT.format(
        pcell=pcell,
        pcell_params=repr(pcell_params),
        cell_name=name,
        out_gds=str(out_gds),
        expected_pins=info["pins"],
    )
    run_klayout_script(script, log_prefix=name)
    if not out_gds.is_file():
        raise KLayoutRunError(f"klayout completed but {out_gds} missing")
    return out_gds


def gen_inductor2(
    w: float,
    s: float,
    d: float,
    nr: int,
    out_dir: str | Path,
    name: str | None = None,
) -> Path:
    """inductor2 (2-terminal). nr>=1; if d below 15.48u the PyCell bumps it."""
    return _gen_inductor("inductor2", w, s, d, nr, out_dir, name=name)


def gen_inductor3(
    w: float,
    s: float,
    d: float,
    nr: int,
    out_dir: str | Path,
    name: str | None = None,
) -> Path:
    """inductor3 (3-terminal, LC = center tap). nr>=2; PyCell DMIN=25.84u."""
    return _gen_inductor("inductor3", w, s, d, nr, out_dir, name=name)


def default_dmin(pcell: str) -> float:
    """Return DMIN (meters) for the requested PyCell variant."""
    return _VARIANT_INFO[pcell]["dmin_um"] * 1e-6


def default_nr(pcell: str) -> int:
    """Return the minimum recommended nr_r for the requested PyCell variant."""
    return _VARIANT_INFO[pcell]["default_nr"]
