"""Run a klayout python script in an isolated environment.

The IHP SG13G2 PyCells live in a `SG13_dev` library that klayout
auto-loads via tech-attached pymacros. If the user's ~/.klayout
contains multiple IHP techs (e.g. sg13g2 + sg13cmos5l), klayout
resolves the first matching library which may be the wrong PDK.
We sidestep this by pointing KLAYOUT_HOME at a fresh tmpdir so
only KLAYOUT_PATH=<sg13g2 tech root> is honored.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class KLayoutRunError(RuntimeError):
    pass


def _ihp_klayout_root() -> Path:
    pdk_root = os.environ.get("IHP_PDK_ROOT")
    if not pdk_root:
        raise KLayoutRunError(
            "IHP_PDK_ROOT not set. Point it at the IHP-Open-PDK checkout."
        )
    root = Path(pdk_root) / "ihp-sg13g2" / "libs.tech" / "klayout"
    if not (root / "tech" / "sg13g2.lyt").is_file():
        raise KLayoutRunError(
            f"IHP_PDK_ROOT={pdk_root} does not contain ihp-sg13g2/libs.tech/klayout/tech/sg13g2.lyt"
        )
    return root


def run_klayout_script(script_body: str, log_prefix: str = "klayout") -> str:
    """Execute a klayout python script in batch mode with an isolated env.

    Prefers the klayout CLI binary in batch mode (-zz).  When the binary's
    embedded Python lacks _tkinter (common with Nix klayout), falls back to
    running the script with the current ``sys.executable`` after aliasing
    ``klayout.db`` as ``pya``.

    Returns combined stdout+stderr on success; raises KLayoutRunError otherwise.
    """
    klayout_bin = os.environ.get("KLAYOUT_BIN", "klayout")
    klayout_root = _ihp_klayout_root()

    preamble = (
        "import sys, os\n"
        "if 'pya' not in sys.modules:\n"
        "    try:\n"
        "        import klayout.db as _pya\n"
        "        sys.modules['pya'] = _pya\n"
        "    except ImportError:\n"
        "        pass\n"
        f"sys.path.insert(0, {str(klayout_root / 'python')!r})\n"
        f"sys.path.insert(0, {str(klayout_root / 'python' / 'pycell4klayout-api' / 'source' / 'python')!r})\n"
        f"os.environ['IHP_PDK_ROOT'] = os.environ.get('IHP_PDK_ROOT', {os.environ.get('IHP_PDK_ROOT', '')!r})\n"
    )

    with tempfile.TemporaryDirectory(prefix="klayout_isolated_") as klayout_home:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, prefix=f"{log_prefix}_"
        ) as fh:
            fh.write(script_body)
            script_path = fh.name
        try:
            env = os.environ.copy()
            env["KLAYOUT_HOME"] = klayout_home
            env["KLAYOUT_PATH"] = str(klayout_root)

            proc = subprocess.run(
                [klayout_bin, "-zz", "-r", script_path],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

            output = (proc.stdout or "") + (proc.stderr or "")
            has_real_error = any(
                "ERROR" in ln and "_tkinter" not in ln
                for ln in output.splitlines()
            )

            if proc.returncode != 0 or has_real_error:
                with open(script_path, "w") as fh2:
                    fh2.write(preamble + script_body)

                proc = subprocess.run(
                    [sys.executable, script_path],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                output = (proc.stdout or "") + (proc.stderr or "")
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    if proc.returncode != 0:
        raise KLayoutRunError(
            f"klayout exited with code {proc.returncode}\n--- output ---\n{output}"
        )
    for line in output.splitlines():
        if "ERROR" in line and "_tkinter" not in line:
            raise KLayoutRunError(f"klayout reported ERROR:\n--- output ---\n{output}")
    return output


def fmt_micron(meters: float) -> str:
    """Pretty-print meters as micron-string with 'p' as decimal point.

    10e-6  -> '10'
    1.5e-6 -> '1p5'
    0.5e-6 -> '0p5'
    """
    um = meters * 1e6
    if abs(um - round(um)) < 1e-9:
        return str(int(round(um)))
    s = f"{um:.3f}".rstrip("0").rstrip(".")
    return s.replace(".", "p")


def klayout_available() -> bool:
    return shutil.which(os.environ.get("KLAYOUT_BIN", "klayout")) is not None
