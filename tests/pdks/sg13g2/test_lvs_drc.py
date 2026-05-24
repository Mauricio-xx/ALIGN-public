import xml.etree.ElementTree as ET

import pytest


pytestmark = pytest.mark.sg13g2


class TestLVS:

    def test_exit_code(self, lvs_result):
        result, _ = lvs_result
        assert result.returncode == 0, (
            f"LVS wrapper failed (rc={result.returncode})\n"
            f"stderr tail:\n{result.stderr[-2000:]}"
        )

    def test_netlists_match(self, lvs_result, circuit):
        result, run_dir = lvs_result
        assert result.returncode == 0, "LVS wrapper failed"

        log = run_dir / f"{circuit['topcell']}.log"
        assert log.exists(), f"LVS log not found: {log}"
        text = log.read_text()
        assert "Congratulations! Netlists match." in text, (
            f"LVS FAIL for {circuit['topcell']}\n"
            f"log tail:\n{text[-1000:]}"
        )

    def test_translated_netlist_created(self, lvs_result, circuit):
        _, run_dir = lvs_result
        translated = run_dir / f"{circuit['name']}.lvs.sp"
        assert translated.exists(), f"Translated netlist not found: {translated}"


class TestDRC:

    def test_exit_code(self, drc_result):
        result, _ = drc_result
        assert result.returncode == 0, (
            f"DRC wrapper failed (rc={result.returncode})\n"
            f"stderr tail:\n{result.stderr[-2000:]}"
        )

    def test_zero_violations(self, drc_result, circuit):
        result, run_dir = drc_result
        assert result.returncode == 0, "DRC wrapper failed"

        topcell = circuit["topcell"]
        lyrdb_files = list(run_dir.glob("*_full.lyrdb"))
        assert lyrdb_files, f"No lyrdb output in {run_dir}"

        for lyrdb in lyrdb_files:
            tree = ET.parse(str(lyrdb))
            items = tree.findall(".//item")
            if items:
                cats = sorted(set(
                    it.find("category").text.strip("'")
                    for it in items if it.find("category") is not None
                ))
                pytest.fail(
                    f"DRC found {len(items)} violations in {topcell}: "
                    + ", ".join(cats)
                )
