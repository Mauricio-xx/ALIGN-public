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
    _parse_subckts,
    looks_like_user_spice,
    merge_series_stacks,
    parse_spice_value,
    translate,
    translate_device_line,
)

OTA_USER_SP = REPO / "examples/telescopic_ota_sg13g2/telescopic_ota_sg13g2.sp"
OTA_LVS_SP = REPO / "examples/telescopic_ota_sg13g2/telescopic_ota_sg13g2.lvs.sp"
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
    """Net with 3+ devices is not a series stack."""
    text = (
        ".subckt FOO d g s b\n"
        "m1 d g mid b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 mid g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m3 mid g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    assert len(_mos_lines(translate(text))) == 3


def test_series_stack_skip_parallel_dd():
    """D-D coupling is a parallel arrangement, not a series stack."""
    text = (
        ".subckt FOO g s b\n"
        "m1 dnet g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        "m2 dnet g s b nmos_rvt w=100n l=130n nf=1 m=1\n"
        ".ends FOO\n"
    )
    # 'g', 's', 'b' are ports. 'dnet' is internal but pins on both devices
    # touch it via D -> {D, D} fails the {D, S} predicate.
    assert len(_mos_lines(translate(text))) == 2


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
