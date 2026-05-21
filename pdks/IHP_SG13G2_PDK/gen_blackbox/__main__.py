"""CLI for IHP SG13G2 black_box device generator.

Usage:
    python -m pdks.IHP_SG13G2_PDK.gen_blackbox \\
        --device cmim --w 10e-6 --l 10e-6 --out /tmp/sg13_bbox

    python -m pdks.IHP_SG13G2_PDK.gen_blackbox \\
        --device rppd --w 1e-6 --l 10e-6 --ps 2e-6 --b 0 --out /tmp/sg13_bbox

    python -m pdks.IHP_SG13G2_PDK.gen_blackbox \\
        --device npn13g2 --nx 1 --le 0.9u --we 0.07u --out /tmp/sg13_bbox
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .mim import gen_cmim
from .polyres import gen_rsil, gen_rppd, gen_rhigh
from .bjt import gen_npn13g2, gen_npn13g2l, gen_npn13g2v
from .inductor import gen_inductor2, gen_inductor3, default_dmin, default_nr
from .klayout_runner import klayout_available


_PASSIVE = {"cmim", "rsil", "rppd", "rhigh"}
_BJT = {"npn13g2", "npn13g2l", "npn13g2v"}
_IND = {"inductor2", "inductor3"}


def _parse_si(text: str) -> float:
    """Accept '10u', '1.5e-6', '10e-6'."""
    text = text.strip()
    suffix_map = {"u": 1e-6, "n": 1e-9, "p": 1e-12, "m": 1e-3}
    if text and text[-1] in suffix_map:
        return float(text[:-1]) * suffix_map[text[-1]]
    return float(text)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pdks.IHP_SG13G2_PDK.gen_blackbox")
    p.add_argument(
        "--device",
        required=True,
        choices=sorted(_PASSIVE | _BJT | _IND),
    )
    p.add_argument("--w", type=_parse_si, help="device width (cmim/rsil/rppd/rhigh/inductor*)")
    p.add_argument("--l", type=_parse_si, help="device length (cmim/rsil/rppd/rhigh)")
    p.add_argument("--ps", type=_parse_si, default=2e-6, help="poly space (resistors only)")
    p.add_argument("--b", type=int, default=0, help="number of bends (rppd/rhigh only)")
    p.add_argument("--nx", type=int, help="emitter multiplier (BJT only)")
    p.add_argument("--le", type=_parse_si, help="emitter length (BJT only)")
    p.add_argument("--we", type=_parse_si, help="emitter width (BJT only)")
    p.add_argument("--s", type=_parse_si, help="spiral metal space (inductor* only)")
    p.add_argument("--d", type=_parse_si, help="spiral diameter (inductor*; default = variant DMIN)")
    p.add_argument("--nr", type=int, help="number of turns (inductor*; default = variant NR)")
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--name", default=None, help="override GDS basename (default auto)")
    args = p.parse_args(argv)

    if not klayout_available():
        print("klayout not in PATH (set KLAYOUT_BIN or install klayout)", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    if args.device in _PASSIVE:
        if args.w is None or args.l is None:
            p.error(f"--device {args.device} requires --w and --l")
        if args.device == "cmim":
            gds = gen_cmim(args.w, args.l, out_dir, name=args.name)
        elif args.device == "rsil":
            gds = gen_rsil(args.w, args.l, args.ps, out_dir, name=args.name)
        elif args.device == "rppd":
            gds = gen_rppd(args.w, args.l, args.ps, out_dir, b=args.b, name=args.name)
        elif args.device == "rhigh":
            gds = gen_rhigh(args.w, args.l, args.ps, out_dir, b=args.b, name=args.name)
    elif args.device in _BJT:
        if args.nx is None or args.le is None or args.we is None:
            p.error(f"--device {args.device} requires --nx --le --we")
        if args.device == "npn13g2":
            gds = gen_npn13g2(args.nx, args.le, args.we, out_dir, name=args.name)
        elif args.device == "npn13g2l":
            gds = gen_npn13g2l(args.nx, args.le, args.we, out_dir, name=args.name)
        elif args.device == "npn13g2v":
            gds = gen_npn13g2v(args.nx, args.le, args.we, out_dir, name=args.name)
    elif args.device in _IND:
        w = args.w if args.w is not None else 2e-6
        s = args.s if args.s is not None else 2.1e-6
        d = args.d if args.d is not None else default_dmin(args.device)
        nr = args.nr if args.nr is not None else default_nr(args.device)
        if args.device == "inductor2":
            gds = gen_inductor2(w, s, d, nr, out_dir, name=args.name)
        elif args.device == "inductor3":
            gds = gen_inductor3(w, s, d, nr, out_dir, name=args.name)
    else:
        print(f"Unknown device {args.device}", file=sys.stderr)
        return 2

    print(f"wrote {gds}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
