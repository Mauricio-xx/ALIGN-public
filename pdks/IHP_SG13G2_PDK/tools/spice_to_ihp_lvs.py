#!/usr/bin/env python3
"""
Translate an ALIGN user-facing SPICE netlist into IHP-LVS-ready form.

The user-facing SPICE in examples/ uses ALIGN-side model aliases
(nmos_rvt / pmos_rvt / nfet / pfet / nmosHV / pmosHV) declared in
pdks/IHP_SG13G2_PDK/models.sp, with per-finger geometry (w + nf + m).
IHP's LVS deck (run_lvs.py) expects:
  - foundry model names (sg13_lv_nmos / sg13_lv_pmos / sg13_hv_nmos /
    sg13_hv_pmos)
  - device width that matches the extracted layout (KLayout folds parallel
    fingers into a single device of W = w_finger * nf * m).
  - subckt name matching the GDS top cell (ALIGN appends _<N>, default _0).

Transformations applied per line:
  - .subckt NAME ...    -> .SUBCKT NAME.upper() + suffix ...
  - .ends NAME          -> .ENDS NAME.upper() + suffix
  - M<id> <4 nodes> <model> <params...>
      model: aliased via MODEL_MAP (unknown models pass through unchanged).
      params: keep L (formatted in microns); set W = w * nf * m; drop the
              rest (nf, m, stack, parallel) so the extracted netlist's
              folded-finger form matches.
  - everything else (comments, blank lines, .model, .include) is preserved.

Limitations:
  - Single-subckt input. Nested subckts work but every .subckt header gets
    the same suffix treatment; the user controls the top-cell name via
    --topcell (overrides the default uppercase+suffix rule for the matching
    subckt only, others still get the default rule).
  - Only MOS device lines are translated; resistors/caps/BJTs/inductors
    pass through verbatim.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ALIGN-side alias -> IHP foundry model. Keep keys lowercase.
MODEL_MAP = {
    "nmos_rvt":  "sg13_lv_nmos",
    "pmos_rvt":  "sg13_lv_pmos",
    "nfet":      "sg13_lv_nmos",
    "pfet":      "sg13_lv_pmos",
    "nmoshv":    "sg13_hv_nmos",
    "pmoshv":    "sg13_hv_pmos",
    "nfet_3p3v": "sg13_hv_nmos",
    "pfet_3p3v": "sg13_hv_pmos",
}

# Aliases that, if present in the input, mark it as user-facing (vs LVS-ready).
ALIGN_ALIAS_PATTERN = re.compile(
    r"\b(nmos_rvt|pmos_rvt|nfet|pfet|nmosHV|pmosHV|nfet_3p3V|pfet_3p3V)\b",
    re.IGNORECASE,
)

SPICE_SI_SUFFIXES = {
    "t":   1e12,
    "g":   1e9,
    "meg": 1e6,
    "k":   1e3,
    "m":   1e-3,
    "u":   1e-6,
    "n":   1e-9,
    "p":   1e-12,
    "f":   1e-15,
    "a":   1e-18,
}


def looks_like_user_spice(text: str) -> bool:
    """Return True if the input contains any ALIGN-side model alias."""
    return ALIGN_ALIAS_PATTERN.search(text) is not None


def parse_spice_value(s: str) -> float:
    """Parse a SPICE numeric literal.

    Accepts plain floats ('1.3e-7'), engineering suffixes ('560n', '2.24u'),
    and trailing units past the suffix ('1.5uF' -> 1.5e-6). Case-insensitive.
    """
    s = s.strip().lower()
    if not s:
        raise ValueError("empty SPICE value")
    # Plain float first.
    try:
        return float(s)
    except ValueError:
        pass
    # Suffix match: longest first to handle 'meg' before 'm'.
    for suf in sorted(SPICE_SI_SUFFIXES, key=len, reverse=True):
        idx = s.find(suf)
        if idx <= 0:
            continue
        head = s[:idx]
        try:
            num = float(head)
        except ValueError:
            continue
        return num * SPICE_SI_SUFFIXES[suf]
    raise ValueError(f"cannot parse SPICE numeric: {s!r}")


def format_microns(value_meters: float) -> str:
    """Render a length in microns with up to 6 significant figures."""
    um = value_meters * 1e6
    s = f"{um:.6g}"
    return f"{s}u"


def parse_kv_params(tokens):
    params = {}
    for tok in tokens:
        if "=" in tok:
            k, v = tok.split("=", 1)
            params[k.lower()] = v
    return params


def translate_device_line(line: str) -> str:
    """Translate a MOS device line. Non-MOS lines are returned unchanged."""
    if not line.strip():
        return line
    tokens = line.split()
    head = tokens[0]
    if not head.lower().startswith("m"):
        return line
    # Expect: M<id> n1 n2 n3 n4 model [params...]
    if len(tokens) < 6:
        return line
    name = tokens[0]
    nodes = tokens[1:5]
    model = tokens[5]
    rest = tokens[6:]

    new_model = MODEL_MAP.get(model.lower())
    if new_model is None:
        return line  # unknown model: pass through

    params = parse_kv_params(rest)
    w_str = params.get("w")
    l_str = params.get("l")
    if w_str is None or l_str is None:
        return line  # malformed: pass through

    try:
        nf = int(float(params.get("nf", "1")))
        m_mult = int(float(params.get("m", "1")))
        w_eff = parse_spice_value(w_str) * nf * m_mult
        l_val = parse_spice_value(l_str)
    except ValueError:
        return line

    new_tokens = [
        name, *nodes, new_model,
        f"L={format_microns(l_val)}",
        f"W={format_microns(w_eff)}",
    ]
    return " ".join(new_tokens)


def _apply_topcell(name: str, suffix: str, topcell: str | None) -> str:
    """Return the renamed subckt identifier."""
    default = name.upper() + suffix
    if topcell and name.upper() + suffix == topcell.upper():
        # No-op: default rule already lands on requested topcell.
        return topcell
    if topcell and name.upper() == topcell.upper().removesuffix(suffix):
        return topcell
    if topcell and name.upper() == topcell.upper():
        # User passed a topcell that omits the suffix; honour as-is.
        return topcell
    return default


def translate(text: str, suffix: str = "_0", topcell: str | None = None) -> str:
    """Translate a full SPICE deck. Returns the translated text."""
    subckt_re = re.compile(r"^\s*\.subckt\s+(\S+)\s+(.*)$", re.IGNORECASE)
    ends_re = re.compile(r"^\s*\.ends(?:\s+(\S+))?\s*$", re.IGNORECASE)
    out_lines = []
    rename_map: dict[str, str] = {}

    for raw in text.splitlines():
        line = raw.rstrip()

        m = subckt_re.match(line)
        if m:
            orig = m.group(1)
            ports = m.group(2)
            new_name = _apply_topcell(orig, suffix, topcell)
            rename_map[orig.upper()] = new_name
            out_lines.append(f".SUBCKT {new_name} {ports}")
            continue

        m = ends_re.match(line)
        if m:
            tag = m.group(1)
            if tag is None:
                out_lines.append(".ENDS")
            else:
                new_name = rename_map.get(tag.upper(), tag.upper() + suffix)
                out_lines.append(f".ENDS {new_name}")
            continue

        out_lines.append(translate_device_line(line))

    return "\n".join(out_lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Translate ALIGN user SPICE to IHP-LVS-ready SPICE.",
    )
    ap.add_argument("input", help="path to the user-facing SPICE netlist")
    ap.add_argument(
        "-o", "--output",
        help="output path; if omitted, writes to stdout",
    )
    ap.add_argument(
        "--suffix", default="_0",
        help="ALIGN top-cell suffix (default: _0)",
    )
    ap.add_argument(
        "--topcell", default=None,
        help="explicit top-cell name to use for the matching subckt",
    )
    args = ap.parse_args(argv)

    text = Path(args.input).read_text()
    result = translate(text, suffix=args.suffix, topcell=args.topcell)

    if args.output:
        Path(args.output).write_text(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
