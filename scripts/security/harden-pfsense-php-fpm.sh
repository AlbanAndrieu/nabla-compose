#!/bin/sh
set -eu

MODE="${1:---check}"
SOURCE="${PFSENSE_PHP_FPM_GENERATOR:-/etc/rc.php_ini_setup}"
GENERATED="${PFSENSE_PHP_FPM_CONFIG:-/usr/local/lib/php-fpm.conf}"
BACKUP="${PFSENSE_PHP_FPM_BACKUP:-/conf/backup/rc.php_ini_setup.nabla-pre-phpfpm-hardening}"
TARGET_MAX=4
TARGET_IDLE=30
TARGET_START=1
TARGET_SPARE=2
TARGET_REQ=500

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: harden-pfsense-php-fpm.sh [--check|--apply|--restore]

--check    Read-only: show sizing inputs and validate source/generated state.
--apply    Back up the pfSense generator, harden the >1000 MiB profile, regenerate
           php-fpm.conf, restart PHP-FPM and the WebConfigurator, then validate.
--restore  Restore the saved generator, regenerate and restart the services.

Environment overrides are available for tests/recovery only:
  PFSENSE_PHP_FPM_GENERATOR
  PFSENSE_PHP_FPM_CONFIG
  PFSENSE_PHP_FPM_BACKUP
EOF
}

case "${MODE}" in
  --check|--apply|--restore) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; fail "unsupported mode: ${MODE}" ;;
esac

[ -f "${SOURCE}" ] || fail "pfSense PHP-FPM generator not found: ${SOURCE}"

release="unknown"
if [ -r /etc/version ]; then
  release=$(cat /etc/version)
fi

realmem="unknown"
physmem="unknown"
if command -v sysctl >/dev/null 2>&1; then
  realmem=$(sysctl -n hw.realmem 2>/dev/null || printf unknown)
  physmem=$(sysctl -n hw.physmem 2>/dev/null || printf unknown)
fi

printf 'pfSense release: %s\n' "${release}"
printf 'hw.realmem: %s\n' "${realmem}"
printf 'hw.physmem: %s\n' "${physmem}"

source_state() {
  awk '
    BEGIN { in_profile=0; max=""; idle=""; start=""; spare=""; req="" }
    /elif \[ "\$\{REALMEM\}" -gt 1000 \]; then/ { in_profile=1; next }
    in_profile && /^[[:space:]]*fi[[:space:]]*$/ {
      printf "%s/%s/%s/%s/%s\n", max, idle, start, spare, req
      exit
    }
    in_profile && /^[[:space:]]*PHPFPMMAX=/   { sub(/.*=/, ""); gsub(/[[:space:]]/, ""); max=$0 }
    in_profile && /^[[:space:]]*PHPFPMIDLE=/  { sub(/.*=/, ""); gsub(/[[:space:]]/, ""); idle=$0 }
    in_profile && /^[[:space:]]*PHPFPMSTART=/ { sub(/.*=/, ""); gsub(/[[:space:]]/, ""); start=$0 }
    in_profile && /^[[:space:]]*PHPFPMSPARE=/ { sub(/.*=/, ""); gsub(/[[:space:]]/, ""); spare=$0 }
    in_profile && /^[[:space:]]*PHPFPMREQ=/   { sub(/.*=/, ""); gsub(/[[:space:]]/, ""); req=$0 }
  ' "${SOURCE}"
}

generated_state() {
  [ -f "${GENERATED}" ] || { printf 'missing\n'; return; }
  awk '
    /^[[:space:]]*pm\.max_children[[:space:]]*=/      { max=$3 }
    /^[[:space:]]*pm\.process_idle_timeout[[:space:]]*=/ { idle=$3 }
    /^[[:space:]]*pm\.start_servers[[:space:]]*=/     { start=$3 }
    /^[[:space:]]*pm\.max_spare_servers[[:space:]]*=/ { spare=$3 }
    /^[[:space:]]*pm\.max_requests[[:space:]]*=/      { req=$3 }
    END { printf "%s/%s/%s/%s/%s\n", max, idle, start, spare, req }
  ' "${GENERATED}"
}

expected="${TARGET_MAX}/${TARGET_IDLE}/${TARGET_START}/${TARGET_SPARE}/${TARGET_REQ}"
upstream="8/3600/2/7/5000"
current_source=$(source_state)
printf 'generator >1000 MiB profile: %s\n' "${current_source:-missing}"
printf 'generated PHP-FPM profile: %s\n' "$(generated_state)"

if [ "${MODE}" = "--check" ]; then
  case "${current_source}" in
    "${expected}") printf 'OK: generator already uses Nabla constrained profile %s\n' "${expected}" ;;
    "${upstream}") printf 'WARN: generator still uses pfSense high-memory profile %s\n' "${upstream}" ;;
    *) fail "unrecognized >1000 MiB generator profile; refuse to infer a safe patch" ;;
  esac
  exit 0
fi

[ "$(id -u)" -eq 0 ] || fail "--apply/--restore must run as root"

if [ "${MODE}" = "--restore" ]; then
  [ -f "${BACKUP}" ] || fail "backup not found: ${BACKUP}"
  cp -p "${BACKUP}" "${SOURCE}"
  /etc/rc.php_ini_setup
  /etc/rc.php-fpm_restart
  /etc/rc.restart_webgui
  printf 'OK: restored generator from %s\n' "${BACKUP}"
  printf 'generated PHP-FPM profile: %s\n' "$(generated_state)"
  exit 0
fi

case "${current_source}" in
  "${expected}") printf 'OK: source generator is already hardened; regenerating runtime only\n' ;;
  "${upstream}")
    if [ ! -f "${BACKUP}" ]; then
      cp -p "${SOURCE}" "${BACKUP}"
      chmod 600 "${BACKUP}" 2>/dev/null || true
      printf 'saved rollback copy: %s\n' "${BACKUP}"
    fi

    tmp=$(mktemp "${SOURCE}.nabla.XXXXXX") || fail "unable to create temporary generator"
    trap 'rm -f "${tmp}"' EXIT HUP INT TERM

    awk -v max="${TARGET_MAX}" -v idle="${TARGET_IDLE}" -v start="${TARGET_START}" -v spare="${TARGET_SPARE}" -v req="${TARGET_REQ}" '
      BEGIN { in_profile=0; changes=0 }
      /elif \[ "\$\{REALMEM\}" -gt 1000 \]; then/ { in_profile=1; print; next }
      in_profile && /^[[:space:]]*fi[[:space:]]*$/ { in_profile=0; print; next }
      in_profile && /^[[:space:]]*PHPFPMMAX=8[[:space:]]*$/   { sub(/PHPFPMMAX=8/, "PHPFPMMAX=" max); changes++; print; next }
      in_profile && /^[[:space:]]*PHPFPMIDLE=3600[[:space:]]*$/ { sub(/PHPFPMIDLE=3600/, "PHPFPMIDLE=" idle); changes++; print; next }
      in_profile && /^[[:space:]]*PHPFPMSTART=2[[:space:]]*$/ { sub(/PHPFPMSTART=2/, "PHPFPMSTART=" start); changes++; print; next }
      in_profile && /^[[:space:]]*PHPFPMSPARE=7[[:space:]]*$/ { sub(/PHPFPMSPARE=7/, "PHPFPMSPARE=" spare); changes++; print; next }
      in_profile && /^[[:space:]]*PHPFPMREQ=5000[[:space:]]*$/ { sub(/PHPFPMREQ=5000/, "PHPFPMREQ=" req); changes++; print; next }
      { print }
      END { if (changes != 5) exit 42 }
    ' "${SOURCE}" >"${tmp}" || { rc=$?; rm -f "${tmp}"; trap - EXIT HUP INT TERM; fail "generator shape changed or patch count was not exactly five (rc=${rc})"; }

    cp -p "${tmp}" "${SOURCE}"
    rm -f "${tmp}"
    trap - EXIT HUP INT TERM
    ;;
  *) fail "unrecognized >1000 MiB generator profile; refusing mutation" ;;
esac

[ "$(source_state)" = "${expected}" ] || fail "source generator did not reach expected profile ${expected}"

/etc/rc.php_ini_setup
[ "$(generated_state)" = "${expected}" ] || fail "generated PHP-FPM config does not match expected profile ${expected}"

/etc/rc.php-fpm_restart
[ -S /var/run/php-fpm.socket ] || fail "PHP-FPM socket was not recreated"

/etc/rc.restart_webgui

workers=$(ps axww -o command | grep -c '^php-fpm: pool nginx (php-fpm)$' || true)
[ "${workers}" -le "${TARGET_MAX}" ] || fail "PHP-FPM worker count ${workers} exceeds target ${TARGET_MAX}"

printf 'OK: pfSense PHP-FPM constrained profile applied: %s\n' "${expected}"
printf 'OK: PHP-FPM socket present and worker count=%s (max=%s)\n' "${workers}" "${TARGET_MAX}"
printf 'NOTE: re-run --check after every pfSense upgrade; upstream may replace /etc/rc.php_ini_setup.\n'
