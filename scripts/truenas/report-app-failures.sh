#!/usr/bin/env bash
set -euo pipefail

for command in midclt jq docker; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    printf '❌ missing command: %s\n' "${command}" >&2
    exit 1
  fi
done

apps_file="$(mktemp)"
jobs_file="$(mktemp)"
trap 'rm -f "${apps_file}" "${jobs_file}"' EXIT

midclt call app.query '[]' '{"extra":{"retrieve_config":true}}' >"${apps_file}"
midclt call core.get_jobs >"${jobs_file}"

printf '=== TrueNAS apps not RUNNING ===\n'
printf 'APP\tSTATE\tCUSTOM\tCONTAINERS\tCOMPOSE_SOURCE\n'

jq -r '
  .[]
  | select(.state != "RUNNING")
  | (
      [
        .config
        | ..
        | strings
        | select(
            startswith("/mnt/cpool/compose/")
            or startswith("/mnt/.ix-apps/")
          )
      ]
      | unique
      | join(" ; ")
    ) as $sources
  | [
      .id,
      .state,
      (.custom_app | tostring),
      ((.active_workloads.containers // 0) | tostring),
      $sources
    ]
  | @tsv
' "${apps_file}"

printf '\n=== Latest lifecycle job for each non-running app ===\n'
while IFS=$'\t' read -r app state; do
  [[ -n "${app}" ]] || continue

  latest="$(
    jq -c --arg app "${app}" '
      [
        .[]
        | select(
            (.method | tostring | startswith("app."))
            and
            ((.arguments // []) | tostring | contains($app))
          )
      ]
      | sort_by(.id)
      | last // empty
      | {
          id,
          method,
          state,
          error,
          progress,
          arguments
        }
    ' "${jobs_file}"
  )"

  printf '%s [%s]\n' "${app}" "${state}"
  if [[ -n "${latest}" ]]; then
    jq . <<<"${latest}"
  else
    printf '  no matching app.* job found\n'
  fi

  printf '  containers:\n'
  docker ps -a     --filter "label=com.docker.compose.project=ix-${app}"     --format '    {{.Names}}\t{{.Status}}' || true

  printf '\n'
done < <(
  jq -r '
    .[]
    | select(.state != "RUNNING")
    | [.id,.state]
    | @tsv
  ' "${apps_file}"
)

printf '=== Unhealthy/restarting/exited ix-* containers ===\n'
docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Label "com.docker.compose.project"}}' |
awk -F '\t' '
  $3 ~ /^ix-/ &&
  (
    $2 ~ /unhealthy/ ||
    $2 ~ /Restarting/ ||
    $2 ~ /^Exited/ ||
    $2 ~ /^Created/
  ) {
    print
  }
'

printf '\n=== Key runtime ports ===\n'
if command -v ss >/dev/null 2>&1; then
  ss -ltnp 2>/dev/null |
    grep -E ':(53|80|443|6060|8080|8084|9005|9090|12345|30238)\\b' || true
else
  printf 'ss not installed; port inventory skipped\n'
fi

printf '\n=== Focus: Traefik ===\n'
jq '
  [
    .[]
    | select(.id == "traefik")
    | {
        id,
        state,
        custom_app,
        active_workloads,
        config
      }
  ]
' "${apps_file}"

printf '\n=== Focus: Keycloak ===\n'
jq '
  [
    .[]
    | select(.id == "keycloak")
    | {
        id,
        state,
        custom_app,
        active_workloads,
        config
      }
  ]
' "${apps_file}"

if ! jq -e '.[] | select(.id == "keycloak")' "${apps_file}" >/dev/null; then
  printf 'INFO: keycloak is not registered as a TrueNAS app. Repository catalog expects LAN HTTP on 172.17.0.24:30238.\n'
fi
