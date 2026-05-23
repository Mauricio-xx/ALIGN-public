#!/usr/bin/env bash
# IHP SG13G2 density-fill wrapper for ALIGN-generated GDS.
#
# Injects an EdgeSeal ring (layer 39/0) around the top-cell bounding box,
# then calls the IHP production filler macros (ActGatP, Metal, TopMetal)
# via klayout batch mode.
#
# Usage:
#   sg13g2_fill.sh [--margin UM] [--no-activ] [--no-metal] [--no-topmetal]
#                  [--topcell NAME] <input.gds> <output.gds>
#
# Options:
#   --margin UM      EdgeSeal margin around bbox in micrometers (default: 5.0)
#   --no-activ       Skip Activ + GatPoly fill
#   --no-metal       Skip Metal1-5 fill
#   --no-topmetal    Skip TopMetal1-2 fill
#   --topcell NAME   Force top cell name (default: auto-detect)
#
# Requires:
#   IHP_PDK_ROOT  pointing at an IHP-Open-PDK clone (dev branch).
#   klayout       in PATH (>= 0.29.11).
#
# Note on density DRC:
#   Density rules (AFil.g, GFil.g, M1-M5.j, TM1.c, TM2.c) check minimum
#   metal/active coverage in 800x800um windows. ALIGN blocks are typically
#   much smaller (10-50um), so block-level density will not meet thresholds
#   even after fill insertion. Density compliance is a chip-level concern:
#   the integrator runs fill across the full die. This tool is useful for
#   chip-level flows and for validating that fill-cell geometry is legal.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILL_HELPER="$SCRIPT_DIR/_fill_helper.py"

MARGIN=5.0
NO_ACTIV=""
NO_METAL=""
NO_TOPMETAL=""
TOPCELL=""

usage() {
    sed -n '/^# IHP SG13G2 density-fill/,/^$/p' "$0" | sed 's/^# //;s/^#//'
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --margin) MARGIN="$2"; shift 2;;
        --no-activ) NO_ACTIV="yes"; shift;;
        --no-metal) NO_METAL="yes"; shift;;
        --no-topmetal) NO_TOPMETAL="yes"; shift;;
        --topcell) TOPCELL="$2"; shift 2;;
        -h|--help) usage;;
        --) shift; break;;
        -*) echo "unknown flag: $1" >&2; usage;;
        *) break;;
    esac
done

if [[ $# -ne 2 ]]; then
    echo "expected: <input.gds> <output.gds>" >&2
    usage
fi

INPUT_GDS="$1"
OUTPUT_GDS="$2"

if [[ ! -f "$INPUT_GDS" ]]; then
    echo "input GDS not found: $INPUT_GDS" >&2
    exit 2
fi

: "${IHP_PDK_ROOT:?IHP_PDK_ROOT must point at an IHP-Open-PDK clone}"

FILLER_PY="$IHP_PDK_ROOT/ihp-sg13g2/libs.tech/klayout/tech/scripts/filler.py"
if [[ ! -f "$FILLER_PY" ]]; then
    echo "filler.py not found at $FILLER_PY" >&2
    exit 2
fi
if [[ ! -f "$FILL_HELPER" ]]; then
    echo "fill helper not found at $FILL_HELPER" >&2
    exit 2
fi

ABS_INPUT=$(readlink -f "$INPUT_GDS")
mkdir -p "$(dirname "$OUTPUT_GDS")"
ABS_OUTPUT=$(cd "$(dirname "$OUTPUT_GDS")" && pwd)/$(basename "$OUTPUT_GDS")

export PDK_ROOT="$IHP_PDK_ROOT"
export PDK="ihp-sg13g2"

KLAYOUT_TECH_DIR="$IHP_PDK_ROOT/ihp-sg13g2/libs.tech/klayout"
export KLAYOUT_HOME=$(mktemp -d)
export KLAYOUT_PATH="$KLAYOUT_TECH_DIR"
trap 'rm -rf "$KLAYOUT_HOME" /tmp/_align_prefill_$$.gds' EXIT

STAGING="/tmp/_align_prefill_$$.gds"

echo ">> sg13g2_fill.sh: input=$ABS_INPUT output=$ABS_OUTPUT margin=${MARGIN}um"

# --- Step 1: Inject EdgeSeal ---
INJECT_ARGS=( -rd action=inject -rd input_file="$ABS_INPUT" -rd output_file="$STAGING" -rd margin="$MARGIN" )
[[ -n "$TOPCELL" ]] && INJECT_ARGS+=( -rd topcell="$TOPCELL" )
echo ">> step 1: injecting EdgeSeal"
klayout -b -r "$FILL_HELPER" "${INJECT_ARGS[@]}"

if [[ ! -f "$STAGING" ]]; then
    echo ">> ERROR: EdgeSeal injection failed" >&2
    exit 1
fi

# --- Step 2: Run IHP filler macros ---
FILLER_ARGS=( -rd output_file="$ABS_OUTPUT" )
[[ -n "$NO_ACTIV" ]]   && FILLER_ARGS+=( -rd no_activ )
[[ -n "$NO_METAL" ]]   && FILLER_ARGS+=( -rd no_metal )
[[ -n "$NO_TOPMETAL" ]] && FILLER_ARGS+=( -rd no_topmetal )

echo ">> step 2: running IHP filler macros"
klayout -n sg13g2 -zz -r "$FILLER_PY" "${FILLER_ARGS[@]}" "$STAGING"

if [[ ! -f "$ABS_OUTPUT" ]]; then
    echo ">> ERROR: filler did not produce output" >&2
    exit 1
fi

# --- Step 3: Strip synthetic EdgeSeal ---
STRIP_ARGS=( -rd action=strip -rd input_file="$ABS_OUTPUT" -rd output_file="$ABS_OUTPUT" )
[[ -n "$TOPCELL" ]] && STRIP_ARGS+=( -rd topcell="$TOPCELL" )
echo ">> step 3: stripping EdgeSeal from output"
klayout -b -r "$FILL_HELPER" "${STRIP_ARGS[@]}"

echo ">> fill complete: $ABS_OUTPUT"
