#!/usr/bin/env bash
set -euo pipefail

APP_ID="${FASTAPI_SAMPLE_APP_ID:-sample}"
CONTAINER="${FASTAPI_SAMPLE_CONTAINER:-fastapi-sample}"
SUBMODULE="${FASTAPI_SAMPLE_SUBMODULE:-fastapi-sample}"
REF="${FASTAPI_SAMPLE_REF:-master}"
OBSERVER_NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-sample-observer}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for command in git docker jq curl sudo midclt stat; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

REPO_OWNER="$(stat -c '%U' "${ROOT}")"

run_git() {
  if [[ "${EUID}" -eq 0 && "${REPO_OWNER}" != "root" ]]; then
    sudo -u "${REPO_OWNER}" -H -- "$@"
  else
    "$@"
  fi
}

run_git git submodule sync --recursive
run_git git submodule update --init --recursive "${SUBMODULE}"

if [[ -n "$(run_git git -C "${SUBMODULE}" status --porcelain --untracked-files=no)" ]]; then
  fail "${SUBMODULE} contains tracked local changes; refusing to overwrite them"
fi

before="$(run_git git -C "${SUBMODULE}" rev-parse HEAD)"
printf 'FastAPI Sample current revision: %s\n' "${before}"

run_git git -C "${SUBMODULE}" fetch --prune origin "${REF}"
target="$(run_git git -C "${SUBMODULE}" rev-parse "origin/${REF}")"

run_git git -C "${SUBMODULE}" checkout --detach "${target}"
run_git git -C "${SUBMODULE}" submodule update --init --recursive

printf 'FastAPI Sample target origin/%s: %s\n' "${REF}" "${target}"

docker compose   -f apps/sample/compose.yml   config   --quiet   --no-interpolate   --no-env-resolution

printf 'Building fastapi-sample before runtime replacement...\n'
docker compose   -f apps/sample/compose.yml   build   --pull   fastapi-sample

network_contract=""
if docker network inspect "${OBSERVER_NETWORK}" >/dev/null 2>&1; then
  network_contract="$(
    docker network inspect "${OBSERVER_NETWORK}" |
      jq -r '.[0].Labels["com.nabla.observer-contract"] // empty'
  )"
fi

if [[ -z "${network_contract}" ]]; then
  sudo bash scripts/truenas/prepare-sample-observer-network.sh
elif [[ "${network_contract}" != "v2" ]]; then
  printf 'Observer network contract is %s; recreating v2 safely.\n'     "${network_contract:-<missing>}"
  docker rm -f "${CONTAINER}" 2>/dev/null || true
  sudo bash scripts/truenas/prepare-sample-observer-network.sh --recreate
else
  sudo bash scripts/truenas/prepare-sample-observer-network.sh
fi

sudo bash   scripts/security/reconcile-truenas-observer-allowlist.sh   --apply

printf 'Removing the previous FastAPI Sample container after successful build...\n'
docker rm -f "${CONTAINER}" 2>/dev/null || true

compose_path="${ROOT}/apps/sample/compose.yml"

sudo midclt call -j app.update "${APP_ID}" "$(
  jq -cn     --arg include "${compose_path}"     '{
      custom_compose_config: {
        include: [$include]
      }
    }'
)"

sudo midclt call -j app.redeploy "${APP_ID}"

printf 'Waiting for FastAPI Sample health on :8091...\n'
curl -fsS   --retry 30   --retry-delay 2   --retry-connrefused   http://127.0.0.1:8091/health |
  jq .

printf 'FastAPI Sample version:\n'
curl -fsS   --retry 5   --retry-delay 1   http://127.0.0.1:8091/v2/version |
  jq .

bash scripts/security/verify-truenas-observer-access.sh

runtime_sha="$(run_git git -C "${SUBMODULE}" rev-parse HEAD)"
printf 'OK: FastAPI Sample origin/%s deployed from %s\n' "${REF}" "${runtime_sha}"

pinned_sha="$(run_git git ls-files -s "${SUBMODULE}" | awk '{print $2}')"
if [[ -n "${pinned_sha}" && "${pinned_sha}" != "${runtime_sha}" ]]; then
  printf 'NOTE: parent repository still pins %s; working tree now uses %s.\n'     "${pinned_sha}" "${runtime_sha}"
  printf '      Update the parent gitlink in a reviewed PR if this revision is promoted.\n'
fi
