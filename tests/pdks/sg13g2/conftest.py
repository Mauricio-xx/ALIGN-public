import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PDK_DIR = REPO_ROOT / "pdks" / "IHP_SG13G2_PDK"
EXAMPLES_DIR = REPO_ROOT / "examples"
TOOLS_DIR = PDK_DIR / "tools"
DOCKER_IMAGE = "align-ihp:latest"

FLAT_CIRCUITS = [
    "inverter_v1_sg13g2",
    "common_source_sg13g2",
    "telescopic_ota_sg13g2",
    "current_mirror_ota_sg13g2",
    "five_transistor_ota_sg13g2",
    "strong_arm_comp_sg13g2",
]

HIER_CIRCUITS = [
    "diff_pair_hier_sg13g2",
    "comparator_hier_sg13g2",
    "comparator1_sg13g2",
]

ALL_CIRCUITS = FLAT_CIRCUITS + HIER_CIRCUITS


def _docker_available():
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", DOCKER_IMAGE],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _ihp_pdk_root():
    root = os.environ.get("IHP_PDK_ROOT", "")
    if root:
        p = Path(root)
        if (p / "ihp-sg13g2/libs.tech/klayout/tech/lvs/run_lvs.py").exists():
            return p
    return None


KLAYOUT_SEARCH = ["/usr/bin/klayout", "klayout"]


def _find_klayout():
    for candidate in KLAYOUT_SEARCH:
        try:
            r = subprocess.run(
                [candidate, "-v"], capture_output=True, text=True, timeout=5,
            )
            m = re.search(r"(\d+)\.(\d+)\.(\d+)", r.stdout + r.stderr)
            if m and tuple(int(x) for x in m.groups()) >= (0, 30, 2):
                return candidate
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


KLAYOUT_BIN = _find_klayout()


HAS_DOCKER = _docker_available()
HAS_IHP_PDK = _ihp_pdk_root() is not None
HAS_KLAYOUT = KLAYOUT_BIN is not None

requires_docker = pytest.mark.skipif(
    not HAS_DOCKER, reason=f"Docker image '{DOCKER_IMAGE}' not available"
)
requires_lvs_drc = pytest.mark.skipif(
    not (HAS_IHP_PDK and HAS_KLAYOUT),
    reason="IHP_PDK_ROOT or klayout >= 0.30.2 not available",
)


def _topcell(circuit_name):
    return circuit_name.upper() + "_0"


@pytest.fixture(scope="session")
def work_root(tmp_path_factory):
    env = os.environ.get("ALIGN_WORK_DIR", "")
    if env:
        base = Path(env).resolve() / "sg13g2_tests"
    else:
        base = tmp_path_factory.mktemp("sg13g2")
    base.mkdir(parents=True, exist_ok=True)
    return base


@pytest.fixture(scope="session")
def ihp_pdk_root():
    root = _ihp_pdk_root()
    if root is None:
        pytest.skip("IHP_PDK_ROOT not set or invalid")
    return root


@pytest.fixture(scope="session", params=ALL_CIRCUITS, ids=lambda c: c)
def circuit(request, work_root):
    name = request.param
    example_dir = EXAMPLES_DIR / name
    assert example_dir.is_dir(), f"Missing example: {example_dir}"

    work_dir = work_root / name
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir = work_dir / "output" / "run"
    output_dir.mkdir(parents=True, exist_ok=True)

    topcell = _topcell(name)
    gds = output_dir / f"{topcell}.gds"
    spice = example_dir / f"{name}.sp"

    return {
        "name": name,
        "example_dir": example_dir,
        "work_dir": work_dir,
        "output_dir": output_dir,
        "topcell": topcell,
        "gds": gds,
        "spice": spice,
    }


@pytest.fixture(scope="session")
def pnr_result(circuit):
    if not HAS_DOCKER:
        pytest.skip(f"Docker image '{DOCKER_IMAGE}' not available")

    output_parent = circuit["output_dir"].parent
    log_dir = circuit["work_dir"] / "LOG"
    log_dir.mkdir(parents=True, exist_ok=True)
    pnr_main = REPO_ROOT / "align" / "pnr" / "main.py"
    cmd = [
        "docker", "run", "--rm",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{pnr_main}:/usr/local/lib/python3.10/dist-packages/align/pnr/main.py:ro",
        "-v", f"{REPO_ROOT}/pdks:/work/pdks:ro",
        "-v", f"{circuit['example_dir']}:/work/input:ro",
        "-v", f"{output_parent}:/work/output",
        "-v", f"{log_dir}:/work/LOG",
        "-w", "/work",
        "-e", "ALIGN_WORK_DIR=/tmp/align_work",
        DOCKER_IMAGE,
        "schematic2layout.py",
        "/work/input",
        "-p", "pdks/IHP_SG13G2_PDK",
        "-w", "/work/output/run",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return result


def _signoff_env(ihp_root):
    env = os.environ.copy()
    env["IHP_PDK_ROOT"] = str(ihp_root)
    if KLAYOUT_BIN:
        klayout_dir = str(Path(KLAYOUT_BIN).parent)
        env["PATH"] = klayout_dir + ":" + env.get("PATH", "")
    env.pop("KLAYOUT_HOME", None)
    env.pop("KLAYOUT_PATH", None)
    return env


@pytest.fixture(scope="session")
def lvs_result(circuit, ihp_pdk_root, pnr_result):
    gds = circuit["gds"]
    if not gds.exists():
        pytest.skip(f"GDS not found: {gds}")

    run_dir = circuit["work_dir"] / "lvs"
    run_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "bash", str(TOOLS_DIR / "sg13g2_lvs.sh"),
        "--run_dir", str(run_dir),
        str(gds), str(circuit["spice"]),
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        env=_signoff_env(ihp_pdk_root), timeout=120,
    )
    return result, run_dir


@pytest.fixture(scope="session")
def drc_result(circuit, ihp_pdk_root, pnr_result):
    gds = circuit["gds"]
    if not gds.exists():
        pytest.skip(f"GDS not found: {gds}")

    run_dir = circuit["work_dir"] / "drc"
    run_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "bash", str(TOOLS_DIR / "sg13g2_drc.sh"),
        "--mode", "prototype",
        "--run_dir", str(run_dir),
        str(gds),
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        env=_signoff_env(ihp_pdk_root), timeout=120,
    )
    return result, run_dir
