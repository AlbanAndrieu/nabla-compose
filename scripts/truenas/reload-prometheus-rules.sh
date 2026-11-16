#!/usr/bin/env bash
# Reload Prometheus after its config or rule files changed in the checkout.
# The container bind-mounts apps/prometheus read-only, so `git merge --ff-only`
# updates the files but Prometheus keeps the rules it loaded until SIGHUP
# (on 2026-11-16 the last reload dated from 13/11 23:00, 7 h after a merge).
#   check: promtool validation + "reload_needed=yes|no"; exit 1 if invalid or stale.
#   apply: same validation, then SIGHUP only when stale, then verify the reload.
# Run as root on TrueNAS (or `sudo -n`); self-contained so it can also run from the
# workstation before it reaches the checkout:
#   ssh truenas 'sudo -n bash -s -- check' < scripts/truenas/reload-prometheus-rules.sh
set -euo pipefail

mode="${1:-check}"
[[ "${mode}" == check || "${mode}" == apply ]] || {
  echo "usage: reload-prometheus-rules.sh check|apply" >&2
  exit 2
}
url="${PROMETHEUS_URL:-http://127.0.0.1:9090}"

container="$(docker ps -q \
  --filter label=com.docker.compose.project=ix-prometheus \
  --filter label=com.docker.compose.service=prometheus | head -n 1)"
[[ -n "${container}" ]] || {
  echo "ERROR: no running prometheus container (TrueNAS App ix-prometheus)"
  exit 1
}

last_reload() {
  curl -fsS --max-time 10 --get --data-urlencode \
    'query=prometheus_config_last_reload_success_timestamp_seconds' "${url}/api/v1/query" |
    jq -r '.data.result[0].value[1] // "0" | tonumber | floor'
}

if ! docker exec "${container}" promtool check config /etc/prometheus/prometheus.yml >/dev/null 2>&1; then
  echo "ERROR: promtool check config failed; Prometheus keeps its loaded rules"
  exit 1
fi
newest="$(docker exec "${container}" sh -c \
  'stat -c %Y /etc/prometheus/prometheus.yml /etc/prometheus/rules/*.yml' | sort -n | tail -n 1)"
reloaded="$(last_reload)"
if ((newest <= reloaded)); then
  echo "OK: reload_needed=no (last reload $(date -d "@${reloaded}" '+%F %T'))"
  exit 0
fi
echo "reload_needed=yes (files $(date -d "@${newest}" '+%F %T') > last reload $(date -d "@${reloaded}" '+%F %T'))"
[[ "${mode}" == apply ]] || exit 1

docker kill -s HUP "${container}" >/dev/null
for _ in $(seq 1 20); do
  if (($(last_reload) > reloaded)); then
    echo "OK: Prometheus reloaded"
    exit 0
  fi
  sleep 1
done
echo "ERROR: no successful reload within 20 s; check the prometheus container logs"
exit 1
