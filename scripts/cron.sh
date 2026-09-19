#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${1:-}" ]]; then
  echo "Usage: $0 <repo-dir>" >&2
  exit 1
fi

REPO_DIR="$1"
COMPOSE_DIR="${REPO_DIR}/bootstrap"
DEPLOY_BRANCH="${NABLA_CRON_BRANCH:-master}"
LOCK_FILE="${NABLA_CRON_LOCK_FILE:-/tmp/nabla-compose-doco-cd-update.lock}"
LOG_TAG="doco-cd-update"

log_info() {
  echo "[${LOG_TAG}] $*"
  logger -t "${LOG_TAG}" "$*"
}

log_error() {
  echo "[${LOG_TAG}] ERROR: $*" >&2
  logger -s -t "${LOG_TAG}" "ERROR: $*"
}

for command in git docker jq logger timeout flock; do
  command -v "${command}" >/dev/null 2>&1 || {
    log_error "${command} is required"
    exit 1
  }
done

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  log_info "Another cron/bootstrap reconciliation is already running; skipping."
  exit 0
fi

cd "${REPO_DIR}"

CURRENT_BRANCH="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [[ "${CURRENT_BRANCH}" != "${DEPLOY_BRANCH}" ]]; then
  log_info "Checkout is on ${CURRENT_BRANCH:-detached}, not ${DEPLOY_BRANCH}; skipping local self-update. Doco-CD remote polling remains independent."
  exit 0
fi

# Protect tracked superproject edits. Dirty/unpinned submodule working trees are
# deliberately ignored here: cron owns the deployment checkout metadata, not
# developer changes inside submodule directories.
if ! git diff --quiet --ignore-submodules=all ||
  ! git diff --cached --quiet --ignore-submodules=all; then
  log_error "Tracked superproject changes are present; refusing automatic update."
  exit 1
fi

git fetch origin "${DEPLOY_BRANCH}" 2>/dev/null
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/${DEPLOY_BRANCH}")"
log_info "Current local commit: ${LOCAL}"
log_info "Current remote ${DEPLOY_BRANCH} commit: ${REMOTE}"

if [[ "${LOCAL}" == "${REMOTE}" ]]; then
  log_info "No changes."
  exit 0
fi

if ! git merge-base --is-ancestor "${LOCAL}" "${REMOTE}"; then
  log_error "Local ${DEPLOY_BRANCH} is not a fast-forward ancestor of origin/${DEPLOY_BRANCH}; refusing destructive reset."
  exit 1
fi

git merge --ff-only "origin/${DEPLOY_BRANCH}"

if git diff --quiet "${LOCAL}" HEAD -- bootstrap/; then
  log_info "Changes pulled but none in bootstrap/, skipping Doco-CD bootstrap compose."
  exit 0
fi

log_info "Changes detected in bootstrap/, validating and reconciling Doco-CD bootstrap stack..."
cd "${COMPOSE_DIR}"
docker compose config --quiet

if ! docker compose up -d; then
  log_error "Failed to reconcile Doco-CD bootstrap containers."
  exit 1
fi
log_info "Doco-CD bootstrap containers reconciled successfully."

log_info "Waiting for bootstrap containers to be healthy..."
TIMEOUT=120
if timeout "${TIMEOUT}" bash -c '
    while true; do
        if docker compose ps --format json | jq -e "select(.Health != \"\" and .Health != \"healthy\")" >/dev/null 2>&1; then
            sleep 5
        else
            break
        fi
    done
'; then
  log_info "All bootstrap containers healthy."
else
  log_error "Bootstrap containers not healthy after ${TIMEOUT}s"
  docker compose ps >&2
  exit 1
fi

docker compose ps
