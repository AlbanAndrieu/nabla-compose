#!/usr/bin/env bash
# Read-only Sample public/private DNS diagnostics; workstation mode is opt-in.
set -uo pipefail

MODE="${1:---check}"
case "$MODE" in
  --check|--workstation|--truenas) (( $# <= 1 )) || exit 2 ;;
  *) echo "Usage: $0 [--check|--truenas|--workstation]" >&2; exit 2 ;;
esac
PUBLIC_HOST="${SAMPLE_DNS_PUBLIC_HOST:-sample.albandrieu.com}"
PRIVATE_HOST="${SAMPLE_DNS_PRIVATE_HOST:-sample.int.albandrieu.com}"
TRUENAS_IP="${SAMPLE_DNS_TRUENAS_IP:-172.17.0.24}"
PFSENSE_DNS="${SAMPLE_DNS_PFSENSE_IP:-172.17.0.1}"
PIHOLE_DNS="${SAMPLE_DNS_PIHOLE_IP:-172.17.0.24}"
PUBLIC_DNS="${SAMPLE_DNS_PUBLIC_RESOLVER:-1.1.1.1}"
IFACE="${SAMPLE_DNS_IFACE:-eno1}"
PIHOLE_CONTAINER="${SAMPLE_DNS_PIHOLE_CONTAINER:-pihole}"

for hostname in "$PUBLIC_HOST" "$PRIVATE_HOST"; do
  [[ "$hostname" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]{0,251}$ ]] || { echo 'invalid DNS hostname' >&2; exit 2; }
done
for address in "$TRUENAS_IP" "$PFSENSE_DNS" "$PIHOLE_DNS" "$PUBLIC_DNS"; do
  [[ "$address" =~ ^[0-9]+(\.[0-9]+){3}$ ]] || { echo 'invalid DNS IPv4 argument' >&2; exit 2; }
done
[[ "$IFACE" =~ ^[a-zA-Z0-9_.:-]+$ && "$PIHOLE_CONTAINER" =~ ^[a-zA-Z0-9_.-]+$ ]] || exit 2
command -v dig >/dev/null 2>&1 || { echo 'UNKNOWN: dig unavailable' >&2; exit 2; }

failures=0
warnings=0
fail() { printf 'FAIL: %s\n' "$*"; failures=$((failures + 1)); }
warn() { printf 'WARN: %s\n' "$*"; warnings=$((warnings + 1)); }
ok() { printf 'OK: %s\n' "$*"; }

lookup_a() {
  dig +time=2 +tries=1 +short "@$1" "$2" A 2>/dev/null |
    awk '/^[0-9]+(\.[0-9]+){3}$/ {print}' | sort -u
}

is_private_ipv4() {
  local first second
  IFS=. read -r first second _ <<<"$1"
  case "$first" in
    0|10|127) return 0 ;;
    172) [[ "$second" =~ ^[0-9]+$ ]] && ((10#$second >= 16 && 10#$second <= 31)); return $? ;;
    192) [[ "$second" == 168 ]]; return $? ;;
    169) [[ "$second" == 254 ]]; return $? ;;
  esac
  return 1
}

check_public() {
  local label="$1" server="$2" answers="$3" address bad=0
  printf 'dns=%s server=%s name=%s A=%s\n' "$label" "$server" "$PUBLIC_HOST" "${answers//$'\n'/,}"
  if [[ -z "$answers" ]]; then
    warn "$label: public DNS unavailable"
    return
  fi
  while IFS= read -r address; do
    if is_private_ipv4 "$address"; then bad=1; fi
  done <<<"$answers"
  if ((bad)); then
    fail "$label: public hostname resolves to a private/LAN address; bypasses Cloudflare/ECH"
  else
    ok "$label: public hostname is not redirected to private IPv4"
  fi
}

echo '==> Sample DNS public: Cloudflare-bound hostname'
pfsense_public="$(lookup_a "$PFSENSE_DNS" "$PUBLIC_HOST")"
pihole_public="$(lookup_a "$PIHOLE_DNS" "$PUBLIC_HOST")"
external_public="$(lookup_a "$PUBLIC_DNS" "$PUBLIC_HOST")"
check_public pfSense "$PFSENSE_DNS" "$pfsense_public"
check_public Pi-hole "$PIHOLE_DNS" "$pihole_public"
check_public public-resolver "$PUBLIC_DNS" "$external_public"

echo '==> Sample DNS private: TrueNAS-bound hostname'
for resolver in "$PIHOLE_DNS" "$PFSENSE_DNS"; do
  answers="$(lookup_a "$resolver" "$PRIVATE_HOST")"
  printf 'dns=%s name=%s A=%s\n' "$resolver" "$PRIVATE_HOST" "${answers//$'\n'/,}"
  if grep -Fxq "$TRUENAS_IP" <<<"$answers"; then
    ok "private hostname via $resolver resolves to TrueNAS"
  else
    warn "private hostname via $resolver not confirmed at TrueNAS"
  fi
done

echo '==> Sample DNS system resolver / NSS'
if command -v getent >/dev/null 2>&1; then
  system_ips="$(getent ahostsv4 "$PUBLIC_HOST" 2>/dev/null |
    awk '$2 == "STREAM" {print $1}' | sort -u)"
  check_public system-resolver system "$system_ips"
else
  warn 'getent unavailable; system DNS unchecked'
fi

if [[ "$MODE" != --truenas ]]; then
  # Read-only DNS check works on any host; local Docker/TrueNAS provenance
  # needs explicit --truenas to avoid a false warning on workstations.
  echo 'SKIP: Pi-hole container configuration requires --truenas on TrueNAS'
else
  echo '==> Sample Pi-hole local DNS record provenance (content redacted)'
  DOCKER_CMD=()
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER_CMD=(docker)
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    DOCKER_CMD=(sudo -n docker)
  fi
  if (("${#DOCKER_CMD[@]}" > 0)); then
    if "${DOCKER_CMD[@]}" inspect "$PIHOLE_CONTAINER" >/dev/null 2>&1; then
      if sources="$("${DOCKER_CMD[@]}" exec "$PIHOLE_CONTAINER" sh -c '
        name="$1"
        for source in /etc/pihole/pihole.toml /etc/pihole/custom.list /etc/hosts /etc/dnsmasq.d/*.conf; do
          [ -f "$source" ] || continue
          if grep -Fq -- "$name" "$source"; then printf "%s\n" "$source"; fi
        done
      ' _ "$PUBLIC_HOST" 2>/dev/null)"; then
        if [[ -n "$sources" ]]; then
          while IFS= read -r source; do
            printf 'pihole_override_source=%s\n' "$source"
          done <<<"$sources"
          if [[ "$pihole_public" == *"$TRUENAS_IP"* ]]; then
            echo 'EVIDENCE: Pi-hole local record explains the previously reported public DNS FAIL'
          else
            warn 'Pi-hole configuration references PUBLIC hostname: review record ownership even if live DNS is currently public'
          fi
        else
          ok 'no matching public DNS record in reviewed Pi-hole files'
        fi
      else
        warn 'Pi-hole local-file inspection failed'
      fi
    else
      warn "Pi-hole container '$PIHOLE_CONTAINER' unavailable"
    fi
  else
    echo 'SKIP: local Docker access unavailable; Pi-hole file inspection not attempted'
  fi

fi

if [[ "$MODE" == --workstation ]]; then
  echo '==> Sample workstation: system resolution of private .int hostname'
  if command -v getent >/dev/null 2>&1; then
    private_system="$(getent ahostsv4 "$PRIVATE_HOST" 2>/dev/null |
      awk '$2 == "STREAM" {print $1}' | sort -u)"
    if grep -Fxq "$TRUENAS_IP" <<<"$private_system"; then
      ok "system resolver correctly routes private .int hostname to TrueNAS"
    else
      warn "system resolver cannot resolve private .int hostname to TrueNAS; Quad9/public DNS alone is not sufficient"
    fi
  fi
fi

if [[ "$MODE" == --workstation ]]; then
  echo '==> Sample workstation: active DNS versus DHCP lease'
  if command -v systemctl >/dev/null 2>&1; then
    for manager in NetworkManager systemd-networkd; do
      printf 'manager=%s state=%s\n' "$manager" "$(systemctl is-active "$manager" 2>/dev/null || true)"
    done
  fi
  if command -v nmcli >/dev/null 2>&1; then
    nmcli -f GENERAL.CONNECTION,IP4.DNS,IP6.DNS device show "$IFACE" 2>/dev/null ||
      warn "NetworkManager interface $IFACE unavailable"
    # Do not reveal full NetworkManager profiles (identities or secrets).
    # Read ONLY the active profile's DNS fields; an empty result is UNKNOWN.
    profile="$(nmcli -g GENERAL.CONNECTION device show "$IFACE" 2>/dev/null || true)"
    if [[ -n "$profile" && "$profile" != "--" ]]; then
      printf 'active_nm_profile=%s\n' "$profile"
      echo '==> NetworkManager active connection DNS settings'
      nm_fields='ipv4.method,ipv4.dns,ipv4.ignore-auto-dns,ipv4.dns-priority,ipv4.dns-search'
      if nm_dns="$(nmcli -f "$nm_fields" connection show "$profile" 2>/dev/null)" &&
         [[ -n "$nm_dns" ]]; then
        printf '%s\n' "$nm_dns"
      elif nm_dns="$(nmcli -g ipv4.dns,ipv4.ignore-auto-dns connection show "$profile" 2>/dev/null)" &&
           [[ -n "$nm_dns" ]]; then
        printf 'nmcli_dns_values=%s\n' "$nm_dns"
        warn 'NetworkManager formatted DNS fields unavailable; displaying raw DNS values instead'
      else
        warn 'NetworkManager active profile DNS properties returned no data; inspect nmcli manually'
      fi
    else
      warn "NetworkManager active connection profile for $IFACE unavailable"
    fi
    # Canonical machine-readable profile values: DHCP can be correct while
    # a saved profile deliberately discards it (as on Wired eno1).
    nm_profile_dns="$(nmcli -g ipv4.dns connection show "$profile" 2>/dev/null || true)"
    nm_ignore_auto_dns="$(nmcli -g ipv4.ignore-auto-dns connection show "$profile" 2>/dev/null || true)"
    if [[ "$nm_ignore_auto_dns" == yes || "$nm_ignore_auto_dns" == true ]]; then
      warn "NetworkManager profile ignores DHCP DNS; configured static DNS: ${nm_profile_dns:-none}"
      echo "ACTION: review 'nmcli connection modify <profile> ipv4.ignore-auto-dns no ipv4.dns ""' locally (no change performed)"
    fi
    nmcli -f DHCP4.OPTION device show "$IFACE" 2>/dev/null |
      grep -Ei 'domain_name_servers|dhcp_server_identifier' || true
  else
    warn 'nmcli unavailable; lease DNS origin unknown'
  fi
  if command -v resolvectl >/dev/null 2>&1; then
    if active_dns="$(resolvectl dns "$IFACE" 2>/dev/null)"; then
      printf '%s\n' "$active_dns"
      # DHCP may correctly announce pfSense while a local profile selects Quad9.
      if ! grep -Fqw "$PFSENSE_DNS" <<<"$active_dns"; then
        warn "interface $IFACE DNS differs from pfSense; inspect NetworkManager profile/resolved, not DHCP blindly"
      fi
      # A configured profile DNS and an unrelated active resolver indicate
      # a second source (VPN, global resolved settings or stale link state).
      if [[ -n "${nm_profile_dns:-}" ]]; then
        profile_dns_seen=0
        for profile_server in ${nm_profile_dns//,/ }; do
          if grep -Fqw "$profile_server" <<<"$active_dns"; then
            profile_dns_seen=1
          fi
        done
        if (( profile_dns_seen == 0 )); then
          warn "systemd-resolved DNS on $IFACE differs from NetworkManager profile DNS; inspect VPN/global DNS configuration"
        fi
      fi
    else
      warn "unable to inspect active DNS on $IFACE"
    fi
    resolvectl domain "$IFACE" 2>/dev/null || true
  else
    warn 'resolvectl unavailable; active link DNS unknown'
  fi
  if command -v networkctl >/dev/null 2>&1 &&
     command -v systemctl >/dev/null 2>&1 &&
     [[ "$(systemctl is-active systemd-networkd 2>/dev/null || true)" == active ]]; then
    networkctl status "$IFACE" --no-pager 2>/dev/null || true
  fi
fi

if [[ "$pihole_public" == *"$TRUENAS_IP"* ]]; then
  echo "ACTION: Pi-hole v6 Local DNS: remove only '$TRUENAS_IP $PUBLIC_HOST'; preserve '$PRIVATE_HOST'"
  echo "ACTION: rerun the diagnostic after Pi-hole's managed DNS configuration is updated"
fi
if [[ "$MODE" == --workstation && -n "${active_dns:-}" ]] &&
   ! grep -Fqw "$PFSENSE_DNS" <<<"$active_dns"; then
  echo "ACTION: inspect active NetworkManager profile DNS settings; do not alter pfSense DHCP ($PFSENSE_DNS)"
fi
printf 'sample_dns_summary failures=%d warnings=%d\n' "$failures" "$warnings"
((failures == 0))
