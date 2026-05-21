"""IHP SG13G2 black_box device generator.

Invokes IHP PyCells (cni.dlo) via klayout -b -r to produce GDS files
that ALIGN consumes through its --blackbox_dir mechanism. Used for
devices whose geometry is too complex to re-derive in Python:
cmim/rfcmim (MIM caps), rsil/rppd/rhigh (poly resistors), npn13G2*
(BJT), inductors.

CLI:
    python -m pdks.IHP_SG13G2_PDK.gen_blackbox \\
        --device cmim --w 10e-6 --l 10e-6 --out /tmp/sg13_bbox

Env:
    IHP_PDK_ROOT (required) -- path to IHP-Open-PDK checkout root.
    KLAYOUT_BIN  (optional) -- klayout executable, defaults to 'klayout'.
"""
from .klayout_runner import run_klayout_script, KLayoutRunError  # noqa: F401
from .mim import gen_cmim  # noqa: F401
from .polyres import gen_rsil, gen_rppd, gen_rhigh  # noqa: F401
from .bjt import gen_npn13g2, gen_npn13g2l, gen_npn13g2v  # noqa: F401
from .inductor import gen_inductor2, gen_inductor3, default_dmin, default_nr  # noqa: F401
