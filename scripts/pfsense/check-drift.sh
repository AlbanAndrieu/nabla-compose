#!/usr/bin/env bash
# Composite read-only drift report: explicit policy checks, plus a full config.xml diff when a baseline is set.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target="${PFSENSE_SSH_TARGET:-admin@172.17.0.1}"
port="${PFSENSE_SSH_PORT:-9922}"
desired_version="${PFSENSE_DESIRED_VERSION:-26.07}"
usage() {
  echo 'Usage: bash scripts/pfsense/check-drift.sh [--check] [--target USER@HOST] [--port PORT]'
}
if [[ "${1:-}" == "--check" ]]; then shift; fi
while (($#)); do
  case "$1" in
    --target) (($# >= 2)) || { usage >&2; exit 2; }; target="$2"; shift 2 ;;
    --port) (($# >= 2)) || { usage >&2; exit 2; }; port="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ "${target}" =~ ^[A-Za-z0-9._@-]+$ ]] || exit 2
[[ "${port}" =~ ^[0-9]{1,5}$ ]] && ((10#${port} > 0 && 10#${port} <= 65535)) || exit 2
echo "pfSense drift audit target=${target}:${port} desired_version=${desired_version}"
echo "INFO: scope=split_dns, Snort/CrowdSec/pfBlockerNG posture, HAProxy/GUI cert bindings, served certs (incl. TrueNAS UI), RAM, DNSBL, PHP-FPM, DHCP, boot environment, full config.xml diff (PFSENSE_DRIFT_BASELINE), scripted fixes in check mode"
echo "INFO: scope_not_included=Cloudflare, live IPv6 SLAAC, runtime state outside config.xml"

drift_count=0
audit_errors=0
echo "==> 1/6 Split-DNS desired vs configured/live"
dns_result=0
bash "${here}/reconcile-split-dns.sh" --check --target "${target}" --port "${port}" || dns_result=$?
if ((dns_result == 2)); then
  drift_count=$((drift_count+1))
elif ((dns_result != 0)); then
  audit_errors=$((audit_errors+1))
fi

echo "==> 2/6 Security and capacity baseline (reuse existing controllers)"
posture_output=""
posture_status=0
posture_output="$(NO_COLOR=1 PFSENSE_COLOR=never bash "${here}/diagnose-recover.sh" \
  --check-posture --target "${target}" --port "${port}" 2>&1)" || posture_status=$?
printf '%s\n' "${posture_output}"
if grep -Eiq 'posture_[[:alnum:]_]+=.*expected=|^[[:space:]]*(FAIL|WARN)[[:space:]]|[[:space:]](FAIL|WARN)[[:space:]]' <<< "${posture_output}"; then
  drift_count=$((drift_count+1))
fi
if ((posture_status != 0)); then
  audit_errors=$((audit_errors+1))
  echo "WARN: posture_audit_exit=${posture_status} (may include an actual failed invariant)"
fi

echo "==> 3/6 Boot Environment, pfSense version and key package versions"
ssh_opts=(-o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 -p "${port}")
boot_status=0
boot_report="$(ssh "${ssh_opts[@]}" "${target}" /bin/sh -s <<'REMOTE'
echo "==> Installed version"
if [ -r /etc/version ]; then
  sed -n '1p' /etc/version
else
  echo "version_unavailable"
fi
echo "==> Boot environments (N=now, R=next)"
if command -v bectl >/dev/null 2>&1; then
  bectl list
else
  echo "WARN: bectl_unavailable"
fi
echo "==> Relevant installed package versions"
for name in pfSense-pkg-pfBlockerNG pfSense-pkg-snort pfSense-pkg-crowdsec; do
  pkg info "$name" 2>/dev/null | awk -v pkg="$name" '/^Version[[:space:]]*:/ {print pkg "=" $3; found=1} END{if(!found)print pkg "=NOT_INSTALLED_OR_UNKNOWN"}'
done
REMOTE
)" || boot_status=$?
printf '%s\n' "${boot_report}"
if ((boot_status)); then
  echo "ERROR: could not verify pfSense boot/runtime inventory"
  audit_errors=$((audit_errors+1))
else
  version="$(sed -n '/^==> Installed version/{n;p;}' <<< "${boot_report}")"
  if [[ "${version}" != "${desired_version}"* ]]; then
    echo "DRIFT: pfSense_version=${version} expected_target=${desired_version} (upgrade is a separate reviewed action)"
    drift_count=$((drift_count+1))
  fi
  if grep -Eq '^default_clone[[:space:]]+NR?[[:space:]]|^default_clone[[:space:]]+N[[:space:]]' <<< "${boot_report}"; then
    echo "WARN: active Boot Environment default_clone; compare against prior 26.07 rollback incident"
  fi
fi
echo "==> 4/6 Full config.xml diff: rules, NAT, aliases, HAProxy, VPN, certificates, IPv6, DNS"
if [[ -n "${PFSENSE_DRIFT_BASELINE:-}" ]]; then
  config_status=0
  python3 "${here}/config-drift.py" --baseline "${PFSENSE_DRIFT_BASELINE}" --ssh "${target}" --port "${port}" || config_status=$?
  if ((config_status == 2)); then
    drift_count=$((drift_count+1))
  elif ((config_status != 0)); then
    audit_errors=$((audit_errors+1))
  fi
else
  echo "INFO: set PFSENSE_DRIFT_BASELINE to a known-good config.xml backup (outside Git) for the full diff"
fi
echo "==> 5/6 Served certificates: trusted chain, expected name, at least 14 days left"
cert_drift=0
# HAProxy :443/:7000, pfSense GUI and the TrueNAS UI (ui_certificate) seen from the LAN.
for endpoint in home.albandrieu.com:443/home.albandrieu.com truenas.albandrieu.com:7000/truenas.albandrieu.com \
  172.17.0.1:10443/home.albandrieu.com 172.17.0.24:7000/truenas.albandrieu.com; do
  addr="${endpoint%/*}"
  name="${endpoint#*/}"
  if timeout 10 openssl s_client -connect "${addr}" -servername "${name}" -verify_hostname "${name}" \
    -verify_return_error </dev/null 2>/dev/null | openssl x509 -noout -checkend 1209600 >/dev/null 2>&1; then
    echo "PASS: served_cert ${addr} name=${name}"
  else
    echo "DRIFT: served_cert ${addr} name=${name} untrusted, wrong name, unreachable or under 14 days"
    cert_drift=1
  fi
done
drift_count=$((drift_count+cert_drift))
echo "==> 6/6 Scripted fixes still applied (each fix script in check mode, no mutation)"
fix_drift=0
# Args: label, remote command, local script. CHANGE/WARN/ERROR means the fix drifted away.
run_fix_check() {
  local out status=0
  # shellcheck disable=SC2029 # the remote command is a fixed literal chosen by this script.
  out="$(ssh "${ssh_opts[@]}" "${target}" "$2" <"$3" 2>&1)" || status=$?
  printf '%s\n' "${out}" | sed "s/^/$1: /"
  if ((status != 0)); then
    audit_errors=$((audit_errors+1))
  elif grep -Eq '^(CHANGE|WARN|ERROR):' <<< "${out}"; then
    fix_drift=1
  fi
}
run_fix_check workstation_targets "php -- check" "${here}/retire-workstation-targets.php"
run_fix_check dhcp_staticmaps "php -- check" "${here}/restore-dhcp-staticmaps.php"
run_fix_check pfblocker_ip_only "php -- check" "${here}/pfblocker-ip-only.php"
run_fix_check php_generator_mode "/bin/sh -s -- check" "${here}/repair-be-php-generator-mode.sh"
run_fix_check fallback_be_config "/bin/sh -s -- check auto" "${here}/sync-fallback-be-config.sh"
run_fix_check be_own_country "php -- check" "${here}/be-drop-own-country.php"
run_fix_check pflow "php -- check" "${here}/reconcile-pflow.php"
# Drop this line once 26.07 is the running BE (pfsense-26.07-upgrade.md).
run_fix_check fallback_exclusion "/bin/sh -s -- check default_20260824183037" "${here}/exclude-be-from-fallback.sh"
drift_count=$((drift_count+fix_drift))
echo "==> Summary"
echo "drift_groups=${drift_count} audit_errors=${audit_errors}"
if ((audit_errors)); then
  echo "result=INCOMPLETE_UNVERIFIED"
  exit 3
fi
if ((drift_count)); then
  echo "result=CONFIG_DRIFT_REQUIRES_REVIEW"
  exit 2
fi
echo "result=SCOPED_BASELINE_CONVERGED"
