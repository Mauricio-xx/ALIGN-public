#!/usr/bin/env bash
# IHP SG13G2 DRC wrapper for ALIGN-generated GDS.
#
# Usage:
#   sg13g2_drc.sh [--mode minimal|maximal] [--run_dir DIR] [--topcell NAME] <input.gds>
#
# Requires:
#   IHP_PDK_ROOT pointing at the IHP-Open-PDK clone (dev branch).
#   klayout in PATH (uses the python3 + klayout.db modules from the IHP env).
#
# Modes:
#   minimal   - --precheck_drc, fast subset of foundry-required rules (default).
#   maximal   - full deck via $IHP_PDK_ROOT/.../drc/rule_decks/sg13g2_maximal.drc style
#               (passed as no extra flags so the deck runs in its default mode + every BEOL/FEOL table).
#
# Exit codes:
#   0 - run completed (violations may still exist; check the RDB summary printed)
#   2 - argument / setup error
#   non-zero - klayout failure surfaced from run_drc.py

set -euo pipefail

MODE=minimal
RUN_DIR=""
TOPCELL=""

usage() {
    sed -n '/^# IHP SG13G2 DRC wrapper/,/^$/p' "$0" | sed 's/^# //;s/^#//'
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode) MODE="$2"; shift 2;;
        --run_dir) RUN_DIR="$2"; shift 2;;
        --topcell) TOPCELL="$2"; shift 2;;
        -h|--help) usage;;
        --) shift; break;;
        -*) echo "unknown flag: $1" >&2; usage;;
        *) break;;
    esac
done

if [[ $# -ne 1 ]]; then
    echo "expected exactly one positional GDS argument" >&2
    usage
fi

INPUT_GDS="$1"
if [[ ! -f "$INPUT_GDS" ]]; then
    echo "input GDS not found: $INPUT_GDS" >&2
    exit 2
fi

: "${IHP_PDK_ROOT:?IHP_PDK_ROOT must point at an IHP-Open-PDK clone}"
RUN_DRC_PY="$IHP_PDK_ROOT/ihp-sg13g2/libs.tech/klayout/tech/drc/run_drc.py"
if [[ ! -f "$RUN_DRC_PY" ]]; then
    echo "run_drc.py not found at $RUN_DRC_PY" >&2
    exit 2
fi

EXTRA_ARGS=()
case "$MODE" in
    minimal) EXTRA_ARGS+=( --precheck_drc );;
    maximal) ;;
    *) echo "unknown mode: $MODE (use minimal|maximal)" >&2; exit 2;;
esac

if [[ -n "$RUN_DIR" ]]; then
    EXTRA_ARGS+=( --run_dir "$RUN_DIR" )
fi
if [[ -n "$TOPCELL" ]]; then
    EXTRA_ARGS+=( --topcell "$TOPCELL" )
fi

ABS_GDS=$(readlink -f "$INPUT_GDS")
echo ">> sg13g2_drc.sh: mode=$MODE gds=$ABS_GDS"
echo ">> running $RUN_DRC_PY"

python3 "$RUN_DRC_PY" --path "$ABS_GDS" "${EXTRA_ARGS[@]}"
