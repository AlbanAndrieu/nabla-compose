#!/usr/bin/env bash
set -euo pipefail

APP_ID="${FASTAPI_SAMPLE_APP_ID:-sample}"
CONTAINER="${FASTAPI_SAMPLE_CONTAINER:-fastapi-sample}"
SUBMODULE="${FASTAPI_SAMPLE_SUBMODULE:-fastapi-sample}"
REF="${FASTAPI_SAMPLE_REF:-master}"
OBSERVER_NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-sample-observer}"
DEPLOY_MODE="${FASTAPI_SAMPLE_DEPLOY_MODE:-auto}"
IMAGE_REPOSITORY="${FASTAPI_SAMPLE_IMAGE_REPOSITORY:-ghcr.io/albanandrieu/fastapi-sample}"
REFRESH_BASE_IMAGES="${FASTAPI_SAMPLE_REFRESH_BASE_IMAGES:-false}"
VERBOSE_LOGS="${FASTAPI_SAMPLE_VERBOSE_LOGS:-false}"
# Guard registry traffic after Docker Hub 429; no automatic pull/build retries.
DOCKERHUB_COOLDOWN_SECONDS="${FASTAPI_SAMPLE_DOCKERHUB_COOLDOWN_SECONDS:-21600}"
ALLOW_ANONYMOUS_BASE_PULL="${FASTAPI_SAMPLE_ALLOW_ANONYMOUS_BASE_PULL:-false}"
OVERRIDE_DOCKERHUB_COOLDOWN="${FASTAPI_SAMPLE_OVERRIDE_DOCKERHUB_COOLDOWN:-false}"
DOCKERHUB_RATE_STATE_DIR="${FASTAPI_SAMPLE_DOCKERHUB_RATE_STATE_DIR:-${XDG_STATE_HOME:-${HOME}/.local/state}/nabla/fastapi-sample}"
DOCKERHUB_RATE_MARKER="${DOCKERHUB_RATE_STATE_DIR}/dockerhub-429"
BUILD_LOG_TAIL="${FASTAPI_SAMPLE_BUILD_LOG_TAIL:-80}"
DEPLOY_LOG_TAIL="${FASTAPI_SAMPLE_DEPLOY_LOG_TAIL:-40}"
CANONICAL_ENV_ROOT="${FASTAPI_SAMPLE_ENV_ROOT:-/mnt/cpool/secrets/runtime/sample}"
LEGACY_ENV_ROOT="${FASTAPI_SAMPLE_LEGACY_ENV_ROOT:-/mnt/cpool/sample}"

# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"
# Common color/icon status presentation. No ANSI for redirected output.
# shellcheck source=../lib/diagnostic-ui.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/diagnostic-ui.sh"
diag_ui_init "${FASTAPI_SAMPLE_COLOR:-auto}" "${FASTAPI_SAMPLE_ICONS:-auto}"

for command in git docker jq curl sudo midclt stat awk grep mktemp tee cmp; do
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

if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
else
    DOCKER=(sudo docker)
fi

run_docker() {
    "${DOCKER[@]}" "$@"
}

step() { diag_section "$1" "$2"; }
summary_ok() { diag_ok "$*"; }
summary_warn() { diag_warn "$*"; }

# Keep success output short; retain a bounded diagnostic only on failure.
quiet_step() {
    local label="$1" log rc
    shift
    log="$(mktemp)"
    if "$@" >"${log}" 2>&1; then
        summary_ok "${label}"
        rm -f -- "${log}"
        return 0
    else
        rc=$?
    fi
    diag_fail "${label} (exit=${rc})"
    # Ordinary errors sometimes contain bearer values or internal URLs.
    # Only an explicit private diagnostic session should retain raw output.
    # Do not dump the arbitrary subprocess log to interactive stdout.
    diag_info "Private failure evidence: ${log} (0600; may contain credentials)"
    return "${rc}"
}

case "${DEPLOY_MODE}" in
    auto | pull | build) ;;
    *) fail "FASTAPI_SAMPLE_DEPLOY_MODE must be one of: auto, pull, build" ;;
esac

case "${REFRESH_BASE_IMAGES}" in
    true | false) ;;
    *) fail "FASTAPI_SAMPLE_REFRESH_BASE_IMAGES must be true or false" ;;
esac

case "${VERBOSE_LOGS}" in
    true | false) ;;
    *) fail "FASTAPI_SAMPLE_VERBOSE_LOGS must be true or false" ;;
esac

for value in "${ALLOW_ANONYMOUS_BASE_PULL}" "${OVERRIDE_DOCKERHUB_COOLDOWN}"; do
    [[ "${value}" == true || "${value}" == false ]] ||
        fail 'FASTAPI_SAMPLE_ALLOW_ANONYMOUS_BASE_PULL and FASTAPI_SAMPLE_OVERRIDE_DOCKERHUB_COOLDOWN must be true or false'
done
[[ "${DOCKERHUB_COOLDOWN_SECONDS}" =~ ^[0-9]{1,5}$ ]] &&
    ((DOCKERHUB_COOLDOWN_SECONDS >= 60 && DOCKERHUB_COOLDOWN_SECONDS <= 86400)) ||
    fail 'FASTAPI_SAMPLE_DOCKERHUB_COOLDOWN_SECONDS must be 60..86400'

[[ "${BUILD_LOG_TAIL}" =~ ^[1-9][0-9]*$ ]] ||
    fail "FASTAPI_SAMPLE_BUILD_LOG_TAIL must be a positive integer"
[[ "${DEPLOY_LOG_TAIL}" =~ ^[1-9][0-9]*$ ]] ||
    fail "FASTAPI_SAMPLE_DEPLOY_LOG_TAIL must be a positive integer"

verify_runtime_env_file() {
    local path="$1"
    local label="$2"
    local metadata

    sudo test -f "${path}" ||
        fail "${label} is missing: ${path}; stage it before redeploying Sample"
    sudo test -s "${path}" ||
        fail "${label} is empty: ${path}; refusing to deploy with an empty runtime file"

    metadata="$(sudo stat -c '%U:%G %a' "${path}")"
    [[ "${metadata}" == "root:root 600" ]] ||
        fail "${label} owner/mode=${metadata}; expected root:root 600"
}

verify_runtime_env_pair() {
    local name="$1"
    local canonical="${CANONICAL_ENV_ROOT}/${name}"
    local legacy="${LEGACY_ENV_ROOT}/${name}"

    verify_runtime_env_file "${canonical}" "Sample canonical ${name}"

    if sudo test -f "${legacy}"; then
        sudo cmp -s "${legacy}" "${canonical}" ||
            fail "Sample ${name} changed after staging: ${legacy} differs from ${canonical}; restage before redeploy"
        summary_ok "Canonical Sample ${name} matches legacy copy"
    fi
}

step '1/6' 'Validate runtime secrets'
# docker system prune can remove stopped staging containers and unused networks.
# A clean build cannot guarantee restoration of a container that was pruned.
if existing_container_state="$(run_docker inspect "${CONTAINER}" --format '{{.State.Status}}' 2>/dev/null)"; then
    [[ "${existing_container_state}" == running ]] ||
        summary_warn "FastAPI staging container is ${existing_container_state}; previous runtime is not confirmed running."
else
    summary_warn "FastAPI staging container not found; docker system prune may have removed it."
fi

verify_runtime_env_pair ".env"
verify_runtime_env_pair ".env.secrets"

wait_for_json_endpoint() {
    local label="$1"
    local url="$2"
    local attempts="${3:-90}"
    local delay="${4:-2}"
    local body
    local state
    local attempt

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if body="$(curl --fail --silent --max-time 5 "${url}" 2>/dev/null)" &&
            jq -e . >/dev/null 2>&1 <<<"${body}"; then
            printf '%s\n' "${body}"
            return 0
        fi

        if ((attempt == 1 || attempt % 30 == 0)); then
            state="$(
                sudo midclt call app.query \
                    "[[\"id\",\"=\",\"${APP_ID}\"]]" 2>/dev/null |
                    jq -r '.[0].state // "UNKNOWN"' 2>/dev/null ||
                    printf 'UNKNOWN'
            )"
            printf '  %s not ready yet (%d/%d, TrueNAS=%s)\n' \
                "${label}" "${attempt}" "${attempts}" "${state}" >&2

            if [[ "${state}" == "CRASHED" || "${state}" == "STOPPED" ]]; then
                break
            fi
        fi

        sleep "${delay}"
    done

    printf 'ERROR: %s did not become ready: %s\n' "${label}" "${url}" >&2
    sudo midclt call app.query \
        "[[\"id\",\"=\",\"${APP_ID}\"]]" 2>/dev/null |
        jq '.[0] | {id,state,active_workloads}' >&2 || true

    run_docker inspect "${CONTAINER}" \
        --format 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} exit={{.State.ExitCode}} error={{.State.Error}}' \
        >&2 2>/dev/null || true
    run_docker logs --tail 80 "${CONTAINER}" >&2 2>/dev/null || true
    return 1
}

verify_prometheus_observer_contract() {
    local prometheus_url
    local payload
    local gatus_up
    local service_samples

    prometheus_url="$(
        # shellcheck disable=SC2016 # expansion happens inside the container
        run_docker exec "${CONTAINER}" sh -lc \
            'printf "%s" "${HOMELAB_PROMETHEUS_URL:-}"' 2>/dev/null || true
    )"
    if [[ -z "${prometheus_url}" ]]; then
        printf 'WARN: HOMELAB_PROMETHEUS_URL is unset in the FastAPI runtime; Gatus synthetic evidence cannot be accepted yet.\n' >&2
        return 1
    fi

    if ! payload="$(
        run_docker exec "${CONTAINER}" curl \
            --fail \
            --silent \
            --show-error \
            --max-time 5 \
            --get \
            --data-urlencode \
            'query=nabla:telemetry:gatus_up or nabla:service:synthetic_probe_success' \
            "${prometheus_url%/}/api/v1/query" 2>/dev/null
    )"; then
        printf 'WARN: FastAPI runtime cannot query the configured Prometheus endpoint; keeping Gatus evidence shadow-only.\n' >&2
        return 1
    fi

    if ! jq -e \
        '.status == "success" and .data.resultType == "vector"' \
        >/dev/null <<<"${payload}"; then
        printf 'WARN: Prometheus returned an invalid instant-vector response; keeping Gatus evidence shadow-only.\n' >&2
        return 1
    fi

    gatus_up="$(
        jq -r \
            '[.data.result[] | select(.metric.__name__ == "nabla:telemetry:gatus_up") | .value[1]] | first // "missing"' \
            <<<"${payload}"
    )"
    service_samples="$(
        jq -r \
            '[.data.result[] | select(.metric.__name__ == "nabla:service:synthetic_probe_success")] | length' \
            <<<"${payload}"
    )"

    if ! jq -e \
        '[.data.result[]
          | select(.metric.__name__ == "nabla:telemetry:gatus_up")
          | .value[1]
          | tonumber] | any(. >= 1)' \
        >/dev/null <<<"${payload}" ||
        [[ "${service_samples}" -lt 1 ]]; then
        printf 'WARN: Prometheus is reachable but Gatus is not UP or no service samples exist; keeping Gatus evidence shadow-only.\n' >&2
        return 1
    fi

    printf 'OK: Prometheus/Gatus observer contract reachable from FastAPI runtime (gatus_up=%s synthetic_samples=%s).\n' \
        "${gatus_up}" "${service_samples}"
}

# Local state only, never Docker daemon settings. A 429 cannot be fixed by
# pruning BuildKit cache: do not retry until expiry or explicit operator override.
dockerhub_cooldown_active() {
    local started now owner mode
    [[ -e "${DOCKERHUB_RATE_MARKER}" || -L "${DOCKERHUB_RATE_MARKER}" ]] || return 1
    [[ -f "${DOCKERHUB_RATE_MARKER}" && ! -L "${DOCKERHUB_RATE_MARKER}" ]] ||
        fail "Unsafe Docker Hub cooldown marker; refusing registry traffic"
    owner="$(stat -c '%u' "${DOCKERHUB_RATE_MARKER}")"
    mode="$(stat -c '%a' "${DOCKERHUB_RATE_MARKER}")"
    [[ "${owner}" == "$(id -u)" && "${mode}" == 600 ]] ||
        fail "Unsafe Docker Hub cooldown marker ownership/mode"
    IFS= read -r started <"${DOCKERHUB_RATE_MARKER}" || true
    [[ "${started:-}" =~ ^[0-9]{10,12}$ ]] ||
        fail "Invalid Docker Hub cooldown marker"
    now="$(date +%s)"
    (( now < started + DOCKERHUB_COOLDOWN_SECONDS ))
}

record_dockerhub_429() {
    local tempfile
    (umask 077; mkdir -p -- "${DOCKERHUB_RATE_STATE_DIR}") ||
        fail "Could not prepare private Docker Hub cooldown directory"
    [[ -d "${DOCKERHUB_RATE_STATE_DIR}" && ! -L "${DOCKERHUB_RATE_STATE_DIR}" ]] ||
        fail "Unsafe Docker Hub cooldown directory"
    tempfile="$(mktemp "${DOCKERHUB_RATE_STATE_DIR}/.dockerhub-429.XXXXXX")" ||
        fail "Could not create private Docker Hub cooldown marker"
    printf '%s\n' "$(date +%s)" >"${tempfile}"
    mv -f -T -- "${tempfile}" "${DOCKERHUB_RATE_MARKER}"
    summary_warn "Docker Hub HTTP 429: cooldown saved locally; no automatic retry or container replacement attempted."
}

dockerhub_429_in_log() {
    local classification
    [[ -f scripts/truenas/classify-fastapi-build-failure.py ]] || return 1
    classification="$(python3 scripts/truenas/classify-fastapi-build-failure.py \
        --check --failure-shape --log "$1" 2>/dev/null)" || return 1
    jq -e '.registry_provider == "docker_hub" and .registry_http_status == 429' \
        >/dev/null 2>&1 <<<"${classification}"
}

# Check only a Docker Hub credential declaration in the selected client context.
# Never print credential bytes. Credential helpers may still be unavailable.
dockerhub_client_auth_configured() {
    local filter
    filter='
      (((.auths // {}) | to_entries) |
       any(.[]; (.key | test("index[.]docker[.]io|registry-1[.]docker[.]io|docker[.]io"; "i"))
           and ([.value.auth // "", .value.identitytoken // "", .value.identityToken // ""] | any(.[]; length > 0))))
      or (((.credHelpers // {}) | keys) |
       any(.[]; test("index[.]docker[.]io|registry-1[.]docker[.]io|docker[.]io"; "i")))
      or ((.credsStore // "") | length > 0)
    '
    if [[ "${DOCKER[0]}" == sudo ]]; then
        # Resolve the selected sudo client's HOME instead of assuming /root.
        sudo -H sh -c 'test -s "$HOME/.docker/config.json" &&
            jq -e "$1" "$HOME/.docker/config.json" >/dev/null 2>&1' sh "${filter}"
    else
        local config="${DOCKER_CONFIG:-${HOME}/.docker}/config.json"
        [[ -s "${config}" ]] &&
            jq -e "${filter}" "${config}" >/dev/null 2>&1
    fi
}

guard_dockerhub_base_build() {
    run_docker info >/dev/null 2>&1 ||
        fail "Docker daemon unavailable in selected build client; no build attempted"
    if dockerhub_cooldown_active; then
        if [[ "${OVERRIDE_DOCKERHUB_COOLDOWN}" != true ]]; then
            fail "Docker Hub 429 cooldown active: refusing remote image resolution. Check registry quota/anti-abuse; set FASTAPI_SAMPLE_OVERRIDE_DOCKERHUB_COOLDOWN=true only after remediation."
        fi
        summary_warn "Operator explicitly overrides Docker Hub 429 cooldown (single build only)."
    fi
    if [[ "${REFRESH_BASE_IMAGES}" == false ]] &&
        run_docker image inspect python:3.13-slim-trixie >/dev/null 2>&1; then
        summary_ok "Python Docker base image present in selected daemon cache"
    elif dockerhub_client_auth_configured; then
        summary_warn "Python base image absent; a Docker Hub credential declaration exists but authentication is NOT verified."
    elif [[ "${ALLOW_ANONYMOUS_BASE_PULL}" == true ]]; then
        summary_warn "Anonymous Docker Hub base image access explicitly allowed; rate limits may recur."
    else
        fail "Python base image absent and selected Docker client has no Docker Hub credential declaration; refusing anonymous Docker Hub request. Authenticate the selected client or explicitly set FASTAPI_SAMPLE_ALLOW_ANONYMOUS_BASE_PULL=true."
    fi
    if [[ "${REFRESH_BASE_IMAGES}" == true ]]; then
        summary_warn "Base-image refresh requested; additional registry requests may count toward quota."
    fi
}

# A 429 from a release registry must not trigger another pull via local build.
RELEASE_PULL_RATE_LIMITED=false
run_release_image_pull() {
    local image="$1" log
    RELEASE_PULL_RATE_LIMITED=false
    log="$(mktemp)"
    if run_docker pull "${image}" >"${log}" 2>&1; then
        rm -f -- "${log}"
        return 0
    fi
    if grep -Eiq '(^|[^0-9])429([^0-9]|$)|too many requests|toomanyrequests|pull rate limit' "${log}"; then
        RELEASE_PULL_RATE_LIMITED=true
    fi
    diag_info "Private release-pull failure evidence: ${log} (0600)"
    return 1
}

run_build_attempt() {
    local log="$1"

    : >"${log}"
    if [[ "${VERBOSE_LOGS}" == "true" ]]; then
        run_docker "${build_args[@]}" 2>&1 | tee "${log}"
    else
        run_docker "${build_args[@]}" >"${log}" 2>&1
    fi
}

build_fastapi_sample() {
    local log
    local rc=1

    log="$(mktemp)"
    if run_build_attempt "${log}"; then
        if [[ "${VERBOSE_LOGS}" != "true" ]]; then
            printf 'OK: FastAPI Sample image build completed; detailed Docker build output suppressed.\n'
        fi
        rm -f "${log}"
        return 0
    else
        rc="$?"
    fi

    # A quota failure is not transient BuildKit frontend failure; never retry it.
    if ! dockerhub_429_in_log "${log}" &&
        grep -Fq 'frontend grpc server closed unexpectedly' "${log}"; then
        printf 'WARN: Docker BuildKit frontend closed unexpectedly; retrying the same cache-preserving build once.\n' >&2
        sleep 2
        if run_build_attempt "${log}"; then
            if [[ "${VERBOSE_LOGS}" != "true" ]]; then
                printf 'OK: FastAPI Sample image build completed after one BuildKit retry; detailed output suppressed.\n'
            fi
            rm -f "${log}"
            return 0
        else
            rc="$?"
        fi
    fi

    diag_fail 'FastAPI Sample image build failed; existing runtime was preserved.'
    # Never print raw BuildKit/uv logs: they can include build arguments,
    # registry URLs or credentials. Emit only a fixed-code classification.
    if command -v python3 >/dev/null 2>&1 &&
        [[ -f scripts/truenas/classify-fastapi-build-failure.py ]]; then
        python3 scripts/truenas/classify-fastapi-build-failure.py \
            --check --failure-shape --log "${log}" || true
    fi
    if dockerhub_429_in_log "${log}"; then
        record_dockerhub_429
    fi
    diag_info "Private Docker build evidence: ${log} (0600; may contain secrets)"
    return "${rc}"
}

run_midclt_job_quiet() {
    local label="$1"
    shift
    local log
    local rc=1

    log="$(mktemp)"
    # shellcheck disable=SC2024 # The log is a caller-owned mktemp file; only midclt needs sudo.
    if [[ "${VERBOSE_LOGS}" == "true" ]]; then
        if sudo midclt call -j "$@" 2>&1 | tee "${log}"; then
            rm -f "${log}"
            return 0
        else
            rc="$?"
        fi
    elif sudo midclt call -j "$@" >"${log}" 2>&1; then
        printf 'OK: %s\n' "${label}"
        rm -f "${log}"
        return 0
    else
        rc="$?"
    fi

    diag_fail "${label} failed"
    diag_info "Private lifecycle job evidence: ${log} (0600)"
    return "${rc}"
}

step '2/6' 'FastAPI Git checkout / provenance'
quiet_step 'FastAPI submodule URL synchronized' run_git git submodule sync -- "${SUBMODULE}"
quiet_step 'FastAPI submodule initialized' run_git git submodule update --init --recursive "${SUBMODULE}"

if [[ -n "$(run_git git -C "${SUBMODULE}" status --porcelain --untracked-files=no)" ]]; then
    fail "${SUBMODULE} contains tracked local changes; refusing to overwrite them"
fi

before="$(run_git git -C "${SUBMODULE}" rev-parse HEAD)"
printf 'FastAPI Sample current revision: %s\n' "${before}"

quiet_step 'FastAPI origin refs fetched' run_git git -C "${SUBMODULE}" fetch --prune --tags origin
if target="$(run_git git -C "${SUBMODULE}" rev-parse --verify --quiet "refs/tags/${REF}^{commit}")" &&
    [[ -n "${target}" ]]; then
    target_label="tag/${REF}"
elif target="$(run_git git -C "${SUBMODULE}" rev-parse --verify --quiet "origin/${REF}^{commit}")" &&
    [[ -n "${target}" ]]; then
    target_label="origin/${REF}"
else
    quiet_step "FastAPI ref fetched: ${REF}" run_git git -C "${SUBMODULE}" fetch --prune origin "${REF}"
    target="$(run_git git -C "${SUBMODULE}" rev-parse FETCH_HEAD)"
    target_label="${REF}"
fi

quiet_step "Detached checkout of ${target_label}" run_git git -C "${SUBMODULE}" checkout --detach "${target}"
quiet_step 'FastAPI nested submodules initialized' run_git git -C "${SUBMODULE}" submodule update --init --recursive

package_version="$(
    awk -F'"' '/^version = "/ {print $2; exit}' "${SUBMODULE}/pyproject.toml"
)"
[[ -n "${package_version}" ]] || fail "cannot determine FastAPI Sample package version"

runtime_image="${FASTAPI_SAMPLE_IMAGE:-fastapi-sample:local}"
release_image="${FASTAPI_SAMPLE_RELEASE_IMAGE:-${IMAGE_REPOSITORY}:${package_version}}"
release_image_explicit=false
[[ -n "${FASTAPI_SAMPLE_RELEASE_IMAGE:-}" ]] && release_image_explicit=true
release_ref=false
[[ "${REF}" =~ ^v?[0-9]+[.][0-9]+[.][0-9]+$ ]] && release_ref=true
export FASTAPI_SAMPLE_IMAGE="${runtime_image}"

printf 'Selected ref: %-26s SHA: %s\n' "${target_label}" "${target}"
if [[ "${REF}" == master ]]; then
    summary_warn 'REF defaults to master: this does not deploy changes from an unmerged PR; use FASTAPI_SAMPLE_REF=<immutable-SHA> to stage one.'
fi
printf 'Runtime image: %s\n' "${runtime_image}"

run_docker compose -f apps/sample/compose.yml config --quiet --no-interpolate --no-env-resolution

image_source="local-build"
if [[ "${DEPLOY_MODE}" != "build" && ( "${release_ref}" == true || "${release_image_explicit}" == true ) ]]; then
    printf 'Trying immutable release image: %s\n' "${release_image}"
    if run_release_image_pull "${release_image}"; then
        if [[ "${release_image}" != "${runtime_image}" ]]; then
            run_docker tag "${release_image}" "${runtime_image}"
        fi
        image_source="release-pull"
        printf 'Using prebuilt release image for immutable release ref; local Python dependency build skipped.\n'
    elif [[ "${RELEASE_PULL_RATE_LIMITED}" == true ]]; then
        fail 'Release registry returned HTTP 429; refusing fallback to a local Docker Hub build. Existing runtime preserved.'
    elif [[ "${DEPLOY_MODE}" == "pull" ]]; then
        fail "release image pull failed in pull-only mode: ${release_image}"
    else
        printf 'WARN: release image unavailable; falling back to local BuildKit build.\n' >&2
    fi
elif [[ "${DEPLOY_MODE}" == "pull" ]]; then
    fail "pull-only mode requires a version ref such as 1.20.18 or an explicit FASTAPI_SAMPLE_RELEASE_IMAGE; refusing to substitute a package-version image for moving ref ${REF}"
elif [[ "${DEPLOY_MODE}" == "auto" ]]; then
    printf 'Moving/source ref %s selected; building target commit %s locally instead of reusing package-version image %s.\n' \
        "${REF}" "${target}" "${release_image}"
fi

if [[ "${image_source}" == "local-build" ]]; then
    build_args=(compose -f apps/sample/compose.yml build)
    if [[ "${REFRESH_BASE_IMAGES}" == "true" ]]; then
        build_args+=(--pull)
    else
        printf 'Reusing local Docker base/dependency cache; set FASTAPI_SAMPLE_REFRESH_BASE_IMAGES=true for a security refresh.\n'
    fi
    build_args+=(fastapi-sample)

    step '3/6' 'Build image before replacing runtime'
    guard_dockerhub_base_build
    build_fastapi_sample
fi

step '4/6' 'Observer network and TrueNAS allowlist'
network_contract=""
if run_docker network inspect "${OBSERVER_NETWORK}" >/dev/null 2>&1; then
    network_contract="$(
        run_docker network inspect "${OBSERVER_NETWORK}" |
            jq -r '.[0].Labels["com.nabla.observer-contract"] // empty'
    )"
fi

if [[ -z "${network_contract}" ]]; then
    quiet_step 'Observer network prepared' sudo bash scripts/truenas/prepare-sample-observer-network.sh
elif [[ "${network_contract}" != "v2" ]]; then
    printf 'Observer network contract is %s; recreating v2 safely.\n' "${network_contract:-<missing>}"
    run_docker rm -f "${CONTAINER}" 2>/dev/null || true
    quiet_step 'Observer network recreated (v2)' sudo bash scripts/truenas/prepare-sample-observer-network.sh --recreate
else
    quiet_step 'Observer network checked (v2)' sudo bash scripts/truenas/prepare-sample-observer-network.sh
fi

quiet_step 'TrueNAS observer allowlist reconciled' sudo bash scripts/security/reconcile-truenas-observer-allowlist.sh --apply

step '5/6' 'Redeploy staging and verify health'
summary_warn 'Now replacing the staging container (brief interruption possible).'
run_docker rm -f "${CONTAINER}" 2>/dev/null || true

compose_path="${ROOT}/apps/sample/compose.yml"

run_midclt_job_quiet "FastAPI Sample app.update completed" \
    app.update "${APP_ID}" "$(
        jq -cn --arg include "${compose_path}" '{
          custom_compose_config: {
            include: [$include]
          }
        }'
    )"

run_midclt_job_quiet "FastAPI Sample app.redeploy completed" \
    app.redeploy "${APP_ID}"

printf 'Waiting for FastAPI Sample health on :8091...\n'
health_payload="$(
    wait_for_json_endpoint \
        "FastAPI Sample health" \
        "http://127.0.0.1:8091/health" \
        90 \
        2
)"
health_status="$(jq -r '.status // "unknown"' <<<"${health_payload}")"
healthy_components="$(jq -r '[.components[]? | select(.status == "healthy")] | length' <<<"${health_payload}")"
total_components="$(jq -r '[.components[]?] | length' <<<"${health_payload}")"
[[ "${health_status}" == healthy && "${healthy_components}" == "${total_components}" && "${total_components}" -gt 0 ]] ||
  fail "FastAPI Sample health contract not healthy for all components"
summary_ok "FastAPI HTTP application health: ${health_status} (${healthy_components}/${total_components} components)"

version_payload="$(
    wait_for_json_endpoint \
        "FastAPI Sample version" \
        "http://127.0.0.1:8091/v2/version" \
        15 \
        1
)"
summary_ok "FastAPI version $(jq -r '.release_version // .version // "unknown"' <<<"${version_payload}")"
# Compare runtime image ID to the exact selected local/ref image. This proves
# artifact identity but NOT its Git revision when build_revision is null.
selected_image_id="$(run_docker image inspect "${runtime_image}" --format '{{.Id}}' 2>/dev/null || true)"
running_image_id="$(run_docker inspect "${CONTAINER}" --format '{{.Image}}' 2>/dev/null || true)"
if [[ -z "${selected_image_id}" || -z "${running_image_id}" || "${selected_image_id}" != "${running_image_id}" ]]; then
    fail "running FastAPI container image digest does not match selected local image"
fi
summary_ok "Runtime image identity matches selected artifact (not Git SHA attestation)"
if [[ -z "$(jq -r '.build_revision // empty' <<<"${version_payload}")" ]]; then
    summary_warn 'build_revision=null: the API package version does not attest an exact Git SHA.'
fi

quiet_step 'TrueNAS observer least-privilege checks' sudo bash scripts/security/verify-truenas-observer-access.sh

step '6/6' 'Optional integrations and deployment summary'
prometheus_state='warning'
if prometheus_details="$(verify_prometheus_observer_contract 2>&1)"; then
    summary_ok "${prometheus_details}"
    prometheus_state='ok'
else
    summary_warn "${prometheus_details}"
fi

pfsense_state='not-run'
if run_docker exec "${CONTAINER}" /code/.venv/bin/python \
    -c 'import nabla.api.pfsense_auth_smoke' >/dev/null 2>&1; then
    pfsense_report="$(mktemp)"
    if run_docker exec "${CONTAINER}" /code/.venv/bin/python \
        -m nabla.api.pfsense_auth_smoke --url https://home.albandrieu.com:10443 >"${pfsense_report}" 2>&1; then
        pfsense_summary="$(grep -E '^summary passed=[0-9]+ total=[0-9]+ secrets_printed=no$' "${pfsense_report}" | tail -n 1 || true)"
        if [[ -n "${pfsense_summary}" ]]; then
            summary_ok "pfSense RBAC: ${pfsense_summary}"
            pfsense_state='ok'
        else
            summary_warn 'pfSense check returned success without expected summary'
            pfsense_state='warning'
        fi
    else
        summary_warn 'pfSense RBAC smoke failed (authenticated log suppressed); deployment remains accepted because pfSense is optional diagnostic evidence'
        pfsense_state='warning'
    fi
    rm -f -- "${pfsense_report}"
else
    summary_warn 'pfSense auth-smoke module unavailable (optional)'
fi

# Optional, strictly bounded AI acceptance from inside the running Sample
# container. Does not generate a completion or read private OpenRAG documents.
ai_connectivity_state='not-run'
if [[ -f scripts/truenas/accept-fastapi-ai-connectivity.py ]]; then
    if ai_report="$(python3 scripts/truenas/accept-fastapi-ai-connectivity.py --check 2>/dev/null)"; then
        summary_ok 'AI connectivity: scoped LiteLLM model visible, Ollama and OpenRAG HTTP available'
        ai_connectivity_state='ok'
    else
        summary_warn 'AI connectivity incomplete: LiteLLM auth/model or Ollama/OpenRAG transport needs follow-up'
        ai_connectivity_state='warning'
    fi
    # Fixed-code report only. Never echo container env, model output or secrets.
    if jq -e '.component == "fastapi_ai_acceptance" and .raw_secrets_printed == false' \
         >/dev/null 2>&1 <<<"${ai_report:-}"; then
        jq -c '{litellm,litellm_proxy_liveness,litellm_key_format,litellm_model,litellm_inference,ollama,
          openrag_backend,openrag_frontend,openrag_mcp,
          openrag_integration,openrag_private_retrieval,acceptance}' \
          <<<"${ai_report}"
    fi
else
    summary_warn 'AI acceptance script unavailable in this checkout'
fi

quiet_step 'Canonical Sample runtime env post-check' sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check sample

runtime_sha="$(run_git git -C "${SUBMODULE}" rev-parse HEAD)"
pinned_sha="$(run_git git ls-files -s "${SUBMODULE}" | awk '{print $2}')"
runtime_version="$(jq -r '.release_version // .version // "unknown"' <<<"${version_payload}")"
diag_section '6/6' 'FastAPI Sample · final acceptance'
diag_ok "staging :8091 | version ${runtime_version} | app HTTP ${health_status}"
printf 'Git ref: %s (%s) · image: %s\n' "${REF}" "${runtime_sha:0:12}" "${runtime_image}"
printf 'Checks: image identity=verified | observer=passed | Prometheus/Gatus=%s | pfSense=%s | AI transports=%s\n' "${prometheus_state}" "${pfsense_state}" "${ai_connectivity_state}"
if [[ -n "${pinned_sha}" && "${pinned_sha}" != "${runtime_sha}" ]]; then
    summary_warn "Parent gitlink ${pinned_sha:0:12} differs from checkout ${runtime_sha:0:12}. Not automatically staged."
fi
if [[ -z "$(jq -r '.build_revision // empty' <<<"${version_payload}")" ]]; then
    summary_warn 'Running image Git SHA is not attested by /v2/version; check OCI provenance separately.'
fi
diag_info 'Legacy env rollback inputs retained; do not finalize until reboot acceptance.'
diag_info 'Next: bash scripts/truenas/diagnose-fastapi-sample.sh --cycles 3'
