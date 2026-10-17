#!/usr/bin/env bash
# Read-only DefectDojo prerequisites. No secrets, migrations or deployment.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
failures=0
warnings=0
pass() { printf '✅ PASS %s\n' "$1"; }
warn() { printf '⚠️ WARN %s\n' "$1"; warnings=$((warnings+1)); }
fail() { printf '❌ FAIL %s\n' "$1" >&2; failures=$((failures+1)); }
printf '🔎 DefectDojo · préflight lecture seule\n'
for tool in docker python3; do
  if command -v "${tool}" >/dev/null; then pass "${tool} disponible"; else fail "${tool} absent"; fi
done
if [[ -d /mnt/cpool/defectdojo ]]; then pass 'Dataset DefectDojo présent'; else fail 'Dataset DefectDojo absent'; fi
if docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true &&
   docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  pass 'PostgreSQL partagé disponible (sans preuve authentification)'
else
  fail 'PostgreSQL partagé indisponible'
fi
if docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  pass 'Conteneur Redis démarré (authentification à confirmer via diagnostic dédié)'
else
  fail 'Redis indisponible'
fi
if [[ -f /mnt/cpool/secrets/runtime/defectdojo/.env.secrets ]]; then
  if [[ "$(stat -c '%U:%G %a' /mnt/cpool/secrets/runtime/defectdojo/.env.secrets)" == 'root:root 600' ]]; then
    pass 'Secrets runtime présents et permissions correctes'
  else
    fail 'Permissions du secret runtime incorrectes'
  fi
else
  warn 'Secrets DefectDojo non matérialisés (Vaultwarden bootstrap requis)'
fi
if [[ "${DD_DATABASE_HOST:-}" == '172.17.0.24' ]]; then
  pass 'DD_DATABASE_HOST cible PostgreSQL TrueNAS'
else
  warn 'Définir DD_DATABASE_HOST=172.17.0.24 avant le rendu Compose'
fi
if [[ -z "${DEFECTDOJO_DJANGO_IMAGE:-}" || "${DEFECTDOJO_DJANGO_IMAGE}" == *:latest ]]; then
  warn 'Image Django non épinglée : sélectionner une version validée'
fi
if [[ -z "${DEFECTDOJO_NGINX_IMAGE:-}" || "${DEFECTDOJO_NGINX_IMAGE}" == *:latest ]]; then
  warn 'Image Nginx non épinglée : sélectionner une version validée'
fi
if [[ -z "${DD_ALLOWED_HOSTS:-}" || "${DD_ALLOWED_HOSTS}" == '*' ]]; then
  warn 'DD_ALLOWED_HOSTS non restreint : définir les hôtes autorisés'
fi
printf '📋 Bilan : %d échec(s), %d avertissement(s)\n' "${failures}" "${warnings}"
(( failures == 0 ))
