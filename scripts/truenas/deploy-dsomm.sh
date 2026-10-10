#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP_ID="${DSOMM_APP_ID:-dsomm}"
CANONICAL_ROOT="${DSOMM_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
DSOMM_URL="${DSOMM_URL:-http://172.17.0.24:31088/}"
WAIT_SECONDS="${DSOMM_WAIT_SECONDS:-240}"
DSOMM_IMAGE="${DSOMM_IMAGE:-wurstbrot/dsomm:4.4.1}"
DSOMM_MODEL_VERSION="${DSOMM_MODEL_VERSION:-5.0.2}"
DSOMM_MODEL_REF="${DSOMM_MODEL_REF:-a2c1b7e6c7cc22de0d478027d76fd8d02c41fd7a}"
DSOMM_MODEL_URL="${DSOMM_MODEL_URL:-https://raw.githubusercontent.com/devsecopsmaturitymodel/DevSecOps-MaturityModel-data/${DSOMM_MODEL_REF}/generated/model.yaml}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash $0 [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo on TrueNAS"
for command in curl docker git grep install jq midclt mktemp python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical checkout ${CANONICAL_ROOT}; current=${ROOT}"
cd "${CANONICAL_ROOT}"

# shellcheck source=../lib/truenas.sh
source "${CANONICAL_ROOT}/scripts/lib/truenas.sh"
truenas_repo_provenance "$(git rev-parse --show-toplevel)"

# shellcheck source=../lib/probe.sh
source "${CANONICAL_ROOT}/scripts/lib/probe.sh"

compose_path="${CANONICAL_ROOT}/apps/dsomm/compose.yml"
progress_seed="${CANONICAL_ROOT}/apps/dsomm/config/team-progress.seed.yaml"
evidence_seed="${CANONICAL_ROOT}/apps/dsomm/config/team-evidence.seed.yaml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"
for seed_file in "${progress_seed}" "${evidence_seed}"; do
  [[ -f "${seed_file}" && ! -L "${seed_file}" ]] ||
    fail "missing or unsafe DSOMM seed file: ${seed_file}"
done

printf '==> DSOMM assessment seed contract\n'
python3 scripts/dsomm/validate-seed.py

printf '\n==> DSOMM frontend image contract\n'
if docker image inspect "${DSOMM_IMAGE}" >/dev/null 2>&1; then
  printf 'OK: DSOMM frontend image is already present locally: %s\n' "${DSOMM_IMAGE}"
elif docker manifest inspect "${DSOMM_IMAGE}" >/dev/null 2>&1; then
  printf 'OK: DSOMM frontend image exists in registry: %s\n' "${DSOMM_IMAGE}"
else
  fail "DSOMM frontend image is unavailable: ${DSOMM_IMAGE}; do not create/start the TrueNAS App with an unresolved tag"
fi

printf '\n==> DSOMM Compose contract\n'
DSOMM_IMAGE="${DSOMM_IMAGE}" docker compose -f "${compose_path}" --profile manual config \
  --quiet --no-interpolate --no-env-resolution

printf '\n==> generated service contracts\n'
python3 scripts/generate-service-topology.py --check
python3 scripts/generate-service-consumers.py --check

printf '\n==> DSOMM repository-owned storage\n'
bash scripts/truenas/bootstrap-repository-storage.sh "${MODE}" "${APP_ID}"

state_root="/mnt/cpool/dsomm/state"
progress_file="${state_root}/team-progress.yaml"
evidence_file="${state_root}/team-evidence.yaml"
model_file="${state_root}/model.yaml"

if [[ "${MODE}" == "--apply" ]]; then
  [[ ! -L "${state_root}" ]] ||
    fail "refusing symlinked DSOMM state directory: ${state_root}"
  install -d -m 0700 "${state_root}"
  [[ -d "${state_root}" && ! -L "${state_root}" ]] ||
    fail "unsafe DSOMM state directory: ${state_root}"
  umask 077

  model_tmp="$(mktemp "${state_root}/model.yaml.tmp.XXXXXX")"
  trap 'rm -f "${model_tmp:-}"' EXIT
  curl --fail --location --silent --show-error \
    --proto '=https' --tlsv1.2 \
    "${DSOMM_MODEL_URL}" -o "${model_tmp}"
  grep -Fq "version: ${DSOMM_MODEL_VERSION}" "${model_tmp}" ||
    fail "downloaded DSOMM model does not declare expected version ${DSOMM_MODEL_VERSION}"
  grep -Fq 'uuid:' "${model_tmp}" ||
    fail "downloaded DSOMM model contains no activity UUIDs"
  install -o root -g root -m 0600 "${model_tmp}" "${model_file}"
  rm -f "${model_tmp}"
  trap - EXIT
  printf 'Staged pinned DSOMM model %s from commit %s without following latest\n' \
    "${DSOMM_MODEL_VERSION}" "${DSOMM_MODEL_REF}"

  state_specs=(
    "progress|${progress_file}|${progress_seed}"
    "evidence|${evidence_file}|${evidence_seed}"
  )
  for state_spec in "${state_specs[@]}"; do
    IFS='|' read -r state_key state_file state_seed <<<"${state_spec}"
    [[ ! -L "${state_file}" ]] ||
      fail "refusing symlinked DSOMM state file: ${state_file}"
    if [[ ! -e "${state_file}" ]]; then
      printf 'Initializing DSOMM %s from reviewed repository seed\n' "${state_key}"
      install -m 0600 "${state_seed}" "${state_file}"
    elif [[ ! -f "${state_file}" ]]; then
      fail "DSOMM state path is not a regular file: ${state_file}"
    fi
    chmod 0600 "${state_file}"
  done
fi

for state_file in "${model_file}" "${progress_file}" "${evidence_file}"; do
  [[ -f "${state_file}" && ! -L "${state_file}" ]] ||
    fail "missing or unsafe DSOMM state file: ${state_file}; run --apply"
done

if [[ "${MODE}" == "--apply" ]]; then
  printf '\n==> DSOMM frontend image pull\n'
  docker pull "${DSOMM_IMAGE}" >/dev/null
  printf 'OK: DSOMM frontend image is local: %s\n' "${DSOMM_IMAGE}"

  printf '\n==> DSOMM direct container smoke\n'
  docker network inspect intranet >/dev/null 2>&1 ||
    fail "required external Docker network is missing: intranet"

  smoke_name="nabla-dsomm-preflight-${BASHPID}"
  cleanup_dsomm_smoke() {
    docker rm -f "${smoke_name}" >/dev/null 2>&1 || true
  }
  trap cleanup_dsomm_smoke EXIT

  # Keep an exited smoke container until its logs have been collected.
  # The EXIT trap removes it after both successful and failed diagnostics.
  docker run -d \
    --name "${smoke_name}" \
    --network intranet \
    --cap-drop ALL \
    --cap-add NET_BIND_SERVICE \
    --security-opt no-new-privileges=true \
    --mount "type=bind,src=${CANONICAL_ROOT}/apps/dsomm/config/meta.yaml,dst=/srv/assets/YAML/meta.yaml,readonly" \
    --mount "type=bind,src=${model_file},dst=/srv/assets/YAML/default/model.yaml,readonly" \
    --mount "type=bind,src=${progress_file},dst=/srv/assets/YAML/team-progress.yaml,readonly" \
    --mount "type=bind,src=${evidence_file},dst=/srv/assets/YAML/team-evidence.yaml,readonly" \
    "${DSOMM_IMAGE}" >/dev/null

  smoke_ready=false
  for ((attempt = 1; attempt <= 20; attempt++)); do
    if docker exec "${smoke_name}" wget -q --spider http://127.0.0.1:8080/; then
      smoke_ready=true
      break
    fi
    running="$(docker inspect -f '{{.State.Running}}' "${smoke_name}" 2>/dev/null || printf 'false')"
    [[ "${running}" == "true" ]] || break
    sleep 1
  done

  if [[ "${smoke_ready}" != true ]]; then
    printf 'ERROR: direct DSOMM container smoke failed; container status and recent logs follow.\n' >&2
    docker inspect --format 'status={{.State.Status}} exit_code={{.State.ExitCode}} error={{.State.Error}}' \
      "${smoke_name}" >&2 2>/dev/null || true
    docker logs --tail 80 "${smoke_name}" >&2 2>/dev/null || true
    fail "DSOMM image/mount/security contract failed before TrueNAS reconciliation"
  fi
  printf 'OK: DSOMM image starts with the repository mounts/security posture outside TrueNAS App orchestration\n'
  cleanup_dsomm_smoke
  trap - EXIT

  printf '\n==> render DSOMM runtime Compose for TrueNAS\n'
  runtime_compose_json="$(
    NABLA_COMPOSE_ROOT="${CANONICAL_ROOT}" DSOMM_IMAGE="${DSOMM_IMAGE}" \
      docker compose -f "${compose_path}" config --format json |
      jq -c '
        {
          services: {
            dsomm: (.services.dsomm | del(.["x-nabla"]))
          },
          networks: {
            intranet: .networks.intranet
          }
        }
      '
  )"
  jq -e '
    .services.dsomm.image != null
    and .services.dsomm.ports != null
    and .networks.intranet != null
  ' <<<"${runtime_compose_json}" >/dev/null ||
    fail "rendered DSOMM runtime Compose is incomplete"
  printf 'OK: rendered one-service DSOMM Compose for TrueNAS Custom App\n'

  printf '\n==> TrueNAS Custom App reconciliation\n'
  lifecycle_mark="$(truenas_lifecycle_mark)"
  if truenas_app_query_by_id "${APP_ID}" | jq -e 'length == 1' >/dev/null; then
    payload="$(jq -cn --argjson compose "${runtime_compose_json}" '{
      custom_compose_config: $compose
    }')"
    truenas_job_compact app.update "${APP_ID}" "${payload}"
  else
    payload="$(jq -cn --arg app_name "${APP_ID}" --arg compose "${runtime_compose_json}" '{
      app_name: $app_name,
      custom_app: true,
      custom_compose_config_string: $compose
    }')"
    truenas_job_compact app.create "${payload}"
  fi

  state="$(truenas_app_state "${APP_ID}")"
  if [[ "${state}" == "STOPPED" ]]; then
    printf 'Starting DSOMM Custom App after configuration reconciliation...\n'
    truenas_job_compact app.start "${APP_ID}"
    state="$(truenas_app_state "${APP_ID}")"
    if [[ "${state}" == "STOPPED" ]]; then
      printf 'ERROR: DSOMM app.start completed but the App returned to STOPPED.\n' >&2
      truenas_lifecycle_errors_since "${APP_ID}" "${lifecycle_mark}" 40 || true
      printf '%s\n' 'Recent DSOMM lifecycle jobs (arguments intentionally omitted):' >&2
      midclt call core.get_jobs |
        jq --arg app "${APP_ID}" '
          [
            .[]
            | select(.method == "app.create" or .method == "app.update" or .method == "app.start")
            | select(
                (.arguments[0]? == $app)
                or ((.arguments[0]? | type) == "object" and .arguments[0].app_name? == $app)
              )
            | {
                id,
                method,
                state,
                error,
                description,
                logs_excerpt
              }
          ]
          | sort_by(.id)
          | reverse
          | .[:5]
        ' >&2 || true
      fail "DSOMM returned to STOPPED immediately after app.start; inspect bounded lifecycle evidence above"
    fi
  fi
fi

state="$(truenas_app_state "${APP_ID}")"
[[ "${state}" != "MISSING" ]] ||
  fail "${APP_ID}: TrueNAS Custom App is not registered; run --apply"
# A read-only --check cannot start a STOPPED App. Do not wait for the
# entire readiness timeout when there is no active startup to observe.
if [[ "${MODE}" == "--check" && "${state}" == "STOPPED" ]]; then
  fail "${APP_ID}: TrueNAS App is STOPPED; --check cannot start it. Review the direct-smoke/runtime preconditions before --apply."
fi

printf '\n==> wait for DSOMM runtime\n'
truenas_wait_app_running "${APP_ID}" "${WAIT_SECONDS}" 4

if probe_http_wait "${DSOMM_URL}" "${WAIT_SECONDS}" 4 3 8; then
  printf 'OK: DSOMM HTTP ready: %s\n' "${DSOMM_URL}"
  printf '%s%s\n' \
    'INFO: x-nabla.status remains planned until runtime acceptance is reviewed ' \
    'and committed as active.'
  exit 0
fi

fail "DSOMM HTTP endpoint did not become ready within ${WAIT_SECONDS}s: ${DSOMM_URL}"
