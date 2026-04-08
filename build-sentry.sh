#!/bin/bash
#set -xv

WORKING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${WORKING_DIR}/scripts/step-0-color.sh"

# shellcheck source=/dev/null
source "${WORKING_DIR}/scripts/step-1-os.sh"


VERSION="24.12.0"
V4_PREFIX=10.100.10

# git clone https://github.com/getsentry/self-hosted.git
# cd self-hosted
# git checkout ${VERSION}

cd sentry

docker buildx rm local-builder || true
docker network rm build || true
docker network create --subnet $V4_PREFIX.0/24 --gateway $V4_PREFIX.1 --ip-range $V4_PREFIX.128/25 build
docker buildx create --name local-builder --driver docker-container --driver-opt network=build --use

./install.sh

cd "${WORKING_DIR}"

docker compose build web

docker buildx use default
docker compose build sentry-cleanup

exit 0
