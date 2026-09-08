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

if docker info >/dev/null 2>&1; then
	DOCKER=(docker)
else
	DOCKER=(sudo docker)
fi

run_docker() {
	"${DOCKER[@]}" "$@"
}

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

run_git git -C "${SUBMODULE}" fetch --prune origin "${REF}"
target="$(run_git git -C "${SUBMODULE}" rev-parse "origin/${REF}")"

run_git git -C "${SUBMODULE}" checkout --detach "${target}"
run_git git -C "${SUBMODULE}" submodule update --init --recursive

printf 'FastAPI Sample target origin/%s: %s\n' "${REF}" "${target}"

run_docker compose -f apps/sample/compose.yml config --quiet --no-interpolate --no-env-resolution

printf 'Building fastapi-sample before runtime replacement...\n'
run_docker compose -f apps/sample/compose.yml build --pull fastapi-sample

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

printf 'Validating FastAPI Sample -> pfSense trusted LAN control path...\n'
pfsense_lan_ip="$(
	run_docker exec "${CONTAINER}" getent hosts home.albandrieu.com |
		awk 'NR == 1 { print $1 }'
)"
[[ "${pfsense_lan_ip}" == "172.17.0.1" ]] ||
	fail "home.albandrieu.com resolved to ${pfsense_lan_ip:-<empty>}, expected pfSense LAN 172.17.0.1"

pfsense_path_mode="$(
	run_docker exec "${CONTAINER}" printenv PFSENSE_SECURITY_PATH_MODE 2>/dev/null ||
		true
)"
[[ "${pfsense_path_mode}" == "out_of_band" ]] ||
	fail "PFSENSE_SECURITY_PATH_MODE=${pfsense_path_mode:-<unset>}, expected out_of_band on TrueNAS"

pfsense_http_status="$(
	run_docker exec "${CONTAINER}" sh -lc \
		'curl --connect-timeout 2 --max-time 5 --silent --show-error --output /dev/null --write-out "%{http_code}" https://home.albandrieu.com:10443/api/v2/system/version'
)"
case "${pfsense_http_status}" in
200 | 401 | 403) ;;
*)
	fail "pfSense LAN HTTPS probe returned HTTP ${pfsense_http_status:-<none>}"
	;;
esac
printf 'OK: pfSense LAN control path resolves to %s, mode=%s, HTTPS=%s\n' \
	"${pfsense_lan_ip}" "${pfsense_path_mode}" "${pfsense_http_status}"

runtime_sha="$(run_git git -C "${SUBMODULE}" rev-parse HEAD)"
printf 'OK: FastAPI Sample origin/%s deployed from %s\n' "${REF}" "${runtime_sha}"

pinned_sha="$(run_git git ls-files -s "${SUBMODULE}" | awk '{print $2}')"
if [[ -n "${pinned_sha}" && "${pinned_sha}" != "${runtime_sha}" ]]; then
	printf 'NOTE: parent repository still pins %s; working tree now uses %s.\n' "${pinned_sha}" "${runtime_sha}"
	printf '      Update the parent gitlink in a reviewed PR if this revision is promoted.\n'
fi
