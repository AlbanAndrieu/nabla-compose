#!/usr/bin/env bash
set -euo pipefail

APP_ID="${FASTAPI_SAMPLE_APP_ID:-sample}"
COMPOSE_FILE="${FASTAPI_SAMPLE_COMPOSE_FILE:-/mnt/cpool/compose/nabla-compose/apps/sample/compose.yml}"

fail() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

for command in jq midclt sudo; do
	command -v "${command}" >/dev/null 2>&1 ||
		fail "${command} is required"
done

[[ -f "${COMPOSE_FILE}" ]] ||
	fail "Compose file not found at ${COMPOSE_FILE}"

printf 'Validating FastAPI Sample TrueNAS compose include...\n'
if command -v docker >/dev/null 2>&1; then
	if docker info >/dev/null 2>&1; then
		docker compose -f "${COMPOSE_FILE}" config --quiet --no-interpolate --no-env-resolution
	else
		sudo docker compose -f "${COMPOSE_FILE}" config --quiet --no-interpolate --no-env-resolution
	fi
fi

printf 'Redeploying TrueNAS application %s through middlewared...\n' "${APP_ID}"
sudo midclt call -j app.redeploy "${APP_ID}"

sudo midclt call app.query \
	"[[\"id\",\"=\",\"${APP_ID}\"]]" |
	jq '.[0] | {id,state,active_workloads}'

printf 'Done.\n'
