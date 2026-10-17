#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

# Read-only, bounded post-reboot triage. No restart, upgrade or secret values.
for command in midclt jq docker; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "ERROR: missing ${command}" >&2; exit 2;
  }
done

if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != dumb ]]; then
  green=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
section 'Applications TrueNAS non démarrées / en transition'
while IFS=
section 'Applications prioritaires'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  state="$(jq -r --arg app "${app}" '[.[] | select(.id==$app) | (.state // "UNKNOWN")] | if length==0 then "ABSENT" else .[0] end' "$tmp")"
  status "$app" "$state"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
section 'Cyberbro MCP · conteneur Compose'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
section 'Conteneurs Docker en anomalie (40 maximum)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
section 'PostgreSQL et Redis · diagnostics post-reboot'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  printf '%b⚠️  Contrôles des services de données à investiguer%b\n' "$yellow" "$reset"
fi
section 'Prochains diagnostics sûrs (lecture seule)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[32m'; yellow=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[33m'; red=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[31m'
  blue=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[36m'; bold=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[1m'; reset=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[0m'
else
  green=''; yellow=''; red=''; blue=''; bold=''; reset=''
fi
section() { printf '\n%b🔎 %s%b\n' "$blue$bold" "$1" "$reset"; }
status() {
  local name="$1" state="$2"
  case "$state" in
    RUNNING|Up*) printf '%b✅ %-28s %s%b\n' "$green" "$name" "$state" "$reset" ;;
    STOPPED|ABSENT|Exited*) printf '%b⚪ %-28s %s%b\n' "$yellow" "$name" "$state" "$reset" ;;
    *) printf '%b⚠️  %-28s %s%b\n' "$red" "$name" "$state" "$reset" ;;
  esac
}

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\t' read -r name state; do status "$name" "$state"; done < <(
  jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "$tmp" |
    LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
)
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[32m'; yellow=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[33m'; red=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[31m'
  blue=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[36m'; bold=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[1m'; reset=
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
\033[0m'
else
  green=''; yellow=''; red=''; blue=''; bold=''; reset=''
fi
section() { printf '\n%b🔎 %s%b\n' "$blue$bold" "$1" "$reset"; }
status() {
  local name="$1" state="$2"
  case "$state" in
    RUNNING|Up*) printf '%b✅ %-28s %s%b\n' "$green" "$name" "$state" "$reset" ;;
    STOPPED|ABSENT|Exited*) printf '%b⚪ %-28s %s%b\n' "$yellow" "$name" "$state" "$reset" ;;
    *) printf '%b⚠️  %-28s %s%b\n' "$red" "$name" "$state" "$reset" ;;
  esac
}

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"
jq -e 'type=="array"' "${tmp}" >/dev/null || {
  echo 'ERROR: invalid TrueNAS app.query' >&2; exit 2;
}
printf '%s\n' '==> Non-running or in-flight applications'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "${tmp}" |
  LC_ALL=C sort | awk 'NR<=80 {print} END {if(NR>80) printf "... %d additional apps omitted\n", NR-80}'
printf '%s\n' '==> High-priority application states'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  jq -r --arg app "${app}" '
    [.[] | select(.id==$app) | (.state // "UNKNOWN")] |
    if length==0 then "ABSENT" else .[0] end |
    $app+"="+.' "${tmp}"
done
# mcp-cyberbro is a Compose service inside the cyberbro TrueNAS App,
# not an independent App ID. app.query would misleadingly report ABSENT.
printf '%s\n' '==> Cyberbro MCP Compose workload'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "NOT FOUND"; else if(NR>5) printf "... %d omitted\n", NR-5}'
printf '%s\n' '==> Problematic Docker workloads (capped)'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print} END {if(NR>40) printf "... %d additional containers omitted\n", NR-40}' || true
printf '%s\n' '==> Shared PostgreSQL / Redis post-reboot diagnostics'
# This check is read-only. Missing Redis credentials are reported as WARN.
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  echo 'WARN: shared data services require operator investigation'
fi
printf '%s\n' '==> Next safe diagnostics (do not apply until the failing reason is confirmed)'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/diagnose-cyberbro.sh'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check'
printf '%s\n' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'

printf '\n%b📋 Fin du triage · aucune modification runtime effectuée%b\n' "$bold" "$reset"
