#!/usr/bin/env bash
# Read-only Prometheus correlation for pfSense, TrueNAS and FastAPI Sample.
set -euo pipefail
prom="${PROMETHEUS_URL:-http://172.17.0.24:9090}"
case "${1:---check}" in --check) ;; *) echo "Usage: PROMETHEUS_URL=http://host:9090 $0 --check" >&2; exit 2;; esac
command -v jq >/dev/null || { echo "jq required" >&2; exit 2; }
query() {
  local expression="$1"
  curl -fsS --max-time 15 -G --data-urlencode "query=$expression" "$prom/api/v1/query" |
    jq -er --arg q "$expression" '{query:$q,status,series:[.data.result[]? | {labels:.metric,value:.value[1]}]}'
}
echo '==> Exporter and probe availability (up=1 means scrape succeeded, not service health)'
query 'up{job=~"pfsense_exporter|truenas_node|fastapi_sample|akvorado_inlet|akvorado_outlet"}'
echo '==> pfSense memory ratio (metric may be absent; never treat absence as zero)'
query 'pfsense_system_memory_usage_ratio{job="pfsense_exporter"}'
query 'nabla:core:pfsense_memory_available_ratio'
echo '==> pfSense service and gateway health'
query 'pfsense_service_up{job="pfsense_exporter"}'
query 'pfsense_gateway_up{job="pfsense_exporter"}'
echo '==> TrueNAS available memory and OOM counter'
query 'node_memory_MemAvailable_bytes{job="truenas_node"}'
query 'node_vmstat_oom_kill{job="truenas_node"}'
query 'nabla:core:truenas_memory_available_ratio'
echo '==> Scrape duration and timeout budget'
query 'scrape_duration_seconds{job=~"pfsense_exporter|truenas_node|fastapi_sample"}'
query 'scrape_timeout_seconds{job=~"pfsense_exporter|truenas_node|fastapi_sample"}'
