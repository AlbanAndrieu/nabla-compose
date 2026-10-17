#!/usr/bin/env bash
# Read-only bounded post-reboot triage. No app lifecycle changes.
set -euo pipefail
for cmd in midclt jq docker; do
  command -v "$cmd" >/dev/null || { printf '❌ Commande absente : %s\n' "$cmd" >&2; exit 2; }
done
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != dumb ]]; then
  BLUE=$'\e[36m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RESET=$'\e[0m'
else
  BLUE='' GREEN='' YELLOW='' RESET=''
fi
section() { printf '\n%b🔎 %s%b\n' "$BLUE" "$1" "$RESET"; }
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
midclt call app.query >"$tmp"
jq -e 'type=="array"' "$tmp" >/dev/null || { echo '❌ app.query invalide' >&2; exit 2; }
section 'Applications TrueNAS non démarrées / en transition'
jq -r '.[] | select((.state // "UNKNOWN") != "RUNNING") | [.id, .state] | @tsv' "$tmp" |
  LC_ALL=C sort | awk 'NR<=80 {print "⚪ " $0} END {if(NR>80) printf "... %d supplémentaires\n",NR-80}'
section 'Applications prioritaires'
for app in dsomm cyberbro sentry scrutiny openrag langflow docling; do
  state="$(jq -r --arg app "$app" '[.[] | select(.id==$app) | (.state // "UNKNOWN")] | if length==0 then "ABSENT" else .[0] end' "$tmp")"
  if [[ "$state" == RUNNING ]]; then
    printf '%b✅ %-20s %s%b\n' "$GREEN" "$app" "$state" "$RESET"
  else
    printf '%b⚠️  %-20s %s%b\n' "$YELLOW" "$app" "$state" "$RESET"
  fi
done
section 'Cyberbro MCP · conteneur Compose'
docker ps -a --filter 'label=com.docker.compose.service=mcp-cyberbro' --format '{{.Names}}\t{{.Status}}' |
  awk 'NR<=5 {print} END {if(NR==0) print "⚪ ABSENT"}'
section 'Conteneurs Docker en anomalie'
docker ps -a --format '{{.Names}}\t{{.Status}}' |
  grep -Ei 'Restarting|unhealthy|Dead|Created|Exited \([1-9]' |
  awk 'NR<=40 {print "⚠️  " $0} END {if(NR>40) printf "... %d supplémentaires\n",NR-40}' || true
section 'PostgreSQL / Redis · diagnostic post-reboot'
if ! bash scripts/truenas/diagnose-shared-data-services.sh; then
  printf '%b⚠️  Vérifier les services de données%b\n' "$YELLOW" "$RESET"
fi
section 'Prochains diagnostics sûrs'
printf '%s\n' 'sudo bash scripts/truenas/deploy-dsomm.sh --check' 'sudo bash scripts/truenas/diagnose-cyberbro.sh' 'sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check' 'sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check' 'sudo bash scripts/truenas/restore-optional-apps.sh --check'
printf '\n%b📋 Triage terminé · aucune modification runtime%b\n' "$GREEN" "$RESET"
