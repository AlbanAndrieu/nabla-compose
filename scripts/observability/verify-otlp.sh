#!/usr/bin/env bash
set -euo pipefail

OBSERVABILITY_HOST="${OBSERVABILITY_HOST:-172.17.0.24}"
ALLOY_OTLP_HTTP_URL="${ALLOY_OTLP_HTTP_URL:-http://${OBSERVABILITY_HOST}:4320}"
LOKI_URL="${LOKI_URL:-http://${OBSERVABILITY_HOST}:3100}"
MIMIR_URL="${MIMIR_URL:-http://${OBSERVABILITY_HOST}:9009}"
TEMPO_URL="${TEMPO_URL:-http://${OBSERVABILITY_HOST}:3200}"
OTLP_SMOKE_TIMEOUT="${OTLP_SMOKE_TIMEOUT:-30}"

errors=0
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

ok() { printf '✅ %s\n' "$*"; }
fail() {
  printf '❌ %s\n' "$*" >&2
  errors=$((errors + 1))
}

for command in curl date jq mktemp python3; do
  if command -v "${command}" >/dev/null 2>&1; then
    ok "command available: ${command}"
  else
    fail "missing command: ${command}"
  fi
done
if ((errors > 0)); then
  exit 1
fi

marker="nabla-otlp-smoke-$(date +%s)-$$"
read -r trace_id metric_value < <(
  python3 - "${tmp_dir}" "${marker}" <<'PY'
import json
import os
import sys
import time

out = sys.argv[1]
marker = sys.argv[2]
now = time.time_ns()
metric_value = (now // 1_000_000_000) % 1_000_000

trace_bytes = os.urandom(16)
span_bytes = os.urandom(8)
trace_id = trace_bytes.hex()

resource = {
    "attributes": [
        {
            "key": "service.name",
            "value": {"stringValue": "nabla-observability-smoke"},
        }
    ]
}

logs = {
    "resourceLogs": [
        {
            "resource": resource,
            "scopeLogs": [
                {
                    "scope": {"name": "nabla-observability-smoke"},
                    "logRecords": [
                        {
                            "timeUnixNano": str(now),
                            "severityText": "INFO",
                            "body": {"stringValue": marker},
                            "attributes": [
                                {
                                    "key": "loki.resource.labels",
                                    "value": {"stringValue": "service.name"},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
}

metrics = {
    "resourceMetrics": [
        {
            "resource": resource,
            "scopeMetrics": [
                {
                    "scope": {"name": "nabla-observability-smoke"},
                    "metrics": [
                        {
                            "name": "nabla_observability_smoke",
                            "description": "Nabla observability integration smoke metric",
                            "unit": "1",
                            "gauge": {
                                "dataPoints": [
                                    {
                                        "timeUnixNano": str(now),
                                        "asInt": str(metric_value),
                                    }
                                ]
                            },
                        }
                    ],
                }
            ],
        }
    ]
}

traces = {
    "resourceSpans": [
        {
            "resource": resource,
            "scopeSpans": [
                {
                    "scope": {"name": "nabla-observability-smoke"},
                    "spans": [
                        {
                            "traceId": trace_bytes.hex(),
                            "spanId": span_bytes.hex(),
                            "name": marker,
                            "kind": 1,
                            "startTimeUnixNano": str(now),
                            "endTimeUnixNano": str(now + 1_000_000),
                            "status": {"code": 1},
                        }
                    ],
                }
            ],
        }
    ]
}

for name, payload in (
    ("logs", logs),
    ("metrics", metrics),
    ("traces", traces),
):
    with open(os.path.join(out, f"{name}.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle)

print(trace_id, metric_value)
PY
)

post_otlp() {
  local signal="$1"
  local status
  status="$(curl --silent --show-error --request POST     --connect-timeout 4 --max-time 15     --header 'Content-Type: application/json'     --data-binary "@${tmp_dir}/${signal}.json"     --output "${tmp_dir}/${signal}-response.json"     --write-out '%{http_code}'     "${ALLOY_OTLP_HTTP_URL%/}/v1/${signal}" || true)"
  if [[ "${status}" == "200" ]]; then
    ok "Alloy accepted OTLP ${signal}"
  else
    fail "Alloy rejected OTLP ${signal} (HTTP ${status:-none})"
  fi
}

printf '🧪 OTLP integration smoke test\n'
printf 'Alloy OTLP/HTTP: %s\n\n' "${ALLOY_OTLP_HTTP_URL}"

post_otlp logs
post_otlp metrics
post_otlp traces

if ((errors > 0)); then
  exit 1
fi

waited=0
loki_ok=false
mimir_ok=false
tempo_ok=false
loki_query='{service_name="nabla-observability-smoke"} |= "'"${marker}"'"'

while ((waited < OTLP_SMOKE_TIMEOUT)); do
  if [[ "${loki_ok}" == "false" ]]; then
    if curl --silent --show-error --get --connect-timeout 4 --max-time 10       --data-urlencode "query=${loki_query}"       --data-urlencode 'since=5m'       --data-urlencode 'limit=20'       --output "${tmp_dir}/loki.json"       "${LOKI_URL%/}/loki/api/v1/query_range" 2>/dev/null &&
      jq -e '.status == "success" and (.data.result | length) > 0'         "${tmp_dir}/loki.json" >/dev/null 2>&1; then
      loki_ok=true
      ok "OTLP log reached Loki"
    fi
  fi

  if [[ "${mimir_ok}" == "false" ]]; then
    if curl --silent --show-error --get --connect-timeout 4 --max-time 10       --data-urlencode 'query={__name__=~"nabla_observability_smoke.*"}'       --output "${tmp_dir}/mimir.json"       "${MIMIR_URL%/}/prometheus/api/v1/query" 2>/dev/null &&
      jq -e --arg expected "${metric_value}" '
        .status == "success"
        and (.data.result | length) > 0
        and any(.data.result[]; .value[1] == $expected)
      ' "${tmp_dir}/mimir.json" >/dev/null 2>&1; then
      mimir_ok=true
      ok "OTLP metric reached Mimir"
    fi
  fi

  if [[ "${tempo_ok}" == "false" ]]; then
    status="$(curl --silent --show-error --connect-timeout 4 --max-time 10       --output "${tmp_dir}/tempo.json" --write-out '%{http_code}'       "${TEMPO_URL%/}/api/traces/${trace_id}" 2>/dev/null || true)"
    if [[ "${status}" == "200" ]] && jq -e '(.batches // .resourceSpans // .trace // empty) != null' "${tmp_dir}/tempo.json" >/dev/null 2>&1; then
      tempo_ok=true
      ok "OTLP trace reached Tempo"
    fi
  fi

  if [[ "${loki_ok}" == "true" && "${mimir_ok}" == "true" && "${tempo_ok}" == "true" ]]; then
    break
  fi

  sleep 2
  waited=$((waited + 2))
done

[[ "${loki_ok}" == "true" ]] || fail "OTLP log did not become queryable in Loki within ${OTLP_SMOKE_TIMEOUT}s"
[[ "${mimir_ok}" == "true" ]] || fail "OTLP metric did not become queryable in Mimir within ${OTLP_SMOKE_TIMEOUT}s"
[[ "${tempo_ok}" == "true" ]] || fail "OTLP trace did not become queryable in Tempo within ${OTLP_SMOKE_TIMEOUT}s"

printf '\n'
if ((errors > 0)); then
  printf '❌ OTLP integration smoke test failed with %d error(s).\n' "${errors}" >&2
  exit 1
fi

printf '✅ Alloy OTLP fan-out to Loki, Mimir and Tempo is healthy.\n'
