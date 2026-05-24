#!/usr/bin/env python3
"""Generate all blackbox GDS files needed by a mixed-signal ALIGN circuit.

Two-pass approach:
  1. Read ALIGN's topology output (__primitives_library__.json) to discover
     exact blackbox primitive names (hashes computed by the compiler).
  2. For each blackbox primitive, extract device type + parameters and invoke
     gen_blackbox to produce the GDS.

Usage (standalone):
    # First, run ALIGN compiler (it will fail at PnR if GDS files are missing,
    # but the topology output is generated):
    schematic2layout.py <design_dir> -p pdks/IHP_SG13G2_PDK -w /tmp/work
    # Then generate the missing blackbox GDS:
    python3 gen_all_blackboxes.py /tmp/work/1_topology --out /tmp/bbox
    # Re-run ALIGN with --blackbox_dir:
    schematic2layout.py <design_dir> -p pdks/IHP_SG13G2_PDK -w /tmp/work2 \\
        --blackbox_dir /tmp/bbox

Or via the combined wrapper:
    sg13g2_run.sh <design_dir>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GEN_BLACKBOX_DIR = SCRIPT_DIR.parent / "gen_blackbox"

BLACKBOX_MODELS = frozenset({
    "NPN13G2", "NPN13G2L", "NPN13G2V", "PNPMPA",
    "RSIL", "RPPD", "RHIGH",
    "CAP_CMIM", "RFCMIM",
    "INDUCTOR2", "INDUCTOR3", "INDUCTORS",
})

_BJT_DEFAULTS = {
    "NPN13G2":  {"we": 0.07e-6, "le": 0.9e-6, "nx": 1},
    "NPN13G2L": {"we": 0.07e-6, "le": 1.0e-6, "nx": 1},
    "NPN13G2V": {"we": 0.12e-6, "le": 1.0e-6, "nx": 1},
}


def _param_float(params: dict, key: str, default: float) -> float:
    val = params.get(key)
    if val is None or val == "1" or val == "0":
        return default
    return float(val)


def _gen_blackbox_args(prim_name: str, model: str, params: dict) -> list[str]:
    """Map (model, params) to gen_blackbox CLI arguments."""
    model_up = model.upper()
    args = ["--name", prim_name]

    if model_up in ("NPN13G2", "NPN13G2L", "NPN13G2V"):
        defaults = _BJT_DEFAULTS[model_up]
        nx = int(float(params.get("NX", "1")))
        we = _param_float(params, "WE", defaults["we"])
        le = _param_float(params, "LE", defaults["le"])
        args += ["--device", model_up.lower(),
                 "--nx", str(nx), "--we", str(we), "--le", str(le)]

    elif model_up in ("RSIL", "RPPD", "RHIGH"):
        w = _param_float(params, "W", 1e-6)
        l = _param_float(params, "L", 10e-6)
        ps = _param_float(params, "PS", 2e-6)
        args += ["--device", model_up.lower(),
                 "--w", str(w), "--l", str(l), "--ps", str(ps)]
        if model_up in ("RPPD", "RHIGH"):
            b = int(float(params.get("B", "0")))
            args += ["--b", str(b)]

    elif model_up in ("CAP_CMIM", "RFCMIM"):
        w = _param_float(params, "W", 10e-6)
        l = _param_float(params, "L", 10e-6)
        args += ["--device", "cmim", "--w", str(w), "--l", str(l)]

    elif model_up in ("INDUCTOR2", "INDUCTOR3", "INDUCTORS"):
        w = _param_float(params, "W", 2e-6)
        s = _param_float(params, "S", 2.1e-6)
        args += ["--device", model_up.lower(), "--w", str(w), "--s", str(s)]
        nr = int(float(params.get("NR", "1")))
        if nr > 1:
            args += ["--nr", str(nr)]
    else:
        return []

    return args


def discover(topology_dir: str | Path) -> dict[str, tuple[str, dict, list[str]]]:
    """Parse __primitives_library__.json and return blackbox primitives.

    Returns: {prim_name: (model, element_params, gen_blackbox_args)}
    """
    plib_path = Path(topology_dir) / "__primitives_library__.json"
    if not plib_path.exists():
        print(f"ERROR: {plib_path} not found", file=sys.stderr)
        return {}

    with open(plib_path) as f:
        plib = json.load(f)

    result = {}
    for entry in plib:
        name = entry.get("name", "")
        elements = entry.get("elements", [])
        if not elements:
            continue
        model = elements[0].get("model", "").upper()
        if model not in BLACKBOX_MODELS:
            continue
        params = elements[0].get("parameters", {})
        bb_args = _gen_blackbox_args(name, model, params)
        if not bb_args:
            print(f"  skip {name}: no gen_blackbox support for {model}", file=sys.stderr)
            continue
        result[name] = (model, params, bb_args)

    return result


def generate(topology_dir: str | Path, out_dir: str | Path,
             dry_run: bool = False) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prims = discover(topology_dir)
    if not prims:
        print("No blackbox devices found in topology output.", file=sys.stderr)
        return []

    gen_bb = [sys.executable, "-m", "gen_blackbox"]
    generated = []

    for prim_name, (model, params, bb_args) in sorted(prims.items()):
        gds_path = out_dir / f"{prim_name}.gds"
        if gds_path.exists():
            print(f"  exists: {gds_path}")
            generated.append(gds_path)
            continue

        cmd = gen_bb + bb_args + ["--out", str(out_dir)]
        print(f"  gen: {prim_name}  ({model})")
        if dry_run:
            print(f"       cmd: {' '.join(cmd)}")
            continue

        result = subprocess.run(
            cmd, cwd=str(GEN_BLACKBOX_DIR.parent),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  FAILED: {prim_name}", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            continue

        if gds_path.exists():
            generated.append(gds_path)
            print(f"       -> {gds_path}")
        else:
            print(f"  WARNING: {gds_path} not created", file=sys.stderr)

    return generated


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="gen_all_blackboxes",
        description="Auto-generate blackbox GDS from ALIGN topology output.",
    )
    p.add_argument("topology_dir",
                   help="path to ALIGN's 1_topology/ directory "
                        "(contains __primitives_library__.json)")
    p.add_argument("--out", required=True,
                   help="output directory for GDS files")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would be generated without running gen_blackbox")
    args = p.parse_args(argv)
    generated = generate(args.topology_dir, args.out, dry_run=args.dry_run)
    if generated:
        print(f"\n{len(generated)} blackbox GDS file(s) ready in {args.out}")
        print(f"Pass --blackbox_dir {args.out} to schematic2layout")
    return 0 if generated or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
