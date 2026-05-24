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
  - Only MOS device lines are translated; resistors/caps/BJTs/inductors
    pass through verbatim.
  - Every .subckt header gets the same suffix treatment; the user controls
    the top-cell name via --topcell (overrides the default uppercase+suffix
    rule for the matching subckt only, others still get the default rule).
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

# BJT user-facing (lowercase) -> KLayout extraction model name (case-sensitive).
BJT_MODEL_MAP = {
    "npn13g2":  "npn13G2",
    "npn13g2l": "npn13G2l",
    "npn13g2v": "npn13G2v",
    "pnpmpa":   "pnpMPA",
}

# Resistor and cap model names match extraction as-is (all lowercase).
# Listed here so translate_passive_line can recognise them as valid models
# and future name changes can be handled centrally.
RES_MODEL_MAP = {
    "rsil":  "rsil",
    "rppd":  "rppd",
    "rhigh": "rhigh",
}

CAP_MODEL_MAP = {
    "cap_cmim": "cap_cmim",
    "rfcmim":   "rfcmim",
}

PASSIVE_MODEL_MAP = {**BJT_MODEL_MAP, **RES_MODEL_MAP, **CAP_MODEL_MAP}

# Models whose SPICE form requires a substrate/bulk terminal that the user
# SPICE typically omits.  IHP's LVS deck SPICE reader expects:
#   Q  C B E <sub>  model params   (4 nodes)
#   R  P M  <bulk>  model params   (3 nodes, poly resistors only)
MODELS_NEEDING_SUBSTRATE = set(BJT_MODEL_MAP) | set(RES_MODEL_MAP)

# IHP PyCell default BJT geometry; KLayout extraction reads these from the
# physical layout, so the schematic must specify them to avoid a 0-vs-real
# parameter mismatch.  Values from libs.tech/klayout/python/sg13g2_pycell_lib.
BJT_DEFAULT_PARAMS = {
    "npn13g2":  {"we": "70n", "le": "900n", "Nx": "1", "m": "1"},
    "npn13g2l": {"we": "70n", "le": "1000n", "Nx": "1", "m": "1"},
    "npn13g2v": {"we": "120n", "le": "1000n", "Nx": "1", "m": "1"},
    "pnpmpa":   {"m": "1"},
}

# Parameters the LVS extraction defaults to 0 because they cannot be
# inferred from geometry; the schematic must match.
RES_EXTRACTION_ZERO_PARAMS = {"ps", "b"}

# Aliases that, if present in the input, mark it as user-facing (vs LVS-ready).
# Includes MOS aliases and BJT model names that need case normalisation.
ALIGN_ALIAS_PATTERN = re.compile(
    r"\b(nmos_rvt|pmos_rvt|nfet|pfet|nmosHV|pmosHV|nfet_3p3V|pfet_3p3V"
    r"|npn13g2l?v?|pnpmpa)\b",
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


def translate_device_line(line: str, w_override_meters: Optional[float] = None) -> str:
    """Translate a MOS device line. Non-MOS lines are returned unchanged.

    If ``w_override_meters`` is supplied, it is used as the emitted W value
    instead of the per-line ``w*nf*m`` product. This is the path taken by
    parallel-merged kept devices, whose total W is the sum of the merged
    group's per-finger contributions.
    """
    if not line.strip():
        return line
    tokens = line.split()
    head = tokens[0]
    if not head.lower().startswith("m"):
        return line
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
        l_val = parse_spice_value(l_str)
        if w_override_meters is not None:
            w_eff = w_override_meters
        else:
            nf = int(float(params.get("nf", "1")))
            m_mult = int(float(params.get("m", "1")))
            w_eff = parse_spice_value(w_str) * nf * m_mult
    except ValueError:
        return line

    new_tokens = [
        name, *nodes, new_model,
        f"L={format_microns(l_val)}",
        f"W={format_microns(w_eff)}",
    ]
    return " ".join(new_tokens)


def translate_passive_line(line: str, substrate_net: str = "sub!") -> str:
    """Translate BJT / resistor / capacitor lines for LVS compatibility.

    Normalises model names to match KLayout extraction names (case-sensitive
    for BJTs: npn13g2 -> npn13G2). For models in MODELS_NEEDING_SUBSTRATE,
    inserts a substrate/bulk terminal before the model token when the user
    SPICE omits it.  IHP LVS deck requires:
      Q  C B E sub  model params   (4 nodes for BJTs)
      R  P M  bulk  model params   (3 nodes for poly resistors)
    Non-matching lines are returned unchanged.
    """
    if not line.strip():
        return line
    tokens = line.split()
    head = tokens[0].lower()
    if head.startswith(".") or head.startswith("*"):
        return line
    if not (head.startswith("q") or head.startswith("r") or head.startswith("c")):
        return line
    if len(tokens) < 3:
        return line

    param_start = len(tokens)
    for i in range(1, len(tokens)):
        if "=" in tokens[i]:
            param_start = i
            break

    model_idx = param_start - 1
    if model_idx < 2:
        return line

    model = tokens[model_idx]
    new_model = PASSIVE_MODEL_MAP.get(model.lower())
    if new_model is None:
        return line

    tokens[model_idx] = new_model

    model_lc = model.lower()
    if model_lc in MODELS_NEEDING_SUBSTRATE:
        is_bjt = head.startswith("q")
        is_res = head.startswith("r")
        expected_nodes = 4 if is_bjt else (3 if is_res else None)
        if expected_nodes is not None:
            node_count = model_idx - 1
            if node_count < expected_nodes:
                tokens.insert(model_idx, substrate_net)

    existing_params = {
        t.split("=", 1)[0].lower() for t in tokens if "=" in t
    }

    if head.startswith("q") and model_lc in BJT_DEFAULT_PARAMS:
        for k, v in BJT_DEFAULT_PARAMS[model_lc].items():
            if k.lower() not in existing_params:
                tokens.append(f"{k}={v}")

    if head.startswith("r") and model_lc in RES_MODEL_MAP:
        tokens = [
            t if "=" not in t or t.split("=", 1)[0].lower()
            not in RES_EXTRACTION_ZERO_PARAMS
            else f"{t.split('=', 1)[0]}=0"
            for t in tokens
        ]

    return " ".join(tokens)


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
    """Parse the deck into _Subckt entries, supporting nested .subckt blocks.

    Uses a stack so that devices inside an inner subckt belong to that inner
    subckt, while devices between the inner .ends and the outer .ends belong
    to the outer subckt. Lines outside any .subckt block are ignored."""
    subckt_re = re.compile(r"^\s*\.subckt\s+(\S+)\s+(.*)$", re.IGNORECASE)
    ends_re = re.compile(r"^\s*\.ends\b", re.IGNORECASE)
    subckts: list = []
    stack: list = []
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        m = subckt_re.match(line)
        if m:
            sub = _Subckt(
                header_line_no=i,
                name=m.group(1),
                ports=m.group(2).split(),
            )
            subckts.append(sub)
            stack.append(sub)
            continue
        if ends_re.match(line):
            if stack:
                stack[-1].ends_line_no = i
                stack.pop()
            continue
        if not stack:
            continue
        dev = _parse_mos_line(line, i)
        if dev is not None:
            stack[-1].devices.append(dev)
    return subckts


def merge_series_stacks(subckt: _Subckt, skip_lines: set | None = None):
    """Apply ALIGN's add_series_devices semantics on a parsed subckt.

    Iterates to fixed point: each pass scans every internal net, and the first
    qualifying merge collapses the higher-named partner into the lower-named
    one (matching ALIGN's sorted-neighbours behaviour). On merge, the kept
    device's pin that touches the internal net is replaced with the dropped
    device's value at the SAME pin name -- since the two devices touch the
    net via OPPOSITE channel pins (one D, one S), that effectively pulls in
    the dropped device's other-side net.

    ``skip_lines`` lets the caller hide devices that an earlier pipeline pass
    has already dropped (e.g. parallel-merged duplicates), so they neither
    participate in series detection nor inflate net-neighbour counts.

    Returns (dropped_line_nos: set[int], overrides: dict[int -> list[str]]).
    Only line numbers of MOS lines that were dropped or mutated appear in
    the return value.
    """
    skip_lines = skip_lines or set()
    port_set = {p.lower() for p in subckt.ports}
    devices_by_line = {
        dev.line_no: dev for dev in subckt.devices if dev.line_no not in skip_lines
    }
    original_nodes = {ln: list(dev.nodes) for ln, dev in devices_by_line.items()}
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


# Parallel-device merge -- mirrors align/compiler/preprocess.py:add_parallel_devices.
# When two or more MOS devices share the same model, the same 4-node tuple
# (D, G, S, B), and the same per-finger geometry, ALIGN's preprocess folds
# them into a single device and aggregates PARALLEL=sum across the group.
# KLayout's LVS extraction folds the laid-out parallel fingers into ONE
# device whose W is the sum of per-finger widths, so the .lvs.sp that feeds
# run_lvs.py must reflect that fold too -- otherwise device counts diverge.
# This pass reproduces ALIGN's grouping on the host SPICE token stream.


def merge_parallel_devices(subckt: _Subckt, skip_lines: set | None = None):
    """Group identical-pin MOS devices in ``subckt`` and emit fold metadata.

    Two devices group iff:
      - their lowered model name maps via ``MODEL_MAP``,
      - their 4-node tuple is identical (case-insensitive),
      - their per-finger geometry (w, l) and multipliers (nf, m) match.

    Within a group of size >= 2, the device whose name sorts lowest is kept
    and its emitted W is overridden with ``sum(w_i * nf_i * m_i)`` over the
    group, matching KLayout's parallel-finger fold. The other group members
    are returned as dropped.

    Returns:
        (dropped_lines: set[int], w_overrides: dict[int -> float meters]).
    Only kept-and-grown devices appear in ``w_overrides``; ungrouped devices
    keep the per-line ``w*nf*m`` computed by ``translate_device_line``.
    """
    skip_lines = skip_lines or set()
    groups: dict = {}
    for dev in subckt.devices:
        if dev.line_no in skip_lines:
            continue
        if dev.model.lower() not in MODEL_MAP:
            continue
        try:
            w_m = parse_spice_value(dev.params.get("w", ""))
            l_m = parse_spice_value(dev.params.get("l", ""))
            nf = int(float(dev.params.get("nf", "1")))
            m = int(float(dev.params.get("m", "1")))
        except ValueError:
            continue
        key = (
            dev.model.lower(),
            tuple(n.lower() for n in dev.nodes),
            round(w_m * 1e15),
            round(l_m * 1e15),
            nf,
            m,
        )
        groups.setdefault(key, []).append((dev, w_m, nf, m))

    dropped_lines: set = set()
    w_overrides: dict = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        sorted_group = sorted(group, key=lambda x: x[0].name.lower())
        keep_dev = sorted_group[0][0]
        w_total = sum(w_m * nf * m for _, w_m, nf, m in sorted_group)
        w_overrides[keep_dev.line_no] = w_total
        for dropped, _, _, _ in sorted_group[1:]:
            dropped_lines.add(dropped.line_no)
    return dropped_lines, w_overrides


# Dummy-device removal -- mirrors align/compiler/preprocess.py:remove_dummy_devices.
# Three patterns are dropped:
#   - PMOS whose gate is tied to a power net (always-off pull-up).
#   - NMOS whose gate is tied to a ground net (always-off pull-down).
#   - Any MOS with D == G == S (diode-shorted single-net dummy, decap-style).
# Net membership is set by the caller via ``power_nets`` / ``gnd_nets``;
# CLI defaults cover the SG13G2 examples (vdd / vss + gnd + 0).

DEFAULT_POWER_NETS = frozenset({"vdd"})
DEFAULT_GROUND_NETS = frozenset({"vss", "gnd", "0"})


def _classify_mos(model: str) -> str:
    """Return 'nmos', 'pmos', or '' if ``model`` is not a known MOS alias.

    Recognised aliases are the keys of ``MODEL_MAP`` plus their case
    variants. Models that aren't translatable (i.e. would pass through
    ``translate_device_line`` unchanged) are not classifiable -- the dummy
    pass leaves them alone.
    """
    m = model.lower()
    if m not in MODEL_MAP:
        return ""
    if "nmos" in m or m.startswith("nfet"):
        return "nmos"
    if "pmos" in m or m.startswith("pfet"):
        return "pmos"
    return ""


def remove_dummy_mos_devices(
    subckt: _Subckt,
    power_nets,
    gnd_nets,
    skip_lines: set | None = None,
    node_overrides: dict | None = None,
):
    """Return MOS line_nos that match ALIGN's dummy-device patterns.

    ``power_nets`` and ``gnd_nets`` are case-insensitive sets of net names
    that classify a gate-tied PMOS / NMOS as always-off. ``node_overrides``
    lets the caller pass post-series-merge node lists so absorbed far-side
    nets correctly classify dummies (e.g. a series-merged PMOS whose new
    gate becomes VDD).
    """
    skip_lines = skip_lines or set()
    node_overrides = node_overrides or {}
    power_lc = {p.lower() for p in power_nets} if power_nets else set()
    gnd_lc = {g.lower() for g in gnd_nets} if gnd_nets else set()

    dropped_lines: set = set()
    for dev in subckt.devices:
        if dev.line_no in skip_lines:
            continue
        kind = _classify_mos(dev.model)
        if not kind:
            continue
        nodes = node_overrides.get(dev.line_no, dev.nodes)
        d_node = nodes[_MOS_PIN_INDEX["D"]].lower()
        g_node = nodes[_MOS_PIN_INDEX["G"]].lower()
        s_node = nodes[_MOS_PIN_INDEX["S"]].lower()

        if kind == "pmos" and g_node in power_lc:
            dropped_lines.add(dev.line_no)
        elif kind == "nmos" and g_node in gnd_lc:
            dropped_lines.add(dev.line_no)
        elif d_node == g_node == s_node:
            dropped_lines.add(dev.line_no)
    return dropped_lines


def _rewrite_mos_nodes(line: str, new_nodes: list) -> str:
    """Replace tokens 1..4 of a MOS line with the supplied nodes."""
    tokens = line.split()
    if len(tokens) < 6:
        return line
    if not tokens[0].lower().startswith("m"):
        return line
    tokens[1:5] = list(new_nodes)
    return " ".join(tokens)


def _remap_passive_nets(
    tokens: list, prefix: str, port_map: dict
) -> str:
    """Remap net tokens in a Q/R/C device line during hierarchy flattening.

    Device syntax: ``<prefix><name> <net>... <model> [key=value...]``
    Nets sit between the device name and the model; the model is the last
    non-key=value token before any key=value parameters.
    """
    dev = tokens[0]
    new_dev = f"{dev[0]}{prefix}{dev[1:]}" if prefix else dev

    param_start = len(tokens)
    for i in range(1, len(tokens)):
        if "=" in tokens[i]:
            param_start = i
            break

    model_idx = param_start - 1
    if model_idx < 2:
        return " ".join(tokens)

    model = tokens[model_idx]
    nets = tokens[1:model_idx]
    params = tokens[param_start:]

    mapped = []
    for n in nets:
        up = n.upper()
        mapped.append(port_map[up] if up in port_map else
                      (f"{prefix}{n}" if prefix else n))

    return " ".join([new_dev] + mapped + [model] + params)


def _flatten_deck(lines: list) -> list:
    """Flatten a hierarchical SPICE deck by inlining subcircuit instances.

    When the input defines multiple .subckt blocks with X* instance lines
    referencing sibling subcircuits, this function recursively expands every
    instance so the output contains a single flat subcircuit.  Internal nets
    of expanded subcircuits are prefixed with the instance hierarchy path
    to keep them unique.  Port nets are substituted to match the caller's
    actual connections.

    If the deck contains only one subcircuit (already flat), returns the
    input unchanged.
    """
    subckt_re = re.compile(r"^\s*\.subckt\s+(\S+)\s+(.*)$", re.IGNORECASE)
    ends_re = re.compile(r"^\s*\.ends\b", re.IGNORECASE)

    subckts: dict = {}
    stack: list = []
    preamble: list = []

    for line in lines:
        stripped = line.rstrip()
        m = subckt_re.match(stripped)
        if m:
            stack.append([m.group(1), m.group(2).split(), []])
            continue
        if ends_re.match(stripped):
            if stack:
                entry = stack.pop()
                subckts[entry[0].upper()] = (entry[0], entry[1], entry[2])
            continue
        if stack:
            stack[-1][2].append(stripped)
        else:
            preamble.append(stripped)

    if len(subckts) <= 1:
        return lines

    referenced: set = set()
    for name_u, (_, _, sbody) in subckts.items():
        for bline in sbody:
            tokens = bline.split()
            if tokens and tokens[0].lower().startswith("x"):
                for j in range(len(tokens) - 1, 0, -1):
                    if "=" not in tokens[j]:
                        referenced.add(tokens[j].upper())
                        break

    if not referenced:
        return lines

    top_candidates = [n for n in subckts if n not in referenced]
    if not top_candidates:
        return lines
    top_name_u = top_candidates[-1]

    def _find_ref(tokens):
        for j in range(len(tokens) - 1, 0, -1):
            if "=" not in tokens[j]:
                return j
        return None

    def _expand(name_u, prefix, port_map, depth=0):
        if depth > 50:
            return []
        _, ports, sbody = subckts[name_u]
        result = []
        for bline in sbody:
            tokens = bline.split()
            if not tokens or bline.lstrip().startswith("*"):
                continue
            if tokens[0].lower().startswith("x"):
                ref_idx = _find_ref(tokens)
                if ref_idx is None:
                    result.append(bline)
                    continue
                ref_u = tokens[ref_idx].upper()
                if ref_u not in subckts:
                    result.append(bline)
                    continue
                actual_nets = tokens[1:ref_idx]
                ref_ports = subckts[ref_u][1]
                mapped = []
                for n in actual_nets:
                    up = n.upper()
                    mapped.append(port_map[up] if up in port_map else
                                  (f"{prefix}{n}" if prefix else n))
                child_map = {fp.upper(): mn for fp, mn in zip(ref_ports, mapped)}
                inst = tokens[0]
                child_prefix = f"{prefix}{inst[1:]}_" if prefix else f"{inst[1:]}_"
                result.extend(_expand(ref_u, child_prefix, child_map, depth + 1))
            elif tokens[0].lower().startswith("m"):
                dev = tokens[0]
                new_dev = f"m{prefix}{dev[1:]}" if prefix else dev
                nodes = tokens[1:5]
                mapped_nodes = []
                for n in nodes:
                    up = n.upper()
                    mapped_nodes.append(port_map[up] if up in port_map else
                                        (f"{prefix}{n}" if prefix else n))
                rest = tokens[5:]
                result.append(" ".join([new_dev] + mapped_nodes + rest))
            elif tokens[0][0].lower() in ("q", "r", "c"):
                result.append(
                    _remap_passive_nets(tokens, prefix, port_map))
            else:
                result.append(bline)
        return result

    orig_name, top_ports, _ = subckts[top_name_u]
    top_map = {p.upper(): p for p in top_ports}
    expanded = _expand(top_name_u, "", top_map)

    out: list = list(preamble)
    out.append(f".subckt {orig_name} {' '.join(top_ports)}")
    out.extend(expanded)
    out.append(f".ends {orig_name}")
    return out


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


def translate(
    text: str,
    suffix: str = "_0",
    topcell: str | None = None,
    power_nets=None,
    gnd_nets=None,
    substrate_net: str = "sub!",
) -> str:
    """Translate a full SPICE deck. Returns the translated text.

    Preprocessing pipeline mirrors ``align/compiler/preprocess.py:42-53``:
      1. ``merge_parallel_devices``  -- fold identical-pin duplicates, sum W.
      2. ``merge_series_stacks``     -- collapse D-S coupled chains, absorb
                                       the dropped partner's far-side net.
      3. ``remove_dummy_mos_devices`` -- drop gate-tied always-off MOS and
                                       D=G=S diode-shorted dummies.

    Each pass is gated on the prior pass's drop set, so already-merged
    devices neither participate in subsequent detection nor inflate net
    neighbour counts. ``power_nets`` / ``gnd_nets`` default to the SG13G2
    examples' conventions (vdd / vss + gnd + 0).
    """
    if power_nets is None:
        power_nets = DEFAULT_POWER_NETS
    if gnd_nets is None:
        gnd_nets = DEFAULT_GROUND_NETS

    subckt_re = re.compile(r"^\s*\.subckt\s+(\S+)\s+(.*)$", re.IGNORECASE)
    ends_re = re.compile(r"^\s*\.ends(?:\s+(\S+))?\s*$", re.IGNORECASE)
    lines = _flatten_deck(text.splitlines())

    # Pre-pass: parse subckts and run ALIGN's preprocess sequence per subckt.
    subckts = _parse_subckts(lines)
    dropped_lines: set = set()
    line_overrides: dict = {}
    w_overrides: dict = {}
    for sub in subckts:
        dp, wo = merge_parallel_devices(sub, skip_lines=dropped_lines)
        dropped_lines |= dp
        w_overrides.update(wo)

        ds, no = merge_series_stacks(sub, skip_lines=dropped_lines)
        dropped_lines |= ds
        line_overrides.update(no)

        dd = remove_dummy_mos_devices(
            sub, power_nets, gnd_nets,
            skip_lines=dropped_lines,
            node_overrides=line_overrides,
        )
        dropped_lines |= dd

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

        translated = translate_device_line(
            line, w_override_meters=w_overrides.get(i)
        )
        if translated is line:
            translated = translate_passive_line(line, substrate_net=substrate_net)
        out_lines.append(translated)

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
    ap.add_argument(
        "--power", default=None,
        help="comma-separated power nets for dummy-device detection "
             f"(default: {','.join(sorted(DEFAULT_POWER_NETS))})",
    )
    ap.add_argument(
        "--ground", default=None,
        help="comma-separated ground nets for dummy-device detection "
             f"(default: {','.join(sorted(DEFAULT_GROUND_NETS))})",
    )
    ap.add_argument(
        "--substrate", default="sub!",
        help="substrate/bulk net name inserted for BJTs (4th node) and "
             "poly resistors (3rd node).  Default: sub!  Use the net that "
             "the layout extraction connects substrate to (often vdd).",
    )
    args = ap.parse_args(argv)

    def _parse_nets(arg, default):
        if arg is None:
            return set(default)
        return {p.strip() for p in arg.split(",") if p.strip()}

    power_nets = _parse_nets(args.power, DEFAULT_POWER_NETS)
    gnd_nets = _parse_nets(args.ground, DEFAULT_GROUND_NETS)

    text = Path(args.input).read_text()
    result = translate(
        text, suffix=args.suffix, topcell=args.topcell,
        power_nets=power_nets, gnd_nets=gnd_nets,
        substrate_net=args.substrate,
    )

    if args.output:
        Path(args.output).write_text(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
