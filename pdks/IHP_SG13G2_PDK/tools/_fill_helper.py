"""KLayout batch-mode helper for ALIGN density fill.

Step 1 (inject_edgeseal): Add EdgeSeal ring (39/0) around top-cell bbox.
Step 2 (strip_edgeseal): Remove EdgeSeal from final output.

Called by sg13g2_fill.sh -- not intended for standalone use.
Invoked with: klayout -b -r _fill_helper.py -rd action=inject|strip ...
"""
import os
import sys
import pya

action = globals().get('action', 'inject')
input_file = globals().get('input_file')
output_file = globals().get('output_file')

if not input_file or not output_file:
    print("ERROR: missing -rd input_file=... and/or -rd output_file=...")
    sys.exit(1)

layout = pya.Layout()
layout.read(input_file)

topcell_name = globals().get('topcell', None)
if topcell_name:
    top = layout.cell(topcell_name)
    if top is None:
        print(f"ERROR: topcell '{topcell_name}' not found")
        sys.exit(1)
else:
    top_cells = [c for c in layout.top_cells()]
    if not top_cells:
        print("ERROR: no cells in layout")
        sys.exit(1)
    top = max(top_cells, key=lambda c: c.bbox().area())

dbu = layout.dbu
es_layer = layout.layer(39, 0)

if action == 'inject':
    margin_um = float(globals().get('margin', '5.0'))
    margin_dbu = int(round(margin_um / dbu))
    ring_w_dbu = int(round(1.0 / dbu))
    bbox = top.bbox()
    outer = pya.Box(
        bbox.left - margin_dbu - ring_w_dbu,
        bbox.bottom - margin_dbu - ring_w_dbu,
        bbox.right + margin_dbu + ring_w_dbu,
        bbox.top + margin_dbu + ring_w_dbu,
    )
    inner = pya.Box(
        bbox.left - margin_dbu,
        bbox.bottom - margin_dbu,
        bbox.right + margin_dbu,
        bbox.top + margin_dbu,
    )
    ring = pya.Region(outer) - pya.Region(inner)
    for poly in ring.each():
        top.shapes(es_layer).insert(poly)
    w = inner.width() * dbu
    h = inner.height() * dbu
    print(f"EdgeSeal ring injected: fill area {w:.1f} x {h:.1f} um ({margin_um} um margin)")
    layout.write(output_file)

elif action == 'strip':
    top.shapes(es_layer).clear()
    print("EdgeSeal stripped from output")
    layout.write(output_file)

else:
    print(f"ERROR: unknown action '{action}'")
    sys.exit(1)
