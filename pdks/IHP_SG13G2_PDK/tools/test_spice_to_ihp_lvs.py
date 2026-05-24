"""
Tests for spice_to_ihp_lvs.

Runnable both as a plain script and under pytest. Designed to avoid pulling
in `align` (host C++ .so is not present), so it can be exercised without
Docker. Pytest collection inside pdks/IHP_SG13G2_PDK/ triggers the parent
package __init__ which imports align; therefore prefer:

    python3 pdks/IHP_SG13G2_PDK/tools/test_spice_to_ihp_lvs.py

Returns non-zero on any failed assertion.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

sys.path.insert(0, str(HERE))

from spice_to_ihp_lvs import (
    DEFAULT_GROUND_NETS,
    DEFAULT_POWER_NETS,
    _flatten_deck,
    _parse_subckts,
    looks_like_user_spice,
    merge_parallel_devices,
    merge_series_stacks,
    parse_spice_value,
    remove_dummy_mos_devices,
    translate,
    translate_device_line,
    translate_passive_line,
)

OTA_USER_SP = REPO / "examples/telescopic_ota_sg13g2/telescopic_ota_sg13g2.sp"
OTA_LVS_SP = REPO / "examples/telescopic_ota_sg13g2/lvs/telescopic_ota_sg13g2.lvs.sp"
CMC_OTA_USER_SP = REPO / "examples/current_mirror_ota_sg13g2/current_mirror_ota_sg13g2.sp"


def _approx(a: float, b: float, rel: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=0.0)


def normalize(text: str) -> list[str]:
    """Canonicalise a SPICE deck for golden comparison.

    Strips blank/comment-only lines, lowercases SPICE directive keywords,
    collapses whitespace. Preserves token order and value content so
    semantic equivalence can be checked while ignoring layout-only
    differences.
    """
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("*"):
            continue
        line = re.sub(r"\s+", " ", line)
        m = re.match(r"^(\.subckt|\.ends|\.model|\.include)\s*(.*)$",
                     line, re.IGNORECASE)
        if m:
            kw = m.group(1).lower()
            rest = m.group(2)
            out.append(f"{kw} {rest}" if rest else kw)
            continue
        out.append(line)
    return out


def test_parse_spice_value_plain_float():
    assert _approx(parse_spice_value("1.3e-7"), 1.3e-7)


def test_parse_spice_value_eng_suffix_n():
    assert _approx(parse_spice_value("560n"), 560e-9)


def test_parse_spice_value_eng_suffix_u():
    assert _approx(parse_spice_value("2.24u"), 2.24e-6)


def test_parse_spice_value_meg_before_m():
    assert _approx(parse_spice_value("1.5meg"), 1.5e6)


def test_looks_like_user_spice_true():
    assert looks_like_user_spice(OTA_USER_SP.read_text()) is True


def test_looks_like_user_spice_false():
    assert looks_like_user_spice(OTA_LVS_SP.read_text()) is False


def test_device_line_nmos_rvt_to_sg13_lv_nmos():
    line = "m1 id id 0 0 nmos_rvt w=560e-9 l=130e-9 nf=4 m=1"
    out = translate_device_line(line)
    tokens = out.split()
    assert tokens[0] == "m1"
    assert tokens[5] == "sg13_lv_nmos"
    assert "W=2.24u" in out
    assert "L=0.13u" in out
    assert "nf=" not in out.lower()
    # 'm' must not survive as a param key; the device prefix 'm1' is fine.
    assert " m=" not in out


def test_device_line_pmos_rvt_to_sg13_lv_pmos():
    line = "m8 voutp vbiasp1 net012 vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1"
    out = translate_device_line(line)
    assert "sg13_lv_pmos" in out
    assert "W=2.24u" in out


def test_device_line_hv_aliases():
    nline = "mN n1 n2 n3 n4 nmosHV w=1u l=500e-9 nf=2 m=1"
    pline = "mP n1 n2 n3 n4 pmosHV w=1u l=500e-9 nf=2 m=1"
    assert "sg13_hv_nmos" in translate_device_line(nline)
    assert "sg13_hv_pmos" in translate_device_line(pline)


def test_device_line_unknown_model_passes_through():
    line = "m1 a b c d some_other_model w=1u l=130n"
    assert translate_device_line(line) == line


def test_translate_full_subckt_rename():
    text = OTA_USER_SP.read_text()
    result = translate(text, suffix="_0")
    assert ".SUBCKT TELESCOPIC_OTA_SG13G2_0 " in result
    assert ".ENDS TELESCOPIC_OTA_SG13G2_0" in result


def test_translate_explicit_topcell_override():
    text = OTA_USER_SP.read_text()
    result = translate(text, suffix="_0", topcell="TELESCOPIC_OTA_SG13G2_0")
    assert ".SUBCKT TELESCOPIC_OTA_SG13G2_0 " in result


def test_golden_text_matches_handwritten_reference():
    """Translator output must be semantically identical to the hand-authored
    telescopic_ota_sg13g2.lvs.sp reference."""
    text = OTA_USER_SP.read_text()
    produced = translate(text, suffix="_0",
                         topcell="TELESCOPIC_OTA_SG13G2_0")
    expected = OTA_LVS_SP.read_text()

    norm_produced = normalize(produced)
    norm_expected = normalize(expected)

    if norm_produced != norm_expected:
        raise AssertionError(
            "translator output diverges from telescopic_ota_sg13g2.lvs.sp.\n"
            f"produced:\n{chr(10).join(norm_produced)}\n"
            f"expected:\n{chr(10).join(norm_expected)}\n"
        )


def test_translate_preserves_comments():
    text = "* a comment\n.subckt FOO a b\nm1 a b 0 0 nmos_rvt w=100n l=130n\n.ends FOO\n"
    result = translate(text, suffix="_0")
    assert "* a comment" in result


def _mos_lines(text):
    return [
        l for l in text.splitlines()
        if l.split() and l.split()[0].lower().startswith("m")
        and not l.split()[0].startswith(".")
    ]


def test_series_stack_basic_ds_merge():
    """Two same-model same-gate same-body same-param devices sharing an
    internal D-S net must collapse into a single device that absorbs the
    dropped partner's far-side net."""
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g stk b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 stk g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    lines = _mos_lines(result)
    assert len(lines) == 1, f"expected 1 MOS line after merge, got {len(lines)}: {lines}"
    # Kept device should be m1 with S absorbed from m2 -> 's'.
    toks = lines[0].split()
    assert toks[0].lower() == "m1"
    assert [t.lower() for t in toks[1:5]] == ["d", "g", "s", "b"]
    assert toks[5].lower() == "sg13_lv_nmos"


def test_series_stack_keeps_lower_name_drops_higher():
    """Higher-named partner is dropped; lower-named is kept (matches ALIGN's
    sorted-neighbours selection)."""
    text = (
        ".subckt FOO d g s b\n"
        "mZZ stk g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "mAA d g stk b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    lines = _mos_lines(result)
    assert len(lines) == 1
    assert lines[0].split()[0].lower() == "maa"


def test_series_stack_skip_different_gates():
    text = (
        ".subckt FOO d g1 g2 s b\n"
        "m1 d g1 stk b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 stk g2 s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 2


def test_series_stack_skip_different_bodies():
    text = (
        ".subckt FOO d g s b1 b2\n"
        "m1 d g stk b1 nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 stk g s b2 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 2


def test_series_stack_skip_different_models():
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g stk b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 stk g s b pmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 2


def test_series_stack_skip_different_params():
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g stk b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 stk g s b nmos_rvt w=100n l=200n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 2


def test_series_stack_skip_port_net():
    """Internal stack node promoted to a port must NOT trigger merge."""
    text = (
        ".subckt FOO d g s b stk\n"
        "m1 d g stk b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 stk g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 2


def test_series_stack_skip_three_neighbors():
    """Net with 3+ truly-distinct devices is not a series stack.

    The 3 neighbours use distinct gates so the parallel pass does not fold
    any of them; this isolates the series pass's 3-neighbour skip.
    """
    text = (
        ".subckt FOO d g1 g2 g3 s b\n"
        "m1 d g1 mid b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 mid g2 s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m3 mid g3 s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 3


def test_parallel_dd_coupling_merges_to_one():
    """Two devices sharing ALL four nodes (D-D, G-G, S-S, B-B) and identical
    geometry are a true parallel arrangement; the parallel pass folds them
    into a single device whose W absorbs both contributions."""
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    lines = _mos_lines(result)
    assert len(lines) == 1, f"expected 1 MOS line after parallel merge, got {len(lines)}: {lines}"
    toks = lines[0].split()
    assert toks[0].lower() == "m1"  # lower name kept
    # W must be 200n (= 100n + 100n) regardless of suffix style.
    assert "W=0.2u" in result


def test_series_stack_three_in_series_collapse_to_one():
    """Chain of 3 stacked devices must collapse to 1 via fixed-point iteration."""
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g s1 b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 s1 g s2 b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m3 s2 g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    lines = _mos_lines(result)
    assert len(lines) == 1
    toks = lines[0].split()
    assert toks[0].lower() == "m1"
    assert [t.lower() for t in toks[1:5]] == ["d", "g", "s", "b"]


def test_cmc_ota_collapses_to_10_mos():
    """The Phase N target: 12-MOS current_mirror_ota_sg13g2.sp (with m20/m20s
    and m18/m18s cascode stacks) must translate to a 10-MOS .lvs.sp -- matching
    the 10-MOS layout extracted by KLayout."""
    text = CMC_OTA_USER_SP.read_text()
    result = translate(text, suffix="_0", topcell="CURRENT_MIRROR_OTA_SG13G2_0")
    lines = _mos_lines(result)
    assert len(lines) == 10, f"expected 10 MOS lines after merge, got {len(lines)}"

    by_name = {l.split()[0].lower(): l for l in lines}
    # m20s and m18s must be dropped.
    assert "m20s" not in by_name
    assert "m18s" not in by_name
    # m20 must absorb m20s's D -> vbiasnd.
    m20 = by_name["m20"].split()
    assert [t.lower() for t in m20[1:5]] == ["vbiasnd", "net16", "vdd", "vdd"]
    # m18 must absorb m18s's D -> voutp.
    m18 = by_name["m18"].split()
    assert [t.lower() for t in m18[1:5]] == ["voutp", "net27", "vdd", "vdd"]
    # The internal stack nets must not appear on any MOS device line; they
    # are absorbed by the merge. (They may still appear in pass-through
    # comments, which are not in `lines`.)
    for ml in lines:
        toks = [t.lower() for t in ml.split()[1:5]]
        assert "m20stack" not in toks
        assert "m18stack" not in toks


def test_telescopic_ota_no_merges():
    """Telescopic OTA cascodes share an internal D-S net but have DIFFERENT
    gates -- must NOT be merged. The existing golden test depends on this."""
    text = OTA_USER_SP.read_text()
    subckts = _parse_subckts(text.splitlines())
    assert len(subckts) == 1
    dropped, overrides = merge_series_stacks(subckts[0])
    assert dropped == set()
    assert overrides == {}


# -- Parallel merge --------------------------------------------------------

def test_parallel_three_devices_sum_w():
    """Three identical-pin identical-param devices collapse to one with
    W=3*W_each."""
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m3 d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    lines = _mos_lines(result)
    assert len(lines) == 1
    assert lines[0].split()[0].lower() == "m1"
    assert "W=0.3u" in result


def test_parallel_lower_name_kept():
    """Among parallel duplicates, the device with the lowest name is kept."""
    text = (
        ".subckt FOO d g s b\n"
        "mZZ d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "mAA d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    lines = _mos_lines(result)
    assert len(lines) == 1
    assert lines[0].split()[0].lower() == "maa"


def test_parallel_skip_different_l():
    """Identical pins + identical W but different L -- must NOT parallel-merge."""
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 d g s b nmos_rvt w=100n l=200n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 2


def test_parallel_skip_different_models():
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 d g s b pmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 2


def test_parallel_skip_different_nodes():
    """A different drain net breaks parallel grouping even if everything else
    matches."""
    text = (
        ".subckt FOO d1 d2 g s b\n"
        "m1 d1 g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 d2 g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 2


def test_parallel_with_m_multiplier_aggregates_correctly():
    """Each device contributes w*nf*m to the merged W -- here W_total =
    100n*2 + 100n*3 = 500n."""
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g s b nmos_rvt w=100n l=130n nf=1 m=2\n"
        "m2 d g s b nmos_rvt w=100n l=130n nf=1 m=3\n"
        ".ends FOO\n"
    )
    # m1 and m2 differ in m -> ALIGN's parity rule does NOT group them.
    # Each emits independently with W = 100n * nf * m.
    result = translate(text, suffix="_0")
    lines = _mos_lines(result)
    assert len(lines) == 2
    assert "W=0.2u" in result  # from m1 (100n * 1 * 2)
    assert "W=0.3u" in result  # from m2 (100n * 1 * 3)


def test_parallel_then_series_pipeline():
    """A parallel pair on one side of a series net should fold to one device
    that then series-merges with the partner on the far side. Pipeline order:
    parallel -> series -> dummy."""
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g mid b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 d g mid b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m3 mid g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    # Parallel pass folds m1+m2 -> m1 (W=200n).
    # Series pass folds m1+m3 over `mid` -> m1 absorbs S=s. m3 dropped.
    # Final: 1 MOS line, m1, nodes (d, g, s, b), W=200n.
    result = translate(text, suffix="_0")
    lines = _mos_lines(result)
    assert len(lines) == 1
    toks = lines[0].split()
    assert toks[0].lower() == "m1"
    assert [t.lower() for t in toks[1:5]] == ["d", "g", "s", "b"]
    assert "W=0.2u" in result


def test_telescopic_ota_no_parallel_merges():
    """Telescopic OTA's cascodes share models but differ in gates -- the
    parallel pass must not fire on any of them. Backs the golden test."""
    text = OTA_USER_SP.read_text()
    subckts = _parse_subckts(text.splitlines())
    assert len(subckts) == 1
    dropped, w_overrides = merge_parallel_devices(subckts[0])
    assert dropped == set(), f"unexpected parallel drops: {dropped}"
    assert w_overrides == {}


def test_cmc_ota_no_parallel_merges_before_series():
    """CMC OTA's cascode partners share models but their 4-node tuples
    differ (stack-internal nets), so parallel pass must not fire. The
    Phase N golden case (12-MOS -> 10-MOS) depends on series merging only."""
    text = CMC_OTA_USER_SP.read_text()
    subckts = _parse_subckts(text.splitlines())
    assert len(subckts) == 1
    dropped, w_overrides = merge_parallel_devices(subckts[0])
    assert dropped == set(), f"unexpected parallel drops on CMC OTA: {dropped}"
    assert w_overrides == {}


# -- Dummy removal ---------------------------------------------------------

def test_dummy_pmos_gate_to_vdd_dropped():
    """A PMOS whose gate is tied to vdd is an always-off pull-up -> drop."""
    text = (
        ".subckt FOO d s b vdd\n"
        "m1 d vdd s b pmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    assert _mos_lines(result) == []


def test_dummy_nmos_gate_to_vss_dropped():
    text = (
        ".subckt FOO d s b vss\n"
        "m1 d vss s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    assert _mos_lines(result) == []


def test_dummy_nmos_gate_to_gnd_dropped():
    """'gnd' is in the default ground set."""
    text = (
        ".subckt FOO d s b gnd\n"
        "m1 d gnd s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    assert _mos_lines(result) == []


def test_dummy_nmos_gate_to_zero_dropped():
    """SPICE classical ground '0' is in the default ground set."""
    text = (
        ".subckt FOO d s b\n"
        "m1 d 0 s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    assert _mos_lines(result) == []


def test_dummy_diode_shorted_dropped():
    """A MOS with D == G == S is a decap-style single-net dummy -> drop."""
    text = (
        ".subckt FOO net b\n"
        "m1 net net net b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    result = translate(text, suffix="_0")
    assert _mos_lines(result) == []


def test_dummy_normal_mos_preserved():
    """A normal MOS (gate not on a power/ground rail, D!=G!=S) is preserved."""
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 1


def test_dummy_pmos_gate_to_ground_preserved():
    """A PMOS gate tied to GROUND is a normal switch (always on) -> keep."""
    text = (
        ".subckt FOO d s b vss\n"
        "m1 d vss s b pmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    # PMOS with G in gnd set: not in any drop pattern (only PMOS-to-power
    # drops, and D==G==S is false here). Preserved.
    assert len(_mos_lines(translate(text))) == 1


def test_dummy_nmos_gate_to_power_preserved():
    """An NMOS gate tied to POWER is a normal switch (always on) -> keep."""
    text = (
        ".subckt FOO d s b vdd\n"
        "m1 d vdd s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 1


def test_dummy_custom_power_net():
    """CLI --power flag overrides the default power-net set."""
    text = (
        ".subckt FOO d s b avdd\n"
        "m1 d avdd s b pmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    # Default does not include 'avdd' -> m1 preserved.
    assert len(_mos_lines(translate(text))) == 1
    # Custom power set covers 'avdd' -> m1 dropped.
    result = translate(text, power_nets={"avdd"})
    assert _mos_lines(result) == []


def test_dummy_telescopic_ota_no_false_drops():
    """Telescopic OTA must not lose any device to the dummy pass. Backs the
    golden LVS test."""
    text = OTA_USER_SP.read_text()
    subckts = _parse_subckts(text.splitlines())
    dropped = remove_dummy_mos_devices(
        subckts[0],
        power_nets=DEFAULT_POWER_NETS,
        gnd_nets=DEFAULT_GROUND_NETS,
    )
    assert dropped == set(), f"unexpected dummy drops on telescopic OTA: {dropped}"


def test_dummy_cmc_ota_no_false_drops():
    """CMC OTA must not lose any device to the dummy pass. Backs Phase N."""
    text = CMC_OTA_USER_SP.read_text()
    subckts = _parse_subckts(text.splitlines())
    dropped = remove_dummy_mos_devices(
        subckts[0],
        power_nets=DEFAULT_POWER_NETS,
        gnd_nets=DEFAULT_GROUND_NETS,
    )
    assert dropped == set(), f"unexpected dummy drops on CMC OTA: {dropped}"


# -- Nested subcircuit support -----------------------------------------------

def test_nested_subckt_devices_assigned_correctly():
    """Devices inside an inner subckt belong to it; devices in the outer
    subckt (before and after the inner block) belong to the outer."""
    text = (
        ".subckt OUTER a b c\n"
        "m1 a b 0 0 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".subckt INNER x y\n"
        "m2 x y 0 0 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends INNER\n"
        "m3 c b 0 0 pmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends OUTER\n"
    )
    subckts = _parse_subckts(text.splitlines())
    assert len(subckts) == 2
    outer = [s for s in subckts if s.name == "OUTER"][0]
    inner = [s for s in subckts if s.name == "INNER"][0]
    assert len(outer.devices) == 2, f"outer should have m1+m3, got {len(outer.devices)}"
    assert len(inner.devices) == 1, f"inner should have m2, got {len(inner.devices)}"
    assert outer.devices[0].name.lower() == "m1"
    assert outer.devices[1].name.lower() == "m3"
    assert inner.devices[0].name.lower() == "m2"


def test_nested_subckt_translate_renames_both():
    """Both outer and inner subckts get renamed with the suffix."""
    text = (
        ".subckt OUTER a b\n"
        "m1 a b 0 0 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".subckt INNER x y\n"
        "m2 x y 0 0 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends INNER\n"
        ".ends OUTER\n"
    )
    result = translate(text, suffix="_0")
    assert ".SUBCKT OUTER_0 " in result
    assert ".ENDS OUTER_0" in result
    assert ".SUBCKT INNER_0 " in result
    assert ".ENDS INNER_0" in result


def test_nested_subckt_merge_independent():
    """Parallel merge within the inner subckt does not affect the outer."""
    text = (
        ".subckt OUTER d g s b\n"
        "m1 d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".subckt INNER x y z w\n"
        "mA x y z w nmos_rvt w=100n l=130n nf=1 m=1\n"
        "mB x y z w nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends INNER\n"
        "m2 s g d b pmos_rvt w=200n l=130n nf=1 m=1\n"
        ".ends OUTER\n"
    )
    subckts = _parse_subckts(text.splitlines())
    inner = [s for s in subckts if s.name == "INNER"][0]
    dp, wo = merge_parallel_devices(inner)
    assert len(dp) == 1, "inner should have 1 parallel-merged drop"
    outer = [s for s in subckts if s.name == "OUTER"][0]
    dp_o, wo_o = merge_parallel_devices(outer)
    assert dp_o == set(), "outer should have no parallel merges"


def test_nested_subckt_three_levels():
    """Stack-based parser handles depth > 2."""
    text = (
        ".subckt L1 a b\n"
        "m1 a b 0 0 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".subckt L2 c d\n"
        "m2 c d 0 0 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".subckt L3 e f\n"
        "m3 e f 0 0 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends L3\n"
        "m4 d c 0 0 pmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends L2\n"
        "m5 b a 0 0 pmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends L1\n"
    )
    subckts = _parse_subckts(text.splitlines())
    assert len(subckts) == 3
    by_name = {s.name: s for s in subckts}
    assert len(by_name["L1"].devices) == 2  # m1, m5
    assert len(by_name["L2"].devices) == 2  # m2, m4
    assert len(by_name["L3"].devices) == 1  # m3


def test_nested_subckt_series_merge_inner_only():
    """Series merge in the inner subckt should not touch outer devices."""
    text = (
        ".subckt OUTER d g s b\n"
        "m_out d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".subckt INNER d2 g2 s2 b2\n"
        "mA d2 g2 stk b2 nmos_rvt w=100n l=130n nf=1 m=1\n"
        "mB stk g2 s2 b2 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends INNER\n"
        ".ends OUTER\n"
    )
    result = translate(text, suffix="_0")
    outer_lines = []
    inner_lines = []
    in_inner = False
    for line in result.splitlines():
        if "INNER" in line and line.strip().startswith(".SUBCKT"):
            in_inner = True
        elif "INNER" in line and line.strip().startswith(".ENDS"):
            in_inner = False
        elif line.split() and line.split()[0].lower().startswith("m") and not line.startswith("."):
            if in_inner:
                inner_lines.append(line)
            else:
                outer_lines.append(line)
    assert len(outer_lines) == 1, f"outer should keep 1 device, got {len(outer_lines)}"
    assert len(inner_lines) == 1, f"inner should merge to 1 device, got {len(inner_lines)}"


def test_flatten_two_level_hierarchy():
    """Two-level hierarchy: leaf subcircuit instantiated by top-level."""
    text = (
        ".subckt leaf a b vdd\n"
        "mp0 a a vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "mp1 b a vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        ".ends leaf\n"
        "\n"
        ".subckt top_cell in out vbias vdd vss\n"
        "mn0 tail vbias vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "mn1 out in tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "xi_ld out in vdd leaf\n"
        ".ends top_cell\n"
    )
    lines = _flatten_deck(text.splitlines())
    body = [l for l in lines if l.strip() and l.split()[0].lower().startswith("m")]
    assert len(body) == 4, f"expected 4 devices after flattening, got {len(body)}"
    subckt_headers = [l for l in lines if l.lower().strip().startswith(".subckt")]
    assert len(subckt_headers) == 1, "should have exactly 1 subckt after flattening"
    assert "top_cell" in subckt_headers[0].lower()


def test_flatten_three_level_hierarchy():
    """Three-level hierarchy: leaf -> mid -> top."""
    text = (
        ".subckt inv a vdd vss z\n"
        "mn0 z a vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "mp1 z a vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        ".ends inv\n"
        "\n"
        ".subckt buf a vdd vss z\n"
        "xi0 a vdd vss mid inv\n"
        "xi1 mid vdd vss z inv\n"
        ".ends buf\n"
        "\n"
        ".subckt top_3l clk vdd vss out\n"
        "mn_tail tail clk vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "xi_buf clk vdd vss out buf\n"
        ".ends top_3l\n"
    )
    lines = _flatten_deck(text.splitlines())
    body = [l for l in lines if l.strip() and l.split()[0].lower().startswith("m")]
    assert len(body) == 5, f"expected 5 devices (1 tail + 4 inv), got {len(body)}"
    subckt_headers = [l for l in lines if l.lower().strip().startswith(".subckt")]
    assert len(subckt_headers) == 1
    assert "top_3l" in subckt_headers[0].lower()
    flat_text = "\n".join(lines)
    assert "i_buf_i0_" in flat_text.lower() or "i_buf_i1_" in flat_text.lower(), \
        "internal nets should carry hierarchy prefix"


def test_flatten_noop_for_flat_input():
    """Flat input (single subcircuit) should pass through unchanged."""
    text = (
        ".subckt flat_circ a b vdd vss\n"
        "mn0 a b vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        ".ends flat_circ\n"
    )
    lines_in = text.splitlines()
    lines_out = _flatten_deck(lines_in)
    assert lines_out is lines_in, "single subcircuit should return same list object"


def test_flatten_noop_for_nested_no_instances():
    """Truly nested subckt with no cross-references should not flatten."""
    text = (
        ".subckt OUTER d g s b\n"
        "m_out d g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".subckt INNER d2 g2 s2 b2\n"
        "mA d2 g2 stk b2 nmos_rvt w=100n l=130n nf=1 m=1\n"
        "mB stk g2 s2 b2 nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends INNER\n"
        ".ends OUTER\n"
    )
    lines_in = text.splitlines()
    lines_out = _flatten_deck(lines_in)
    assert lines_out is lines_in, "no cross-references: should return same list object"


def test_flatten_translate_end_to_end():
    """Full translate with flatten: hierarchical input, flat LVS-ready output."""
    text = (
        ".subckt cm_load d m vdd\n"
        "mp0 d d vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "mp1 m d vdd vdd pmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        ".ends cm_load\n"
        "\n"
        ".subckt dpair vin vip vn vp vb vdd vss\n"
        "mn0 tail vb vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "mn1 vn vin tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "mn2 vp vip tail vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "xi_ld vn vp vdd cm_load\n"
        ".ends dpair\n"
    )
    result = translate(text, suffix="_0")
    lines = result.strip().splitlines()
    subckt_lines = [l for l in lines if l.upper().startswith(".SUBCKT")]
    assert len(subckt_lines) == 1, f"should have 1 subckt, got {len(subckt_lines)}"
    assert "DPAIR_0" in subckt_lines[0]
    dev_lines = [l for l in lines if l.split() and l.split()[0].lower().startswith("m")]
    assert len(dev_lines) == 5, f"expected 5 devices, got {len(dev_lines)}"
    mos_models = {l.split()[5] for l in dev_lines}
    assert mos_models == {"sg13_lv_nmos", "sg13_lv_pmos"}


# -- Passive / BJT translation -----------------------------------------------

def test_bjt_npn13g2_case_normalised():
    """User-facing lowercase npn13g2 must become KLayout's npn13G2."""
    line = "Q1 c1 b1 e1 npn13g2"
    out = translate_passive_line(line)
    assert "npn13G2" in out
    assert out.split()[0] == "Q1"


def test_bjt_npn13g2l_case_normalised():
    line = "Q2 c b e s npn13g2l we=70n le=1u Nx=1 m=1"
    out = translate_passive_line(line)
    assert "npn13G2l" in out
    assert "we=70n" in out


def test_bjt_npn13g2v_case_normalised():
    line = "Qhv c b e npn13g2v"
    out = translate_passive_line(line)
    assert "npn13G2v" in out


def test_bjt_pnpmpa_case_normalised():
    line = "Q3 c b e pnpmpa w=1u l=1u"
    out = translate_passive_line(line)
    assert "pnpMPA" in out


def test_bjt_unknown_model_passes_through():
    line = "Q1 c b e some_other_bjt"
    assert translate_passive_line(line) == line


def test_resistor_rsil_zeroes_ps():
    """rsil: ps/b zeroed to match extraction defaults."""
    line = "R1 n1 n2 sub rsil w=0.5u l=10u ps=0.5u m=1"
    out = translate_passive_line(line)
    assert "rsil" in out
    assert "ps=0" in out
    assert "w=0.5u" in out


def test_resistor_rppd_zeroes_ps_b():
    line = "R2 n1 n2 sub rppd w=0.5u l=10u ps=0.5u b=0 m=1"
    out = translate_passive_line(line)
    assert "rppd" in out
    assert "ps=0" in out
    assert "b=0" in out


def test_resistor_rhigh_zeroes_ps():
    line = "R3 n1 n2 sub rhigh w=0.5u l=10u ps=0.5u b=0 m=1"
    out = translate_passive_line(line)
    assert "rhigh" in out
    assert "ps=0" in out


def test_cap_cmim_passes_through():
    """cap_cmim model name matches extraction."""
    line = "C1 plus minus cap_cmim w=7u l=7u m=1"
    assert translate_passive_line(line) == line


def test_cap_rfcmim_passes_through():
    line = "C2 plus minus sub rfcmim w=7u l=7u wfeed=3u m=1"
    assert translate_passive_line(line) == line


def test_passive_non_device_line_unchanged():
    """Non-device lines must pass through."""
    for line in ["* comment", ".include foo.sp", ".subckt TOP a b", ""]:
        assert translate_passive_line(line) == line


def test_mos_line_not_touched_by_passive():
    """MOS lines must not be modified by translate_passive_line."""
    line = "m1 d g s b nmos_rvt w=100n l=130n nf=1 m=1"
    assert translate_passive_line(line) == line


def test_translate_mixed_mos_bjt_subckt():
    """Full translate() handles MOS and BJT lines in the same subcircuit."""
    text = (
        ".subckt bandgap vout vdd vss\n"
        "m1 vout vbias vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "Q1 c1 b1 e1 npn13g2\n"
        "R1 vdd c1 vss rsil w=0.5u l=10u ps=0.5u\n"
        "C1 vout vss cap_cmim w=7u l=7u\n"
        ".ends bandgap\n"
    )
    result = translate(text, suffix="_0")
    assert ".SUBCKT BANDGAP_0 " in result
    assert "sg13_lv_nmos" in result
    assert "npn13G2" in result
    assert "rsil" in result
    assert "cap_cmim" in result


def test_translate_bjt_in_subckt_rename():
    """BJT model names normalised even after subckt renaming."""
    text = (
        ".subckt npn_test c b e\n"
        "Q1 c b e npn13g2\n"
        ".ends npn_test\n"
    )
    result = translate(text, suffix="_0")
    assert ".SUBCKT NPN_TEST_0 " in result
    assert "npn13G2" in result


def test_looks_like_user_spice_detects_bjt():
    """Auto-detect should trigger on BJT model names."""
    text = ".subckt foo a b\nQ1 a b e npn13g2\n.ends foo\n"
    assert looks_like_user_spice(text) is True


def test_looks_like_user_spice_detects_pnpmpa():
    text = ".subckt foo a b\nQ1 a b e pnpmpa\n.ends foo\n"
    assert looks_like_user_spice(text) is True


def test_flatten_hierarchy_with_bjt():
    """Flattener remaps BJT nets correctly."""
    text = (
        ".subckt bias c b e\n"
        "Q1 c b e npn13g2\n"
        ".ends bias\n"
        "\n"
        ".subckt top out vdd vss\n"
        "mn0 tail vbias vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "xi_q out vdd vss bias\n"
        ".ends top\n"
    )
    result = translate(text, suffix="_0")
    assert ".SUBCKT TOP_0 " in result
    assert "npn13G2" in result
    bjt_lines = [l for l in result.splitlines() if l.strip().startswith("Q")]
    assert len(bjt_lines) == 1
    toks = bjt_lines[0].split()
    assert toks[1].lower() == "out"
    assert toks[2].lower() == "vdd"
    assert toks[3].lower() == "vss"


def test_flatten_hierarchy_with_resistor():
    """Flattener remaps resistor nets correctly."""
    text = (
        ".subckt rload a b sub\n"
        "R1 a b sub rsil w=0.5u l=10u ps=0.5u\n"
        ".ends rload\n"
        "\n"
        ".subckt top out vdd vss\n"
        "mn0 out vbias vss vss nmos_rvt w=560e-9 l=130e-9 nf=4 m=1\n"
        "xi_r out vdd vss rload\n"
        ".ends top\n"
    )
    result = translate(text, suffix="_0")
    res_lines = [l for l in result.splitlines() if l.strip().startswith("R")]
    assert len(res_lines) == 1
    toks = res_lines[0].split()
    assert toks[1].lower() == "out"
    assert toks[2].lower() == "vdd"
    assert toks[3].lower() == "vss"
    assert "rsil" in res_lines[0]


def _all_tests():
    return [
        (name, obj)
        for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]


def main() -> int:
    passed = 0
    failed = 0
    for name, fn in _all_tests():
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
        except Exception as exc:
            failed += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS {name}")
    total = passed + failed
    print(f"\nresult: {passed}/{total} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
