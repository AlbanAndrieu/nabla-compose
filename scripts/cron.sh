#!/usr/bin/env bash
set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <repo-dir>" >&2
    exit 1
fi

REPO_DIR="$1"
COMPOSE_DIR="${REPO_DIR}/bootstrap"
LOG_TAG="doco-cd-update"

log_info() {
    echo "[${LOG_TAG}] $*"
    logger -t "$LOG_TAG" "$*"
}

log_error() {
    echo "[${LOG_TAG}] ERROR: $*" >&2
    logger -s -t "$LOG_TAG" "ERROR: $*"
}

cd "$REPO_DIR"

git fetch origin 2>/dev/null

LOCAL=$(git rev-parse HEAD)
log_info "Current local commit: ${LOCAL}"

REMOTE=$(git rev-parse @{u})
log_info "Current remote commit: ${REMOTE}"

if [ "$LOCAL" = "$REMOTE" ]; then
    log_info "No changes."
    exit 0
fi

git reset --hard "$REMOTE"

if git diff --quiet "${LOCAL}" HEAD -- bootstrap/; then
    log_info "Changes pulled but none in bootstrap/, skipping compose."
    exit 0
fi

log_info "Changes detected in bootstrap/, running docker compose up..."
cd "$COMPOSE_DIR"
docker compose up -d 2>/dev/null
if [ $? -ne 0 ]; then
    log_error "Failed to start containers with docker compose with new changes from upstream."
    exit 1
else
    log_info "Containers started successfully."
fi

log_info "Waiting for containers to be healthy..."
TIMEOUT=120
if timeout "$TIMEOUT" bash -c '
    while true; do
        if docker compose ps --format json | jq -e "select(.Health != \"\" and .Health != \"healthy\")" > /dev/null 2>&1; then
            sleep 5
        else
            break
        fi
    done
'; then
    log_info "All containers healthy."
else
    log_error "Containers not healthy after ${TIMEOUT}s"
    docker compose ps >&2
    exit 1
fi

docker compose ps 2>/dev/null
