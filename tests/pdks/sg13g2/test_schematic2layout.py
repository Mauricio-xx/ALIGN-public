import pytest


pytestmark = pytest.mark.sg13g2


class TestSchematic2Layout:

    def test_exit_code(self, pnr_result):
        assert pnr_result.returncode == 0, (
            f"schematic2layout failed (rc={pnr_result.returncode})\n"
            f"stderr tail:\n{pnr_result.stderr[-2000:]}"
        )

    def test_gds_produced(self, pnr_result, circuit):
        assert pnr_result.returncode == 0, "P&R failed"
        gds = circuit["gds"]
        assert gds.exists(), f"GDS not found: {gds}"
        assert gds.stat().st_size > 0

    def test_lef_produced(self, pnr_result, circuit):
        assert pnr_result.returncode == 0, "P&R failed"
        lef = circuit["output_dir"] / f"{circuit['topcell']}.lef"
        assert lef.exists(), f"LEF not found: {lef}"
