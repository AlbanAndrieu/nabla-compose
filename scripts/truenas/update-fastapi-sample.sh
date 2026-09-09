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

fail() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

for command in git docker jq curl sudo midclt stat awk; do
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

case "${DEPLOY_MODE}" in
	auto | pull | build) ;;
	*) fail "FASTAPI_SAMPLE_DEPLOY_MODE must be one of: auto, pull, build" ;;
esac

case "${REFRESH_BASE_IMAGES}" in
	true | false) ;;
	*) fail "FASTAPI_SAMPLE_REFRESH_BASE_IMAGES must be true or false" ;;
esac

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

		if ((attempt == 1 || attempt % 10 == 0)); then
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

run_git git submodule sync --recursive
run_git git submodule update --init --recursive "${SUBMODULE}"

if [[ -n "$(run_git git -C "${SUBMODULE}" status --porcelain --untracked-files=no)" ]]; then
	fail "${SUBMODULE} contains tracked local changes; refusing to overwrite them"
fi

before="$(run_git git -C "${SUBMODULE}" rev-parse HEAD)"
printf 'FastAPI Sample current revision: %s\n' "${before}"

run_git git -C "${SUBMODULE}" fetch --prune --tags origin
if target="$(run_git git -C "${SUBMODULE}" rev-parse --verify --quiet "refs/tags/${REF}^{commit}")" &&
	[[ -n "${target}" ]]; then
	target_label="tag/${REF}"
elif target="$(run_git git -C "${SUBMODULE}" rev-parse --verify --quiet "origin/${REF}^{commit}")" &&
	[[ -n "${target}" ]]; then
	target_label="origin/${REF}"
else
	run_git git -C "${SUBMODULE}" fetch --prune origin "${REF}"
	target="$(run_git git -C "${SUBMODULE}" rev-parse FETCH_HEAD)"
	target_label="${REF}"
fi

run_git git -C "${SUBMODULE}" checkout --detach "${target}"
run_git git -C "${SUBMODULE}" submodule update --init --recursive

package_version="$(
	awk -F'"' '/^version = "/ {print $2; exit}' "${SUBMODULE}/pyproject.toml"
)"
[[ -n "${package_version}" ]] || fail "cannot determine FastAPI Sample package version"

runtime_image="${FASTAPI_SAMPLE_IMAGE:-fastapi-sample:local}"
release_image="${FASTAPI_SAMPLE_RELEASE_IMAGE:-${IMAGE_REPOSITORY}:${package_version}}"
export FASTAPI_SAMPLE_IMAGE="${runtime_image}"

printf 'FastAPI Sample target %s: %s (version %s)\n' \
	"${target_label}" "${target}" "${package_version}"
printf 'Runtime image: %s\n' "${runtime_image}"

run_docker compose -f apps/sample/compose.yml config --quiet --no-interpolate --no-env-resolution

image_source="local-build"
if [[ "${DEPLOY_MODE}" != "build" ]]; then
	printf 'Trying immutable release image: %s\n' "${release_image}"
	if run_docker pull "${release_image}"; then
		if [[ "${release_image}" != "${runtime_image}" ]]; then
			run_docker tag "${release_image}" "${runtime_image}"
		fi
		image_source="release-pull"
		printf 'Using prebuilt release image; local Python dependency build skipped.\n'
	elif [[ "${DEPLOY_MODE}" == "pull" ]]; then
		fail "release image pull failed in pull-only mode: ${release_image}"
	else
		printf 'WARN: release image unavailable; falling back to local BuildKit build.\n' >&2
	fi
fi

if [[ "${image_source}" == "local-build" ]]; then
	build_args=(compose -f apps/sample/compose.yml build)
	if [[ "${REFRESH_BASE_IMAGES}" == "true" ]]; then
		build_args+=(--pull)
	else
		printf 'Reusing local Docker base/dependency cache; set FASTAPI_SAMPLE_REFRESH_BASE_IMAGES=true for a security refresh.\n'
	fi
	build_args+=(fastapi-sample)

	printf 'Building fastapi-sample before runtime replacement...\n'
	run_docker "${build_args[@]}"
fi

network_contract=""
if run_docker network inspect "${OBSERVER_NETWORK}" >/dev/null 2>&1; then
	network_contract="$(
		run_docker network inspect "${OBSERVER_NETWORK}" |
			jq -r '.[0].Labels["com.nabla.observer-contract"] // empty'
	)"
fi

if [[ -z "${network_contract}" ]]; then
	sudo bash scripts/truenas/prepare-sample-observer-network.sh
elif [[ "${network_contract}" != "v2" ]]; then
	printf 'Observer network contract is %s; recreating v2 safely.\n' "${network_contract:-<missing>}"
	run_docker rm -f "${CONTAINER}" 2>/dev/null || true
	sudo bash scripts/truenas/prepare-sample-observer-network.sh --recreate
else
	sudo bash scripts/truenas/prepare-sample-observer-network.sh
fi

sudo bash scripts/security/reconcile-truenas-observer-allowlist.sh --apply

printf 'Removing the previous FastAPI Sample container after successful build...\n'
run_docker rm -f "${CONTAINER}" 2>/dev/null || true

compose_path="${ROOT}/apps/sample/compose.yml"

sudo midclt call -j app.update "${APP_ID}" "$(
	jq -cn --arg include "${compose_path}" '{
      custom_compose_config: {
        include: [$include]
      }
    }'
)"

sudo midclt call -j app.redeploy "${APP_ID}"

printf 'Waiting for FastAPI Sample health on :8091...\n'
health_payload="$(
	wait_for_json_endpoint \
		"FastAPI Sample health" \
		"http://127.0.0.1:8091/health" \
		90 \
		2
)"
jq . <<<"${health_payload}"

printf 'FastAPI Sample version:\n'
version_payload="$(
	wait_for_json_endpoint \
		"FastAPI Sample version" \
		"http://127.0.0.1:8091/v2/version" \
		15 \
		1
)"
jq . <<<"${version_payload}"

sudo bash scripts/security/verify-truenas-observer-access.sh

runtime_sha="$(run_git git -C "${SUBMODULE}" rev-parse HEAD)"
printf 'OK: FastAPI Sample %s deployed from %s via %s\n' "${REF}" "${runtime_sha}" "${image_source}"

pinned_sha="$(run_git git ls-files -s "${SUBMODULE}" | awk '{print $2}')"
if [[ -n "${pinned_sha}" && "${pinned_sha}" != "${runtime_sha}" ]]; then
	printf 'NOTE: parent repository still pins %s; working tree now uses %s.\n' "${pinned_sha}" "${runtime_sha}"
	printf '      Update the parent gitlink in a reviewed PR if this revision is promoted.\n'
fi
