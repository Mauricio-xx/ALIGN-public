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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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


# Series-stack merge — mirrors align/compiler/preprocess.py:add_series_devices.
# When the user-facing SPICE contains a {D,S}-coupled pair of same-model
# same-gate same-body same-params devices over a 2-neighbor internal net,
# ALIGN's preprocess collapses them into one device with STACK=N+M and the
# PDK primitive renders the stacked form. KLayout LVS folds the rendered
# series fingers back into one device on extraction, so the .lvs.sp that
# feeds run_lvs.py must also drop the merged partner -- otherwise device
# counts diverge. This block reproduces the same merge purely on the
# host SPICE token stream (no align/networkx dependency).

_MOS_PIN_INDEX = {"D": 0, "G": 1, "S": 2, "B": 3}
_MOS_PIN_NAMES = ("D", "G", "S", "B")


@dataclass
class _Device:
    line_no: int          # index into the input lines list
    name: str             # 'm20'
    nodes: list           # [D, G, S, B]
    model: str            # lowercased on use
    params: dict          # lowercased keys


@dataclass
class _Subckt:
    header_line_no: int
    name: str
    ports: list
    devices: list = field(default_factory=list)
    ends_line_no: Optional[int] = None


def _parse_mos_line(line: str, line_no: int) -> Optional[_Device]:
    """Return a _Device for SPICE MOS lines (M<id> D G S B model ...); else None."""
    tokens = line.split()
    if len(tokens) < 6:
        return None
    head = tokens[0]
    if not head.lower().startswith("m"):
        return None
    if head.startswith("."):
        return None
    return _Device(
        line_no=line_no,
        name=head,
        nodes=tokens[1:5],
        model=tokens[5],
        params=parse_kv_params(tokens[6:]),
    )


def _parse_subckts(lines: list) -> list:
    """Parse the deck into _Subckt entries. Lines outside .subckt blocks are
    ignored for merge purposes (top-level MOS without a subckt is rare in
    ALIGN user input and not the target of series-stack merging here)."""
    subckt_re = re.compile(r"^\s*\.subckt\s+(\S+)\s+(.*)$", re.IGNORECASE)
    ends_re = re.compile(r"^\s*\.ends\b", re.IGNORECASE)
    subckts: list = []
    current: Optional[_Subckt] = None
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        m = subckt_re.match(line)
        if m:
            current = _Subckt(
                header_line_no=i,
                name=m.group(1),
                ports=m.group(2).split(),
            )
            subckts.append(current)
            continue
        if ends_re.match(line):
            if current is not None:
                current.ends_line_no = i
            current = None
            continue
        if current is None:
            continue
        dev = _parse_mos_line(line, i)
        if dev is not None:
            current.devices.append(dev)
    return subckts


def merge_series_stacks(subckt: _Subckt):
    """Apply ALIGN's add_series_devices semantics on a parsed subckt.

    Iterates to fixed point: each pass scans every internal net, and the first
    qualifying merge collapses the higher-named partner into the lower-named
    one (matching ALIGN's sorted-neighbours behaviour). On merge, the kept
    device's pin that touches the internal net is replaced with the dropped
    device's value at the SAME pin name -- since the two devices touch the
    net via OPPOSITE channel pins (one D, one S), that effectively pulls in
    the dropped device's other-side net.

    Returns (dropped_line_nos: set[int], overrides: dict[int -> list[str]]).
    Only line numbers of MOS lines that were dropped or mutated appear in
    the return value.
    """
    port_set = {p.lower() for p in subckt.ports}
    devices_by_line = {dev.line_no: dev for dev in subckt.devices}
    original_nodes = {dev.line_no: list(dev.nodes) for dev in subckt.devices}
    current_nodes = {ln: list(nodes) for ln, nodes in original_nodes.items()}
    alive = set(devices_by_line)

    changed = True
    while changed:
        changed = False
        # net (lowercase) -> {device_line: set(pin_name)}
        adjacency: dict = {}
        for line_no in alive:
            for pin_name, net in zip(_MOS_PIN_NAMES, current_nodes[line_no]):
                adjacency.setdefault(net.lower(), {}).setdefault(line_no, set()).add(pin_name)

        for net, dev_pins in adjacency.items():
            if net in port_set:
                continue
            if len(dev_pins) != 2:
                continue
            items = list(dev_pins.items())
            lineA, pinsA = items[0]
            lineB, pinsB = items[1]
            if len(pinsA) != 1 or len(pinsB) != 1:
                continue
            pinA = next(iter(pinsA))
            pinB = next(iter(pinsB))
            if {pinA, pinB} != {"D", "S"}:
                continue
            devA = devices_by_line[lineA]
            devB = devices_by_line[lineB]
            if devA.model.lower() != devB.model.lower():
                continue
            if current_nodes[lineA][_MOS_PIN_INDEX["G"]] != current_nodes[lineB][_MOS_PIN_INDEX["G"]]:
                continue
            if current_nodes[lineA][_MOS_PIN_INDEX["B"]] != current_nodes[lineB][_MOS_PIN_INDEX["B"]]:
                continue
            paramsA = {k: v for k, v in devA.params.items() if k != "stack"}
            paramsB = {k: v for k, v in devB.params.items() if k != "stack"}
            if paramsA != paramsB:
                continue
            if devA.name.lower() < devB.name.lower():
                keep_line, drop_line, keep_pin = lineA, lineB, pinA
            else:
                keep_line, drop_line, keep_pin = lineB, lineA, pinB
            keep_idx = _MOS_PIN_INDEX[keep_pin]
            current_nodes[keep_line][keep_idx] = current_nodes[drop_line][keep_idx]
            alive.discard(drop_line)
            changed = True
            break

    dropped_lines = set(devices_by_line) - alive
    overrides = {
        ln: current_nodes[ln]
        for ln in alive
        if current_nodes[ln] != original_nodes[ln]
    }
    return dropped_lines, overrides


def _rewrite_mos_nodes(line: str, new_nodes: list) -> str:
    """Replace tokens 1..4 of a MOS line with the supplied nodes."""
    tokens = line.split()
    if len(tokens) < 6:
        return line
    if not tokens[0].lower().startswith("m"):
        return line
    tokens[1:5] = list(new_nodes)
    return " ".join(tokens)


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
    lines = text.splitlines()

    # Pre-pass: parse subckts and compute series-stack merges per subckt.
    subckts = _parse_subckts(lines)
    dropped_lines: set = set()
    line_overrides: dict = {}
    for sub in subckts:
        d, o = merge_series_stacks(sub)
        dropped_lines |= d
        line_overrides.update(o)

    out_lines = []
    rename_map: dict[str, str] = {}

    for i, raw in enumerate(lines):
        if i in dropped_lines:
            continue
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

        if i in line_overrides:
            line = _rewrite_mos_nodes(line, line_overrides[i])

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
