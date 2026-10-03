#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP_ID="${NABLA_DOCKER_PROXY_APP_ID:-docker-socket-proxy}"
NETWORK="${NABLA_DOCKER_PROXY_NETWORK:-intranet}"
ALIAS="${NABLA_DOCKER_PROXY_ALIAS:-docker-socket-proxy}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    cat <<'EOF'
usage:
  sudo bash scripts/truenas/ensure-docker-socket-proxy-intranet.sh --check
  sudo bash scripts/truenas/ensure-docker-socket-proxy-intranet.sh --apply

Ensures the active TrueNAS Docker Socket Proxy container is attached to the
shared intranet network with the docker-socket-proxy alias required by
repository-managed consumers such as pihole-dns-sync.

The Docker network attachment is runtime-scoped: TrueNAS App recreation may
remove it. Re-run this helper after restore/redeploy until the proxy provider is
fully migrated to repository-owned Compose.
EOF
    exit 0
    ;;
  *) fail "unsupported mode: ${MODE}" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root"
for command in docker jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

docker network inspect "${NETWORK}" >/dev/null 2>&1 ||
  fail "Docker network does not exist: ${NETWORK}"

app_json="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]")"
state="$(jq -r 'if length == 1 then .[0].state else "MISSING" end' <<<"${app_json}")"
[[ "${state}" == "RUNNING" ]] ||
  fail "${APP_ID}: TrueNAS App state=${state}, expected RUNNING"

container_id="$(
  jq -r '
    .[0].active_workloads.container_details[]?
    | select(.service_name == "docker-socket-proxy" and .state == "running")
    | .id
  ' <<<"${app_json}" | head -n1
)"
[[ -n "${container_id}" ]] ||
  fail "${APP_ID}: no running docker-socket-proxy workload found"

container_name="$(docker inspect --format '{{.Name}}' "${container_id}" | sed 's#^/##')"

network_json="$(
  docker inspect "${container_id}" |
    jq -c --arg network "${NETWORK}" '.[0].NetworkSettings.Networks[$network] // null'
)"

if [[ "${network_json}" == "null" ]]; then
  if [[ "${MODE}" == "--check" ]]; then
    fail "${container_name}: not attached to ${NETWORK}; apply with --apply"
  fi

  printf 'ATTACH %s -> %s alias=%s\n' "${container_name}" "${NETWORK}" "${ALIAS}"
  docker network connect --alias "${ALIAS}" "${NETWORK}" "${container_id}"

  network_json="$(
    docker inspect "${container_id}" |
      jq -c --arg network "${NETWORK}" '.[0].NetworkSettings.Networks[$network] // null'
  )"
fi

[[ "${network_json}" != "null" ]] ||
  fail "${container_name}: ${NETWORK} attachment still missing"

if ! jq -e --arg alias "${ALIAS}" '
  ((.Aliases // []) + (.DNSNames // [])) | index($alias) != null
' <<<"${network_json}" >/dev/null; then
  fail "${container_name}: attached to ${NETWORK} but alias ${ALIAS} is missing; review before reconnecting"
fi

ipv4="$(jq -r '.IPAddress // ""' <<<"${network_json}")"
ipv6="$(jq -r '.GlobalIPv6Address // ""' <<<"${network_json}")"

printf 'OK: %s attached to %s alias=%s ipv4=%s ipv6=%s\n'   "${container_name}" "${NETWORK}" "${ALIAS}"   "${ipv4:-none}" "${ipv6:-none}"
