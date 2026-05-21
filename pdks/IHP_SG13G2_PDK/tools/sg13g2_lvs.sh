#!/usr/bin/env bash
# IHP SG13G2 LVS wrapper for ALIGN-generated GDS.
#
# Usage:
#   sg13g2_lvs.sh [--run_dir DIR] [--topcell NAME] [--net_only]
#                 [--implicit_nets "VDD,VSS"] <input.gds> [<schematic.spice>]
#
# Requires:
#   IHP_PDK_ROOT pointing at the IHP-Open-PDK clone (dev branch).
#   klayout in PATH.
#
# If schematic is omitted the wrapper falls back to --net_only (extraction only).

set -euo pipefail

RUN_DIR=""
TOPCELL=""
NET_ONLY=0
IMPLICIT=""

usage() {
    sed -n '/^# IHP SG13G2 LVS wrapper/,/^$/p' "$0" | sed 's/^# //;s/^#//'
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --run_dir) RUN_DIR="$2"; shift 2;;
        --topcell) TOPCELL="$2"; shift 2;;
        --net_only) NET_ONLY=1; shift;;
        --implicit_nets) IMPLICIT="$2"; shift 2;;
        -h|--help) usage;;
        --) shift; break;;
        -*) echo "unknown flag: $1" >&2; usage;;
        *) break;;
    esac
done

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "expected 1 or 2 positional args: <gds> [<schematic>]" >&2
    usage
fi

LAYOUT="$1"
NETLIST="${2:-}"

if [[ ! -f "$LAYOUT" ]]; then
    echo "input GDS not found: $LAYOUT" >&2
    exit 2
fi
if [[ -z "$NETLIST" ]]; then
    NET_ONLY=1
elif [[ ! -f "$NETLIST" ]]; then
    echo "schematic netlist not found: $NETLIST" >&2
    exit 2
fi

: "${IHP_PDK_ROOT:?IHP_PDK_ROOT must point at an IHP-Open-PDK clone}"
RUN_LVS_PY="$IHP_PDK_ROOT/ihp-sg13g2/libs.tech/klayout/tech/lvs/run_lvs.py"
if [[ ! -f "$RUN_LVS_PY" ]]; then
    echo "run_lvs.py not found at $RUN_LVS_PY" >&2
    exit 2
fi

ARGS=( --layout "$(readlink -f "$LAYOUT")" )
if [[ -n "$NETLIST" ]]; then
    ARGS+=( --netlist "$(readlink -f "$NETLIST")" )
fi
if [[ $NET_ONLY -eq 1 ]]; then
    ARGS+=( --net_only )
fi
if [[ -n "$RUN_DIR" ]]; then
    ARGS+=( --run_dir "$RUN_DIR" )
fi
if [[ -n "$TOPCELL" ]]; then
    ARGS+=( --topcell "$TOPCELL" )
fi
if [[ -n "$IMPLICIT" ]]; then
    ARGS+=( --implicit_nets "$IMPLICIT" )
fi

echo ">> sg13g2_lvs.sh: gds=$LAYOUT netlist=${NETLIST:-<none>} net_only=$NET_ONLY"
python3 "$RUN_LVS_PY" "${ARGS[@]}"
