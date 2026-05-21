"""MIM cap generator using IHP cmim PyCell as data source.

The IHP cmim PyCell emits drawing geometry on MIM/Vmim/Metal5/TopMetal1
but does not export its addPin() entries to the GDS. ALIGN's
gds2lefjson needs label-on-Label-datatype to register a port, so this
module wraps the PyCell call with explicit label injection:

    PLUS  -> TopMetal1.Label (126/25) at center of TopMetal1 box
    MINUS -> Metal5.Label    ( 67/25) at center of Metal5 box

The TopMetal1 box covers the via array; the Metal5 box is the
bottom plate. Both are single-rectangle in cmim, so center-of-bbox is
unambiguous.
"""

from __future__ import annotations

from pathlib import Path

from .klayout_runner import KLayoutRunError, fmt_micron, run_klayout_script


_CMIM_SCRIPT = '''
import pya

layout = pya.Layout()
layout.technology_name = "sg13g2"

params = {{"w": {w}, "l": {l}}}
pcell = layout.create_cell("cmim", "SG13_dev", params)
if pcell is None:
    raise SystemExit("cmim PyCell instantiation returned None")

top = layout.create_cell("{cell_name}")
top.insert(pya.DCellInstArray(pcell, pya.DTrans()))

# Bounding boxes for pin label positions
TM1_GDS = (126, 0)
M5_GDS  = ( 67, 0)
LABEL_DT = 25  # Per layers.json: Pin=2, Label=25

def _bbox_center(cell, gds_layer, gds_dt):
    li = layout.find_layer(gds_layer, gds_dt)
    if li is None:
        raise SystemExit(f"layer {{gds_layer}}/{{gds_dt}} not present in pcell")
    bbox = pya.Box()
    for sh in cell.shapes(li).each():
        bbox += sh.bbox()
    if bbox.empty():
        raise SystemExit(f"no shapes on {{gds_layer}}/{{gds_dt}} in pcell")
    return pya.Point(bbox.center().x, bbox.center().y)

# Search the instantiated PyCell variant cell for its drawing shapes
pcell_actual = layout.cell(top.each_inst().__next__().cell_index)
plus_pt  = _bbox_center(pcell_actual, *TM1_GDS)
minus_pt = _bbox_center(pcell_actual, *M5_GDS)

# Inject labels at TOP level so gds2lefjson sees them in the top cell after flatten
tm1_label_li = layout.layer(TM1_GDS[0], LABEL_DT)
m5_label_li  = layout.layer(M5_GDS[0],  LABEL_DT)
top.shapes(tm1_label_li).insert(pya.Text("PLUS", pya.Trans(plus_pt)))
top.shapes(m5_label_li ).insert(pya.Text("MINUS", pya.Trans(minus_pt)))

# Also inject Pin-datatype boxes so the LEF has a proper port geometry
PIN_DT = 2
tm1_pin_li = layout.layer(TM1_GDS[0], PIN_DT)
m5_pin_li  = layout.layer(M5_GDS[0],  PIN_DT)

def _bbox_of(cell, gds_layer, gds_dt):
    li = layout.find_layer(gds_layer, gds_dt)
    bbox = pya.Box()
    for sh in cell.shapes(li).each():
        bbox += sh.bbox()
    return bbox

plus_bbox  = _bbox_of(pcell_actual, *TM1_GDS)
minus_bbox = _bbox_of(pcell_actual, *M5_GDS)
top.shapes(tm1_pin_li).insert(plus_bbox)
top.shapes(m5_pin_li ).insert(minus_bbox)

# Skip klayout context-info cell; otherwise gdspy in ALIGN picks the wrong top
opts = pya.SaveLayoutOptions()
opts.write_context_info = False
layout.write("{out_gds}", opts)
print("OK cmim -> {out_gds} w={w} l={l}")
'''


def cmim_name(w: float, l: float) -> str:
    return f"CMIM_W{fmt_micron(w)}_L{fmt_micron(l)}"


def gen_cmim(w: float, l: float, out_dir: str | Path, name: str | None = None) -> Path:
    """Generate a CMIM black_box GDS via the IHP cmim PyCell.

    w, l: physical dimensions of the MIM cap (meters).
    out_dir: directory to write the GDS into. Created if absent.
    name: top cell + GDS basename. Defaults to CMIM_W<w>_L<l>.

    Returns path to the generated GDS.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if name is None:
        name = cmim_name(w, l)
    out_gds = out_dir / f"{name}.gds"
    script = _CMIM_SCRIPT.format(w=float(w), l=float(l), cell_name=name, out_gds=str(out_gds))
    run_klayout_script(script, log_prefix=name)
    if not out_gds.is_file():
        raise KLayoutRunError(f"klayout completed but {out_gds} missing")
    return out_gds
