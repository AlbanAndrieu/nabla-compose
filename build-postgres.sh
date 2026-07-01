#!/usr/bin/env bash
# shellcheck shell=bash

set -euo pipefail

WORKING_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/scripts/step-0-color.sh"

# shellcheck source=/dev/null
source "${WORKING_DIR}/scripts/step-1-os.sh"

echo "Building postgres-plpython3u"
docker compose build postgres

cd pgwatch/docker
./build-docker.sh

cd "${WORKING_DIR}"

exit 0
