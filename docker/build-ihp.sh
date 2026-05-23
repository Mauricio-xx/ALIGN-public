#!/usr/bin/env bash
# Build the ALIGN Docker image with IHP SG13G2 fixes baked in.
#
# This creates a thin overlay on top of darpaalign/align-public:latest,
# patching align/cmdline.py (Phase O --skipGDS fix). The PDK and examples
# are bind-mounted at runtime from the host repo.
#
# Usage:
#   ./docker/build-ihp.sh            # builds align-ihp:latest
#   ./docker/build-ihp.sh my-tag     # builds align-ihp:my-tag
#
# Run (use --user to avoid root-owned output files):
#   docker run --rm --user $(id -u):$(id -g) \
#     -v $PWD:/work -w /work align-ihp:latest \
#     schematic2layout.py examples/inverter_v1_sg13g2 \
#       -p pdks/IHP_SG13G2_PDK -w /work/.tmp_runs/output

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${1:-latest}"
IMAGE="align-ihp:${TAG}"

echo ">> building ${IMAGE} from ${REPO_ROOT}"
docker build -f "${REPO_ROOT}/docker/Dockerfile.ihp" -t "${IMAGE}" "${REPO_ROOT}"
echo ">> done: ${IMAGE}"
