"""CLI for IHP SG13G2 black_box device generator.

Usage:
    python -m pdks.IHP_SG13G2_PDK.gen_blackbox \\
        --device cmim --w 10e-6 --l 10e-6 --out /tmp/sg13_bbox

    python -m pdks.IHP_SG13G2_PDK.gen_blackbox \\
        --device rppd --w 1e-6 --l 10e-6 --ps 2e-6 --b 0 --out /tmp/sg13_bbox
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .mim import gen_cmim
from .polyres import gen_rsil, gen_rppd, gen_rhigh
from .klayout_runner import klayout_available


def _parse_si(text: str) -> float:
    """Accept '10u', '1.5e-6', '10e-6'."""
    text = text.strip()
    suffix_map = {"u": 1e-6, "n": 1e-9, "p": 1e-12, "m": 1e-3}
    if text and text[-1] in suffix_map:
        return float(text[:-1]) * suffix_map[text[-1]]
    return float(text)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pdks.IHP_SG13G2_PDK.gen_blackbox")
    p.add_argument("--device", required=True, choices=["cmim", "rsil", "rppd", "rhigh"])
    p.add_argument("--w", required=True, type=_parse_si, help="device width (meters or 10u)")
    p.add_argument("--l", required=True, type=_parse_si, help="device length")
    p.add_argument("--ps", type=_parse_si, default=2e-6, help="poly space (resistors only)")
    p.add_argument("--b", type=int, default=0, help="number of bends (rppd/rhigh only)")
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--name", default=None, help="override GDS basename (default auto)")
    args = p.parse_args(argv)

    if not klayout_available():
        print("klayout not in PATH (set KLAYOUT_BIN or install klayout)", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    if args.device == "cmim":
        gds = gen_cmim(args.w, args.l, out_dir, name=args.name)
    elif args.device == "rsil":
        gds = gen_rsil(args.w, args.l, args.ps, out_dir, name=args.name)
    elif args.device == "rppd":
        gds = gen_rppd(args.w, args.l, args.ps, out_dir, b=args.b, name=args.name)
    elif args.device == "rhigh":
        gds = gen_rhigh(args.w, args.l, args.ps, out_dir, b=args.b, name=args.name)
    else:
        print(f"Unknown device {args.device}", file=sys.stderr)
        return 2

    print(f"wrote {gds}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
