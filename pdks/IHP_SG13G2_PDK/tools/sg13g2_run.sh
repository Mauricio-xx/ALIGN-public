#!/usr/bin/env bash
# End-to-end mixed-signal P&R for IHP SG13G2 with automatic blackbox GDS.
#
# Usage:
#   sg13g2_run.sh <design_dir> [-w WORKDIR] [-- extra schematic2layout args]
#
# Requirements:
#   - Docker image align-ihp:latest (built via docker/build-ihp.sh)
#   - klayout >= 0.30.2 in PATH or KLAYOUT_BIN
#   - IHP_PDK_ROOT pointing at an IHP-Open-PDK clone (dev branch)
#
# The script performs a two-pass flow:
#   Pass 1: run compiler to discover blackbox primitive names
#   Pass 2: generate blackbox GDS on host, then run full P&R in Docker
#
# For pure MOS circuits (no BJTs/resistors/caps), only one pass is needed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
GEN_BB="$SCRIPT_DIR/gen_all_blackboxes.py"
DOCKER_IMAGE="${ALIGN_DOCKER_IMAGE:-align-ihp:latest}"

usage() {
    echo "Usage: sg13g2_run.sh <design_dir> [-w WORKDIR] [-- extra args]"
    echo ""
    echo "  <design_dir>  directory containing the .sp netlist"
    echo "  -w WORKDIR    output directory (default: .tmp_runs/<design_name>)"
    echo "  --            extra arguments passed to schematic2layout"
    exit 2
}

[[ $# -lt 1 ]] && usage

DESIGN_DIR="$1"; shift
WORKDIR=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -w) WORKDIR="$2"; shift 2;;
        --) shift; EXTRA_ARGS=("$@"); break;;
        -h|--help) usage;;
        *) EXTRA_ARGS+=("$1"); shift;;
    esac
done

DESIGN_NAME="$(basename "$DESIGN_DIR")"
[[ -z "$WORKDIR" ]] && WORKDIR="$REPO_ROOT/.tmp_runs/${DESIGN_NAME}"

: "${IHP_PDK_ROOT:?IHP_PDK_ROOT must point at an IHP-Open-PDK clone}"
: "${KLAYOUT_BIN:=$(command -v klayout || echo /usr/bin/klayout)}"
export KLAYOUT_BIN

# Overlay files for the Docker container
OVERLAYS=(
    -v "$REPO_ROOT/align/pnr/main.py:/usr/local/lib/python3.10/dist-packages/align/pnr/main.py:ro"
    -v "$REPO_ROOT/align/pnr/placer.py:/usr/local/lib/python3.10/dist-packages/align/pnr/placer.py:ro"
    -v "$REPO_ROOT/align/pnr/router.py:/usr/local/lib/python3.10/dist-packages/align/pnr/router.py:ro"
    -v "$REPO_ROOT/align/schema/library.py:/usr/local/lib/python3.10/dist-packages/align/schema/library.py:ro"
    -v "$REPO_ROOT/align/compiler/gen_abstract_name.py:/usr/local/lib/python3.10/dist-packages/align/compiler/gen_abstract_name.py:ro"
    -v "$REPO_ROOT/align/cell_fabric/remove_duplicates.py:/usr/local/lib/python3.10/dist-packages/align/cell_fabric/remove_duplicates.py:ro"
)

has_blackbox_models() {
    grep -E -iq '\b(npn13g2l?v?|pnpmpa|rsil|rppd|rhigh|cap_cmim|rfcmim|inductor[23s]?)\b' "$1"
}

find_spice() {
    local dir="$1"
    local sp
    sp=$(find "$dir" -maxdepth 1 -name '*.sp' ! -name '*.lvs.sp' | head -1)
    echo "$sp"
}

run_docker() {
    local workdir="$1"; shift
    local bbox_args=()
    [[ -n "${BBOX_DIR:-}" ]] && bbox_args=(--blackbox_dir /bbox)
    local bbox_mount=()
    [[ -n "${BBOX_DIR:-}" ]] && bbox_mount=(-v "$BBOX_DIR:/bbox:ro")

    # Resolve DESIGN_DIR: if inside REPO_ROOT, convert to relative path for
    # Docker (REPO_ROOT is /work inside the container). Otherwise mount it.
    local design_mount=()
    local docker_design_dir
    local abs_design
    abs_design="$(cd "$DESIGN_DIR" && pwd)"
    if [[ "$abs_design" == "$REPO_ROOT"* ]]; then
        docker_design_dir="${abs_design#"$REPO_ROOT"/}"
    elif [[ "$abs_design" == "$workdir"* ]]; then
        docker_design_dir="$abs_design"
    else
        design_mount=(-v "$abs_design:$abs_design:ro")
        docker_design_dir="$abs_design"
    fi

    rm -rf "$workdir"
    mkdir -p "$workdir/LOG"
    docker run --rm \
        --user "$(id -u):$(id -g)" \
        -v "$REPO_ROOT:/work" -w /work \
        "${bbox_mount[@]}" \
        "${design_mount[@]}" \
        -v "$workdir:$workdir" \
        "${OVERLAYS[@]}" \
        -e ALIGN_WORK_DIR="$workdir" \
        "$DOCKER_IMAGE" \
        schematic2layout.py "$docker_design_dir" \
            -p pdks/IHP_SG13G2_PDK \
            -w "$workdir" \
            "${bbox_args[@]}" \
            "${EXTRA_ARGS[@]}" \
            "$@" 2>&1
}

SP_FILE="$(find_spice "$DESIGN_DIR")"
[[ -z "$SP_FILE" ]] && { echo "No .sp file found in $DESIGN_DIR" >&2; exit 2; }

if has_blackbox_models "$SP_FILE"; then
    echo ">> Mixed-signal circuit detected. Running two-pass flow."

    # Pass 1: compiler only (will fail at PnR but topology is generated)
    PASS1_DIR="${WORKDIR}_pass1"
    echo ">> Pass 1: discovering blackbox primitives..."
    run_docker "$PASS1_DIR" || true

    if [[ ! -f "$PASS1_DIR/1_topology/__primitives_library__.json" ]]; then
        echo "ERROR: Pass 1 did not produce topology output" >&2
        exit 1
    fi

    # Generate blackbox GDS from topology output
    BBOX_DIR="${WORKDIR}_bbox"
    echo ">> Generating blackbox GDS files..."
    python3 "$GEN_BB" "$PASS1_DIR/1_topology" --out "$BBOX_DIR"

    # Pass 2: full flow with blackbox GDS
    echo ">> Pass 2: full P&R with blackbox GDS..."
    export BBOX_DIR
    run_docker "$WORKDIR"
else
    echo ">> Pure MOS circuit. Single-pass flow."
    BBOX_DIR="" run_docker "$WORKDIR"
fi

echo ""
echo ">> Output: $WORKDIR"
GDS_FILE=$(find "$WORKDIR" -maxdepth 1 -name '*.gds' ! -name '*.python.gds' | head -1)
[[ -n "$GDS_FILE" ]] && echo ">> GDS: $GDS_FILE"
