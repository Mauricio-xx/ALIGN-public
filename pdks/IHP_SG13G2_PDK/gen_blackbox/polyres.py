"""Poly resistor generator using IHP rsil/rppd/rhigh PyCells.

The PyCells inherit from ResistorBase and emit two Metal1 contact pads
(one at the bottom, one at the top of the body). PLUS is the bottom
contact (negative y), MINUS is the top (positive y, beyond l). The
body itself draws on PolyRes/GatPoly/RES, which the GDS includes but
which are not pins.

Label/pin injection strategy:
    PLUS  -> Metal1.Label at center of min-y Metal1 box
    MINUS -> Metal1.Label at center of max-y Metal1 box

The Metal1 box is also re-emitted on Metal1.Pin (datatype 2).
"""

from __future__ import annotations

from pathlib import Path

from .klayout_runner import KLayoutRunError, fmt_micron, run_klayout_script


_POLYRES_SCRIPT = '''
import pya

layout = pya.Layout()
layout.technology_name = "sg13g2"

params = {pcell_params}
pcell = layout.create_cell("{pcell}", "SG13_dev", params)
if pcell is None:
    raise SystemExit("{pcell} PyCell instantiation returned None")

top = layout.create_cell("{cell_name}")
top.insert(pya.DCellInstArray(pcell, pya.DTrans()))

# Identify PLUS/MINUS pin boxes by extreme-y Metal1 rects
M1_DRAW = (8, 0)
LABEL_DT = 25
PIN_DT = 2

pcell_actual = layout.cell(top.each_inst().__next__().cell_index)
m1_draw_li = layout.find_layer(*M1_DRAW)
if m1_draw_li is None:
    raise SystemExit("no Metal1.drawing shapes in {pcell} -- cannot extract pins")

boxes = [sh.bbox() for sh in pcell_actual.shapes(m1_draw_li).each() if sh.is_box() or sh.is_polygon() or sh.is_path()]
# Discard zero-area artifacts
boxes = [b for b in boxes if b.width() > 0 and b.height() > 0]
if len(boxes) < 2:
    raise SystemExit(f"expected >=2 Metal1 boxes for {pcell}, got {{len(boxes)}}")

# PLUS = min-y bbox, MINUS = max-y bbox
boxes.sort(key=lambda b: b.center().y)
plus_box = boxes[0]
minus_box = boxes[-1]

m1_label_li = layout.layer(M1_DRAW[0], LABEL_DT)
m1_pin_li   = layout.layer(M1_DRAW[0], PIN_DT)
top.shapes(m1_label_li).insert(pya.Text("PLUS", pya.Trans(plus_box.center().x, plus_box.center().y)))
top.shapes(m1_label_li).insert(pya.Text("MINUS", pya.Trans(minus_box.center().x, minus_box.center().y)))
top.shapes(m1_pin_li).insert(plus_box)
top.shapes(m1_pin_li).insert(minus_box)

opts = pya.SaveLayoutOptions()
opts.write_context_info = False
layout.write("{out_gds}", opts)
print("OK {pcell} -> {out_gds}")
'''


def _polyres_name(pcell: str, w: float, l: float, b: int, ps: float) -> str:
    parts = [pcell.upper(), f"W{fmt_micron(w)}", f"L{fmt_micron(l)}"]
    if b > 0:
        parts.append(f"B{b}")
    parts.append(f"PS{fmt_micron(ps)}")
    return "_".join(parts)


def _gen_polyres(
    pcell: str,
    w: float,
    l: float,
    ps: float,
    out_dir: str | Path,
    b: int = 0,
    name: str | None = None,
    extra_params: dict | None = None,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if name is None:
        name = _polyres_name(pcell, w, l, b, ps)
    out_gds = out_dir / f"{name}.gds"

    pcell_params: dict = {"w": float(w), "l": float(l), "ps": float(ps)}
    if pcell in {"rppd", "rhigh"}:
        pcell_params["b"] = str(int(b))
    if extra_params:
        pcell_params.update(extra_params)

    script = _POLYRES_SCRIPT.format(
        pcell=pcell,
        pcell_params=repr(pcell_params),
        cell_name=name,
        out_gds=str(out_gds),
    )
    run_klayout_script(script, log_prefix=name)
    if not out_gds.is_file():
        raise KLayoutRunError(f"klayout completed but {out_gds} missing")
    return out_gds


def gen_rsil(
    w: float, l: float, ps: float, out_dir: str | Path, name: str | None = None
) -> Path:
    """rsil silicide poly resistor. rsil has no bends parameter."""
    return _gen_polyres("rsil", w, l, ps, out_dir, b=0, name=name)


def gen_rppd(
    w: float,
    l: float,
    ps: float,
    out_dir: str | Path,
    b: int = 0,
    name: str | None = None,
) -> Path:
    return _gen_polyres("rppd", w, l, ps, out_dir, b=b, name=name)


def gen_rhigh(
    w: float,
    l: float,
    ps: float,
    out_dir: str | Path,
    b: int = 0,
    name: str | None = None,
) -> Path:
    return _gen_polyres("rhigh", w, l, ps, out_dir, b=b, name=name)
