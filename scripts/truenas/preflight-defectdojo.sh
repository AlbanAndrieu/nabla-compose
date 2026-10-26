#!/usr/bin/env bash
# Read-only DefectDojo prerequisites. No secrets, migrations or deployment.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
# shellcheck source=../lib/diagnostic-ui.sh
source "${ROOT}/scripts/lib/diagnostic-ui.sh"
diag_ui_init "${DIAG_COLOR:-auto}" "${DIAG_ICONS:-auto}" || exit 2
diag_section '' 'DefectDojo · préflight lecture seule'
for tool in docker python3; do
  if command -v "${tool}" >/dev/null; then diag_ok "${tool} disponible"; else diag_fail "${tool} absent"; fi
done
if [[ -d /mnt/cpool/defectdojo ]]; then diag_ok 'Dataset DefectDojo présent'; else diag_fail 'Dataset DefectDojo absent'; fi
if docker inspect ix-postgres-postgres-1 --format '{{.State.Running}}' 2>/dev/null | grep -qx true &&
   docker exec ix-postgres-postgres-1 pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  diag_ok 'PostgreSQL partagé disponible (sans preuve authentification)'
else
  diag_fail 'PostgreSQL partagé indisponible'
fi
if docker inspect redis --format '{{.State.Running}}' 2>/dev/null | grep -qx true; then
  diag_ok 'Conteneur Redis démarré (authentification à confirmer via diagnostic dédié)'
else
  diag_fail 'Redis indisponible'
fi
# Docker Compose needs BOTH env_file paths before container creation.
# Validate the non-secret metadata path independently; a correct .env.secrets
# does not compensate for a missing .env.
runtime_metadata="/mnt/cpool/secrets/runtime/defectdojo/.env"
if [[ ! -f "${runtime_metadata}" || -L "${runtime_metadata}" ]]; then
  diag_fail 'DefectDojo non-secret runtime .env missing or unsafe'
elif (( EUID == 0 )); then
  if python3 "${ROOT}/scripts/truenas/prepare-defectdojo-runtime-env.py" --inspect >/dev/null; then
    diag_ok 'DefectDojo non-secret runtime metadata is root:root 0600'
  else
    diag_fail 'DefectDojo non-secret runtime metadata invalid; normalize the copied .env.example'
  fi
else
  diag_warn 'DefectDojo metadata permissions not attested without sudo'
fi
if [[ -f /mnt/cpool/secrets/runtime/defectdojo/.env.secrets ]]; then
  if [[ "$(stat -c '%U:%G %a' /mnt/cpool/secrets/runtime/defectdojo/.env.secrets)" == 'root:root 600' ]]; then
    diag_ok 'Secrets runtime présents et permissions correctes'
  else
    diag_fail 'Permissions du secret runtime incorrectes'
  fi
else
  diag_warn 'Secrets DefectDojo non matérialisés (Vaultwarden bootstrap requis)'
fi
if [[ "${DD_DATABASE_HOST:-}" == '172.17.0.24' ]]; then
  diag_ok 'DD_DATABASE_HOST cible PostgreSQL TrueNAS'
else
  diag_warn 'Définir DD_DATABASE_HOST=172.17.0.24 avant le rendu Compose'
fi
if [[ -z "${DEFECTDOJO_DJANGO_IMAGE:-}" || "${DEFECTDOJO_DJANGO_IMAGE}" == *:latest ]]; then
  diag_warn 'Image Django non épinglée : sélectionner une version validée'
fi
if [[ -z "${DEFECTDOJO_NGINX_IMAGE:-}" || "${DEFECTDOJO_NGINX_IMAGE}" == *:latest ]]; then
  diag_warn 'Image Nginx non épinglée : sélectionner une version validée'
fi
if [[ -z "${DD_ALLOWED_HOSTS:-}" || "${DD_ALLOWED_HOSTS}" == '*' ]]; then
  diag_warn 'DD_ALLOWED_HOSTS non restreint : définir les hôtes autorisés'
fi
diag_summary
((DIAG_FAILURES == 0))
