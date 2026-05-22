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
    looks_like_user_spice,
    parse_spice_value,
    translate,
    translate_device_line,
)

OTA_USER_SP = REPO / "examples/telescopic_ota_sg13g2/telescopic_ota_sg13g2.sp"
OTA_LVS_SP = REPO / "examples/telescopic_ota_sg13g2/telescopic_ota_sg13g2.lvs.sp"


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
