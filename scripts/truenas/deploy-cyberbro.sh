#!/usr/bin/env bash
set -euo pipefail

APP_ID="${CYBERBRO_APP_ID:-cyberbro}"
CANONICAL_ROOT="${CYBERBRO_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
CYBERBRO_URL="${CYBERBRO_URL:-http://172.17.0.24:5100/}"
WAIT_SECONDS="${CYBERBRO_WAIT_SECONDS:-240}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "run with sudo -E so TrueNAS middleware, ZFS and runtime env files can be managed"
for command in docker git jq midclt curl python3; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

printf '==> Cyberbro datasets\n'
bash scripts/truenas/bootstrap-repository-storage.sh --apply "${APP_ID}"
bash scripts/truenas/bootstrap-repository-storage.sh --check "${APP_ID}"

printf '\n==> Cyberbro runtime env files\n'
bash scripts/truenas/bootstrap-cyberbro-env.sh --apply
bash scripts/truenas/bootstrap-cyberbro-env.sh --check

compose_path="${CANONICAL_ROOT}/apps/cyberbro/compose.yml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"
docker compose \
  -f "${compose_path}" \
  config \
  --quiet \
  --no-interpolate \
  --no-env-resolution

printf '\n==> generated service contracts\n'
python3 scripts/generate-service-topology.py --check
python3 scripts/generate-service-consumers.py --check

printf '\n==> TrueNAS Custom App reconciliation\n'
if midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
  jq -e 'length > 0' >/dev/null; then
  midclt call -j app.update "${APP_ID}" "$(
    jq -cn --arg include "${compose_path}" '{
      custom_compose_config: {
        include: [$include]
      }
    }'
  )"
else
  wrapper="$(printf 'include:\n  - %s\n' "${compose_path}")"
  midclt call -j app.create "$(
    jq -cn \
      --arg app_name "${APP_ID}" \
      --arg compose "${wrapper}" \
      '{
        app_name: $app_name,
        custom_app: true,
        custom_compose_config_string: $compose
      }'
  )"
fi

printf '\n==> wait for TrueNAS RUNNING + container health\n'
deadline=$((SECONDS + WAIT_SECONDS))
while ((SECONDS < deadline)); do
  state="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" | jq -r '.[0].state // "UNKNOWN"')"
  cyberbro_health="$(docker inspect cyberbro --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  mcp_state="$(docker inspect mcp-cyberbro --format '{{.State.Status}}' 2>/dev/null || true)"
  if [[ "${state}" == "RUNNING" && "${cyberbro_health}" == "healthy" && "${mcp_state}" == "running" ]]; then
    break
  fi
  sleep 4
done

if ! bash scripts/truenas/diagnose-cyberbro.sh; then
  fail "Cyberbro failed runtime acceptance; diagnostic evidence printed above"
fi

printf '\n==> final curl acceptance\n'
curl -fsS --max-time 10 -o /dev/null "${CYBERBRO_URL}" ||
  fail "final Cyberbro curl failed: ${CYBERBRO_URL}"
printf 'OK: curl %s\n' "${CYBERBRO_URL}"

printf '\n==> downstream generated-monitor consumers\n'
if midclt call app.query '[["id","=","autokuma"]]' |
  jq -e 'length > 0' >/dev/null; then
  bash scripts/truenas/deploy-autokuma.sh
else
  printf 'WARNING: autokuma TrueNAS app not present; generated monitor inventory is ready but not reconciled.\n' >&2
fi

if midclt call app.query '[["id","=","uptime-kuma"]]' |
  jq -e 'length > 0' >/dev/null; then
  midclt call app.query '[["id","=","uptime-kuma"]]' |
    jq -r '.[0] | "OK: Uptime Kuma state=\(.state // \"UNKNOWN\") (monitor configuration reconciled by AutoKuma)"'
else
  printf 'WARNING: uptime-kuma TrueNAS app not present.\n' >&2
fi

for consumer in gatus homarr; do
  if midclt call app.query "[[\"id\",\"=\",\"${consumer}\"]]" |
    jq -e 'length > 0' >/dev/null; then
    midclt call -j app.redeploy "${consumer}"
    midclt call app.query "[[\"id\",\"=\",\"${consumer}\"]]" |
      jq -r '.[0] | "OK: \(.id) state=\(.state // \"UNKNOWN\")"'
  else
    printf 'WARNING: %s TrueNAS app not present; generated config remains ready for next deployment.\n' "${consumer}" >&2
  fi
done

printf 'INFO: Prometheus not redeployed because Cyberbro has no documented metrics endpoint and this change does not modify apps/prometheus configuration.\n'
printf 'OK: Cyberbro deployment and downstream reconciliation completed.\n'
