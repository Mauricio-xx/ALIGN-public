"""BJT NPN device generator using IHP npn13G2/npn13G2L/npn13G2V PyCells.

The PyCells emit collector and base on Metal1, emitter on Metal2.
Substrate is implicit ('sub!' global per IHP convention); no S port is
emitted -- callers wanting an explicit substrate net must add a ring
themselves at a higher level.

Label/pin injection strategy (applied at the wrapping top cell so
that ALIGN's gds2lefjson sees the labels after flatten):

    C -> Metal1.Label (8/25) at center of max-y Metal1 bbox
    B -> Metal1.Label (8/25) at center of min-y Metal1 bbox
    E -> Metal2.Label (10/25) at center of largest-area Metal2 bbox

Pin shapes are re-emitted on Metal1.Pin (8/2) and Metal2.Pin (10/2)
so the LEF gets a proper PORT geometry per terminal.
"""

from __future__ import annotations

from pathlib import Path

from .klayout_runner import KLayoutRunError, fmt_micron, run_klayout_script


_BJT_SCRIPT = '''
import pya

layout = pya.Layout()
layout.technology_name = "sg13g2"

params = {pcell_params}
pcell = layout.create_cell("{pcell}", "SG13_dev", params)
if pcell is None:
    raise SystemExit("{pcell} PyCell instantiation returned None")

M1_DRAW = (8, 0)
M2_DRAW = (10, 0)
LABEL_DT = 25
PIN_DT = 2

# ALIGN routing grid (layers.json) -- pin centers must land on tracks
M1_PITCH = 510
M2_PITCH = 560
M1_HALF_W = 105
M2_HALF_H = 145

def _snap(val, pitch):
    return int(round(val / pitch)) * pitch

# Resolve PCell, compute grid-aligned shift so cell starts at (0,0)
_tmp = layout.create_cell("_resolve")
_tmp.insert(pya.DCellInstArray(pcell, pya.DTrans()))
_pcell_actual = layout.cell(_tmp.each_inst().__next__().cell_index)
_pbb = _pcell_actual.bbox()
dx = ((-_pbb.left + M1_PITCH - 1) // M1_PITCH) * M1_PITCH if _pbb.left < 0 else 0
dy = ((-_pbb.bottom + M2_PITCH - 1) // M2_PITCH) * M2_PITCH if _pbb.bottom < 0 else 0

# Clear native Pin/Label shapes from PyCell (may be off-grid)
for _ln, _dt in [(M1_DRAW[0], PIN_DT), (M2_DRAW[0], PIN_DT),
                 (M1_DRAW[0], LABEL_DT), (M2_DRAW[0], LABEL_DT)]:
    _li = layout.find_layer(_ln, _dt)
    if _li is not None:
        _pcell_actual.shapes(_li).clear()

# Read pin boxes from Draw shapes (native coordinates)
m1_li = layout.find_layer(*M1_DRAW)
m2_li = layout.find_layer(*M2_DRAW)
if m1_li is None:
    raise SystemExit("no Metal1 shapes in {pcell}")
if m2_li is None:
    raise SystemExit("no Metal2 shapes in {pcell}")

def _good_boxes(cell, li):
    out = []
    for sh in cell.shapes(li).each():
        b = sh.bbox()
        if b.width() > 0 and b.height() > 0:
            out.append(b)
    return out

m1_boxes = _good_boxes(_pcell_actual, m1_li)
m2_boxes = _good_boxes(_pcell_actual, m2_li)
if len(m1_boxes) < 2:
    raise SystemExit(f"expected >=2 Metal1 boxes for {pcell}, got {{len(m1_boxes)}}")
if not m2_boxes:
    raise SystemExit(f"expected Metal2 box for {pcell} emitter, got 0")

m1_boxes.sort(key=lambda b: b.center().y)
b_box = m1_boxes[0]
c_box = m1_boxes[-1]
e_box = max(m2_boxes, key=lambda b: b.width() * b.height())

layout.delete_cells([_tmp.cell_index()])

# Create top cell with shifted pcell (all shapes in positive territory)
top = layout.create_cell("{cell_name}")
top.insert(pya.CellInstArray(pcell.cell_index(), pya.Trans(pya.Vector(dx, dy))))

m1_draw_out = layout.layer(*M1_DRAW)
m2_draw_out = layout.layer(*M2_DRAW)
m1_label_li = layout.layer(M1_DRAW[0], LABEL_DT)
m1_pin_li   = layout.layer(M1_DRAW[0], PIN_DT)
m2_label_li = layout.layer(M2_DRAW[0], LABEL_DT)
m2_pin_li   = layout.layer(M2_DRAW[0], PIN_DT)

# Collector (M1 vertical): snap shifted center_x to M1 track
c_sx = _snap(c_box.center().x + dx, M1_PITCH)
c_hw = max(c_box.width() // 2, M1_HALF_W)
c_pin = pya.Box(c_sx - c_hw, c_box.bottom + dy, c_sx + c_hw, c_box.top + dy)
c_ext = pya.Box(min(c_box.left + dx, c_pin.left), c_box.bottom + dy,
                max(c_box.right + dx, c_pin.right), c_box.top + dy)
top.shapes(m1_draw_out).insert(c_ext)
top.shapes(m1_pin_li).insert(c_pin)
top.shapes(m1_label_li).insert(pya.Text("C", pya.Trans(c_sx, c_box.center().y + dy)))

# Base (M1 vertical): snap shifted center_x to M1 track
b_sx = _snap(b_box.center().x + dx, M1_PITCH)
b_hw = max(b_box.width() // 2, M1_HALF_W)
b_pin = pya.Box(b_sx - b_hw, b_box.bottom + dy, b_sx + b_hw, b_box.top + dy)
b_ext = pya.Box(min(b_box.left + dx, b_pin.left), b_box.bottom + dy,
                max(b_box.right + dx, b_pin.right), b_box.top + dy)
top.shapes(m1_draw_out).insert(b_ext)
top.shapes(m1_pin_li).insert(b_pin)
top.shapes(m1_label_li).insert(pya.Text("B", pya.Trans(b_sx, b_box.center().y + dy)))

# Emitter (M2 horizontal): snap shifted center_y to M2 track
e_sy = _snap(e_box.center().y + dy, M2_PITCH)
e_hh = max(e_box.height() // 2, M2_HALF_H)
e_pin = pya.Box(e_box.left + dx, e_sy - e_hh, e_box.right + dx, e_sy + e_hh)
e_ext = pya.Box(e_box.left + dx, min(e_box.bottom + dy, e_pin.bottom),
                e_box.right + dx, max(e_box.top + dy, e_pin.top))
top.shapes(m2_draw_out).insert(e_ext)
top.shapes(m2_pin_li).insert(e_pin)
top.shapes(m2_label_li).insert(pya.Text("E", pya.Trans(e_box.center().x + dx, e_sy)))

# Grid-align cell bounding box starting at (0,0)
_fb = top.bbox()
_x1 = -(-_fb.right // M1_PITCH) * M1_PITCH
_y1 = -(-_fb.top // M2_PITCH) * M2_PITCH
top.shapes(layout.layer(100, 5)).insert(pya.Box(0, 0, _x1, _y1))

opts = pya.SaveLayoutOptions()
opts.write_context_info = False
layout.write("{out_gds}", opts)
print("OK {pcell} -> {out_gds}")
'''


_NX_LIMITS = {
    "npn13G2": (1, 10),
    "npn13G2L": (1, 4),
    "npn13G2V": (1, 8),
}


def _bjt_name(pcell: str, nx: int, le: float, we: float) -> str:
    return f"{pcell.upper()}_NX{nx}_LE{fmt_micron(le)}_WE{fmt_micron(we)}"


def _gen_bjt(
    pcell: str,
    nx: int,
    le: float,
    we: float,
    out_dir: str | Path,
    name: str | None = None,
) -> Path:
    nx = int(nx)
    nx_lo, nx_hi = _NX_LIMITS[pcell]
    if not (nx_lo <= nx <= nx_hi):
        raise ValueError(f"{pcell} Nx must be in [{nx_lo}, {nx_hi}], got {nx}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if name is None:
        name = _bjt_name(pcell, nx, le, we)
    out_gds = out_dir / f"{name}.gds"

    pcell_params: dict = {"Nx": nx, "le": float(le), "we": float(we)}

    script = _BJT_SCRIPT.format(
        pcell=pcell,
        pcell_params=repr(pcell_params),
        cell_name=name,
        out_gds=str(out_gds),
    )
    run_klayout_script(script, log_prefix=name)
    if not out_gds.is_file():
        raise KLayoutRunError(f"klayout completed but {out_gds} missing")
    return out_gds


def gen_npn13g2(
    nx: int, le: float, we: float, out_dir: str | Path, name: str | None = None
) -> Path:
    """npn13G2 standard NPN. Nx in [1,10], le default 0.9u, we default 0.07u."""
    return _gen_bjt("npn13G2", nx, le, we, out_dir, name=name)


def gen_npn13g2l(
    nx: int, le: float, we: float, out_dir: str | Path, name: str | None = None
) -> Path:
    """npn13G2L long-emitter variant. Nx in [1,4], le default 1.0u, we default 0.07u."""
    return _gen_bjt("npn13G2L", nx, le, we, out_dir, name=name)


def gen_npn13g2v(
    nx: int, le: float, we: float, out_dir: str | Path, name: str | None = None
) -> Path:
    """npn13G2V high-voltage variant. Nx in [1,8], le default 1.0u, we default 0.12u."""
    return _gen_bjt("npn13G2V", nx, le, we, out_dir, name=name)
