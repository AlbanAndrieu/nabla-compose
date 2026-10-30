#!/usr/bin/env bash
# Workstation-only, audited pfSense PHP-FPM capacity reconciliation.
# Modifications require an explicit opt-in and run on the Netgate over SSH.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PAYLOAD="${ROOT}/scripts/security/harden-pfsense-php-fpm.sh"
TARGET="${PFSENSE_SSH_TARGET:-home.albandrieu.com}"
PORT="${PFSENSE_SSH_PORT:-}"
ACK="${PFSENSE_PHP_FPM_CHANGE_CONFIRM:-}"

usage() {
  cat <<'EOF'
Usage: reconcile-php-fpm.sh --check|--apply|--restore
  --check   Read-only: remote generator/profile/worker count and resolver status.
  --apply   Needs PFSENSE_PHP_FPM_CHANGE_CONFIRM=APPLY_4_WORKERS.
  --restore Needs PFSENSE_PHP_FPM_CHANGE_CONFIRM=RESTORE_BACKUP.

Only --apply/--restore restart PHP-FPM and WebConfigurator (not Unbound).
Keep an independent shell or serial console available during maintenance.
EOF
}
case "${1:-}" in
  --check) mode=check; token="" ;;
  --apply) mode=apply; token=APPLY_4_WORKERS ;;
  --restore) mode=restore; token=RESTORE_BACKUP ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
[[ $# -eq 1 ]] || { usage >&2; exit 2; }
[[ "${TARGET}" =~ ^[a-zA-Z0-9._@-]+$ ]] || { echo "Invalid SSH target" >&2; exit 2; }
if [[ -n "${PORT}" ]]; then
  [[ "${PORT}" =~ ^[0-9]{1,5}$ ]] || { echo "Invalid SSH port" >&2; exit 2; }
  PORT=$((10#${PORT}))
  ((PORT >= 1 && PORT <= 65535)) || { echo "Invalid SSH port" >&2; exit 2; }
fi
if [[ "${mode}" != check && "${ACK}" != "${token}" ]]; then
  echo "ERROR: explicit maintenance confirmation missing (${token})" >&2
  exit 2
fi
[[ -r "${PAYLOAD}" ]] || { echo "ERROR: reviewed PHP-FPM payload missing" >&2; exit 2; }
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes)
[[ -z "${PORT}" ]] || ssh_opts+=(-p "${PORT}")

echo "=== Preflight: Unbound resolver and pfSense service posture (read-only) ==="
# Validated mode must expand into the remote argv.
# shellcheck disable=SC2029
ssh "${ssh_opts[@]}" "${TARGET}" "/bin/sh -s -- ${mode}" <<'REMOTE'
set -eu
mode=$1
healthy=yes
if ! pgrep -x unbound >/dev/null 2>&1; then
  echo "WARN: unbound_not_running"; healthy=no
elif ! unbound-control -c /var/unbound/unbound.conf status 2>/dev/null | grep -q 'is running'; then
  echo "WARN: unbound_control_unavailable"; healthy=no
elif ! drill -t A example.com @127.0.0.1 2>/dev/null | grep -q 'rcode: NOERROR'; then
  echo "WARN: unbound_public_dns_unverified"; healthy=no
fi
if [ "$healthy" = yes ]; then
  echo 'preflight_unbound=HEALTHY'
else
  echo 'preflight_unbound=UNVERIFIED'
  if [ "$mode" = apply ]; then
    echo 'ERROR: refusing_php_fpm_apply_while_unbound_unhealthy'
    exit 80
  fi
fi
if [ -S /var/run/php-fpm.socket ]; then
  echo 'preflight_php_socket=PRESENT'
else
  echo 'preflight_php_socket=MISSING'
fi
if pgrep -f crowdsec-firewall-bouncer >/dev/null 2>&1; then
  echo 'preflight_crowdsec_firewall_bouncer=PROCESS_SEEN'
else
  echo 'preflight_crowdsec_firewall_bouncer=NOT_OBSERVED'
fi
echo 'preflight_crowdsec_bouncer_is_not_modified=yes'
REMOTE

echo "=== Reviewed PHP-FPM profile inspection (read-only) ==="
ssh "${ssh_opts[@]}" "${TARGET}" '/bin/sh -s -- --check' < "${PAYLOAD}"

if [[ "${mode}" == check ]]; then
  echo 'result=CHECK_ONLY_NO_MUTATION'
  exit 0
fi

echo "=== Controlled maintenance: PHP-FPM and webConfigurator (${mode}) ==="
# The remote command chooses root directly or passwordless sudo.
# No interactive credentials; stdin is exclusively the reviewed POSIX script.
# Native pfSense scripts may issue a non-fatal numeric warning on restart.
# Capture only in process memory, show unchanged output and flag it explicitly.
# Never rewrite pfSense appliance service scripts from this workstation driver.
# Validated mode selects the reviewed remote action.
# shellcheck disable=SC2029
if native_output=$(ssh "${ssh_opts[@]}" "${TARGET}" \
  "if [ \"\$(id -u)\" -eq 0 ]; then exec /bin/sh -s -- --${mode}; else exec sudo -n /bin/sh -s -- --${mode}; fi" < "${PAYLOAD}" 2>&1); then
  printf '%s\n' "${native_output}"
else
  native_rc=$?
  printf '%s\n' "${native_output}"
  printf 'ERROR: native_php_fpm_restart_failed exit_code=%s\n' "${native_rc}" >&2
  exit "${native_rc}"
fi
case "${native_output}" in
  *'NaN: bad number'*)
    echo 'WARN: pfSense_native_restart_numeric_warning=OBSERVED_SOURCE_UNCONFIRMED'
    ;;
esac
unset native_output

echo '=== Post-change verification: critical DNS and PHP-FPM ==='
ssh "${ssh_opts[@]}" "${TARGET}" '/bin/sh -s' <<'REMOTE'
set -eu
if ! pgrep -x unbound >/dev/null 2>&1; then
  echo 'ERROR: post_unbound_missing'; exit 81
fi
if ! unbound-control -c /var/unbound/unbound.conf status 2>/dev/null | grep -q 'is running'; then
  echo 'ERROR: post_unbound_control_unavailable'; exit 81
fi
if ! drill -t A example.com @127.0.0.1 2>/dev/null | grep -q 'rcode: NOERROR'; then
  echo 'ERROR: post_dns_failed'; exit 81
fi
[ -S /var/run/php-fpm.socket ] || { echo 'ERROR: post_php_fpm_socket_missing'; exit 81; }
workers=$(ps axww -o command= | awk '/^php-fpm: pool nginx/ {count++} END{print count+0}')
case "$workers" in ''|*[!0-9]*) echo 'ERROR: post_worker_count_unknown'; exit 81;; esac
[ "$workers" -gt 0 ] || { echo 'ERROR: post_workers_absent'; exit 81; }
echo "post_php_fpm_nginx_workers=$workers"
echo 'post_unbound=HEALTHY'
echo 'post_php_socket=PRESENT'
REMOTE

if [[ "${mode}" == apply ]]; then
  echo '=== Verify reduced PHP-FPM pool after apply ==='
  ssh "${ssh_opts[@]}" "${TARGET}" '/bin/sh -s' <<'REMOTE'
set -eu
config=/usr/local/lib/php-fpm.conf
[ -r "$config" ] || { echo 'ERROR: expected_php_fpm_config_unavailable'; exit 82; }
max_children=$(awk -F= '/^[[:space:]]*pm[.]max_children[[:space:]]*=/ {gsub(/[[:space:]]/, "", $2); print $2; exit}' "$config")
[ "$max_children" = 4 ] || { echo 'ERROR: expected_four_php_fpm_children'; exit 82; }
workers=$(ps axww -o command= | awk '/^php-fpm: pool nginx/ {count++} END{print count+0}')
case "$workers" in ''|*[!0-9]*) echo 'ERROR: post_workers_invalid'; exit 82;; esac
[ "$workers" -le 4 ] && [ "$workers" -gt 0 ] ||
  { echo 'ERROR: post_workers_exceed_four_or_missing'; exit 82; }
printf 'verified_php_fpm_max_children=4 active_workers=%s\n' "$workers"
REMOTE
fi

echo '=== Final profile check ==='
ssh "${ssh_opts[@]}" "${TARGET}" '/bin/sh -s -- --check' < "${PAYLOAD}"
echo 'result=CHANGE_COMPLETED_WITH_DNS_SMOKE'
echo 'NOTE: Validate HTTPS webConfigurator, pfREST and LAN/private DNS from the workstation.'
echo 'NOTE: Check RAM with just pfsense-memory-sample.'
