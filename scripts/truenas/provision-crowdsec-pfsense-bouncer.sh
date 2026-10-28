#!/usr/bin/env bash
# TrueNAS only. Explicit --apply replaces UNUSED PFSENSE_FIREWALL central credential.
# Key is generated and stored BEFORE deleting/reissuing the registration.
# Key stays in protected root-only runtime file. No pfSense changes.
set -euo pipefail
set +x
umask 077

mode="${1:---check}"
case "$mode" in
  --check|--apply) ;;
  -h|--help) echo "Usage: sudo bash $0 [--check|--apply]"; exit 0 ;;
  *) echo 'ERROR: invalid mode' >&2; exit 2 ;;
esac
(($# <= 1)) || { echo 'ERROR: unexpected arguments' >&2; exit 2; }

name='PFSENSE_FIREWALL'
container="${CROWDSEC_CONTAINER:-crowdsec}"
file="${CROWDSEC_SECRET_FILE:-/mnt/cpool/secrets/runtime/crowdsec/.env.secrets}"
[[ "$container" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || { echo 'ERROR: invalid container' >&2; exit 2; }
[[ "$file" == /*/.env.secrets ]] || { echo 'ERROR: invalid runtime secret path' >&2; exit 2; }
for program in docker jq timeout mktemp chmod chown install ln openssl; do
  command -v "$program" >/dev/null || { echo "ERROR: missing tool $program" >&2; exit 2; }
done
if [[ "$mode" == --apply && "$(id -u)" != 0 ]]; then
  echo 'ERROR: --apply must run with sudo/root on TrueNAS' >&2
  exit 2
fi
if [[ -e "$file" || -L "$file" ]]; then
  echo 'credential_state=EXISTS; refusing to overwrite it'
  [[ "$mode" == --check ]] && exit 0 || exit 2
fi
health="$(timeout 10 docker inspect "$container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null)" || {
  echo 'ERROR: cannot inspect CrowdSec container' >&2; exit 2;
}
[[ "$health" == healthy ]] || { echo 'ERROR: central CrowdSec not healthy' >&2; exit 2; }
registrations="$(timeout 12 docker exec "$container" cscli bouncers list -o json 2>/dev/null)" || {
  echo 'ERROR: cannot list central LAPI bouncers' >&2; exit 2;
}
count="$(jq -er --arg name "$name" '[.[] | select(.name == $name)] | length' <<< "$registrations")" || exit 2
[[ "$count" == 0 || "$count" == 1 ]] || { echo 'ERROR: inconsistent registrations' >&2; exit 2; }
last=''
if [[ "$count" == 1 ]]; then
  last="$(jq -r --arg name "$name" '.[] | select(.name == $name) | (.last_pull // "")' <<< "$registrations")"
fi
printf 'central_registration=%s last_pull=%s\n' "$name" "${last:-<none>}"
[[ -z "$last" ]] || { echo 'NO_GO: central bouncer is already used; not rotating'; exit 2; }
if [[ "$mode" == --check ]]; then
  echo 'credential_state=MISSING; unused registration eligible for --apply'
  exit 0
fi

dir="${file%/*}"
install -d -m 0700 -o root -g root -- "$dir"
[[ ! -e "$file" && ! -L "$file" ]] || { echo 'ERROR: secret concurrently created' >&2; exit 2; }
# Generate OUR token first; CrowdSec --output raw may output additional text,
# therefore never parse its result as the key. The --key flag is documented.
# Persist the key BEFORE changing the registration so a CLI error cannot lose it.
key="$(openssl rand -hex 32)" || { echo 'ERROR: key generation failed' >&2; exit 2; }
[[ "$key" =~ ^[a-f0-9]{64}$ ]] || { unset key; echo 'ERROR: invalid generated token' >&2; exit 2; }
tmp="$(mktemp "$dir/.env.secrets.XXXXXX")"
trap '[[ -z "${tmp:-}" ]] || rm -f -- "$tmp"' EXIT
printf 'BOUNCER_KEY_PFSENSE_FIREWALL=%s\n' "$key" > "$tmp"
chmod 0600 "$tmp"
chown root:root "$tmp"
# Atomic creation refuses to overwrite a concurrently created destination.
ln -- "$tmp" "$file" || { unset key; echo 'ERROR: secret already exists' >&2; exit 2; }
rm -f -- "$tmp"
tmp=''
echo 'credential_state=STAGED root:root 0600'

if [[ "$count" == 1 ]]; then
  timeout 12 docker exec "$container" cscli bouncers delete "$name" >/dev/null 2>&1 || {
    unset key
    echo 'NO_GO: unused central registration was not deleted; candidate key safely staged' >&2
    exit 2
  }
fi

# Send token to container on STDIN rather than host/docker process argv.
# Inner sh invokes documented cscli --key, swallowing CLI text (which can
# otherwise disclose the token). Do not enable shell tracing or print it.
if ! printf '%s\n' "$key" |
  timeout 12 docker exec -i "$container" sh -c \
    'IFS= read -r candidate || exit 2; cscli bouncers add PFSENSE_FIREWALL --key "$candidate" >/dev/null 2>&1'; then
  unset key
  echo 'NO_GO: central bouncer add failed; root-only candidate file is retained for recovery' >&2
  exit 2
fi
unset key
echo 'credential_state=CREATED root:root 0600; bouncer=PFSENSE_FIREWALL'
echo 'next=sudo bash scripts/truenas/check-crowdsec-candidate-bouncer.sh'
