#!/usr/bin/env bash
# IHP SG13G2 LVS wrapper for ALIGN-generated GDS.
#
# Usage:
#   sg13g2_lvs.sh [--run_dir DIR] [--topcell NAME] [--net_only]
#                 [--implicit_nets "VDD,VSS"]
#                 [--translate | --no-translate] [--suffix _N]
#                 <input.gds> [<schematic.spice>]
#
# When the schematic uses ALIGN-side model aliases (nmos_rvt/pmos_rvt/nfet/
# pfet/nmosHV/pmosHV) the wrapper auto-translates it to an IHP-LVS-ready
# SPICE via tools/spice_to_ihp_lvs.py before invoking run_lvs.py. The
# translated netlist is written inside --run_dir as <name>.lvs.sp.
# Override with --translate (force) or --no-translate (skip) when needed.
#
# Requires:
#   IHP_PDK_ROOT pointing at the IHP-Open-PDK clone (dev branch).
#   klayout in PATH.
#
# If schematic is omitted the wrapper falls back to --net_only (extraction only).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSLATOR="$SCRIPT_DIR/spice_to_ihp_lvs.py"

RUN_DIR=""
TOPCELL=""
NET_ONLY=0
IMPLICIT=""
TRANSLATE_MODE="auto"   # auto | force | skip
SUFFIX="_0"
SUBSTRATE="sub!"
IGNORE_PORTS=0
MIXED_SIGNAL=0

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
        --translate) TRANSLATE_MODE="force"; shift;;
        --no-translate) TRANSLATE_MODE="skip"; shift;;
        --suffix) SUFFIX="$2"; shift 2;;
        --substrate) SUBSTRATE="$2"; shift 2;;
        --ignore-ports) IGNORE_PORTS=1; shift;;
        --mixed-signal) MIXED_SIGNAL=1; shift;;
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

EFFECTIVE_NETLIST="$NETLIST"
TRANSLATED_NETLIST=""

if [[ -n "$NETLIST" && "$TRANSLATE_MODE" != "skip" ]]; then
    NEED_TRANSLATE=0
    if [[ "$TRANSLATE_MODE" == "force" ]]; then
        NEED_TRANSLATE=1
    elif grep -E -iq '\b(nmos_rvt|pmos_rvt|nfet|pfet|nmosHV|pmosHV|nfet_3p3V|pfet_3p3V|npn13g2l?v?|pnpmpa)\b' "$NETLIST"; then
        NEED_TRANSLATE=1
    fi
    if [[ $NEED_TRANSLATE -eq 1 ]]; then
        if [[ ! -f "$TRANSLATOR" ]]; then
            echo "translator not found at $TRANSLATOR" >&2
            exit 2
        fi
        OUT_BASE="$(basename "$NETLIST")"
        OUT_BASE="${OUT_BASE%.sp}.lvs.sp"
        if [[ -n "$RUN_DIR" ]]; then
            mkdir -p "$RUN_DIR"
            TRANSLATED_NETLIST="$RUN_DIR/$OUT_BASE"
        else
            TRANSLATED_NETLIST="$(mktemp --suffix=".lvs.sp")"
        fi
        TRANS_ARGS=( "$NETLIST" -o "$TRANSLATED_NETLIST" --suffix "$SUFFIX" --substrate "$SUBSTRATE" )
        if [[ -n "$TOPCELL" ]]; then
            TRANS_ARGS+=( --topcell "$TOPCELL" )
        fi
        echo ">> sg13g2_lvs.sh: translating $NETLIST -> $TRANSLATED_NETLIST"
        python3 "$TRANSLATOR" "${TRANS_ARGS[@]}"
        EFFECTIVE_NETLIST="$TRANSLATED_NETLIST"
    fi
fi

ARGS=( --layout "$(readlink -f "$LAYOUT")" )
if [[ -n "$EFFECTIVE_NETLIST" ]]; then
    ARGS+=( --netlist "$(readlink -f "$EFFECTIVE_NETLIST")" )
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
if [[ $IGNORE_PORTS -eq 1 ]]; then
    ARGS+=( --ignore_top_ports_mismatch )
fi

if [[ $MIXED_SIGNAL -eq 1 && $NET_ONLY -eq 0 && -n "$EFFECTIVE_NETLIST" ]]; then
    # Workaround for KLayout SPICE reader uppercasing model names while
    # the extraction preserves mixed case (npn13G2 vs NPN13G2, rsil vs RSIL).
    # Extract first, fix case in the extracted netlist, then compare.
    echo ">> sg13g2_lvs.sh: mixed-signal mode -- extract + fix case + compare"
    EXTRACT_DIR="${RUN_DIR:-$(mktemp -d)}"
    mkdir -p "$EXTRACT_DIR"
    EXTRACT_ARGS=( --layout "$(readlink -f "$LAYOUT")" --net_only --run_dir "$EXTRACT_DIR" )
    [[ -n "$TOPCELL" ]] && EXTRACT_ARGS+=( --topcell "$TOPCELL" )
    python3 "$RUN_LVS_PY" "${EXTRACT_ARGS[@]}"
    EXTRACTED_CIR="$(ls "$EXTRACT_DIR"/*_extracted.cir 2>/dev/null | head -1)"
    if [[ -z "$EXTRACTED_CIR" ]]; then
        echo "ERROR: extraction produced no .cir file" >&2
        exit 1
    fi
    FIXED_CIR="${EXTRACTED_CIR%.cir}_fixed.cir"
    sed 's/npn13G2/NPN13G2/g; s/npn13G2l/NPN13G2L/g; s/npn13G2v/NPN13G2V/g; s/pnpMPA/PNPMPA/g; s/ rsil / RSIL /g; s/ rppd / RPPD /g; s/ rhigh / RHIGH /g' "$EXTRACTED_CIR" > "$FIXED_CIR"
    CMP_ARGS=( --layout_netlist "$(readlink -f "$FIXED_CIR")" --netlist "$(readlink -f "$EFFECTIVE_NETLIST")" --run_dir "$EXTRACT_DIR" --ignore_top_ports_mismatch )
    CELL_NAME="$(basename "$LAYOUT" .gds)"
    CMP_ARGS+=( --topcell "${TOPCELL:-$CELL_NAME}" )
    python3 "$RUN_LVS_PY" "${CMP_ARGS[@]}"
else
    echo ">> sg13g2_lvs.sh: gds=$LAYOUT netlist=${EFFECTIVE_NETLIST:-<none>} net_only=$NET_ONLY"
    python3 "$RUN_LVS_PY" "${ARGS[@]}"
fi
