#!/usr/bin/env bash
# Drop a stale public-hostname override from Pi-hole dns.hosts (check, then apply).
#
# Pi-hole keeps hand-made "172.17.0.24 <public name>" records in pihole.toml. When
# Traefik has no router for that name, every LAN client relayed through the R7000
# gets Traefik's 404 while the public Cloudflare route works (vaultwarden, 21/11/2026).
# Removing the record sends LAN clients to the public route, where Access still guards
# the protected paths. *.int.albandrieu.com records belong to pihole-dns-sync: refused.
#
# Usage (from the workstation, through the TrueNAS ControlMaster):
#   scripts/truenas/pihole-public-host-override.sh check vaultwarden.albandrieu.com
#   scripts/truenas/pihole-public-host-override.sh apply vaultwarden.albandrieu.com
set -euo pipefail

mode="${1:-}"
host="${2:-}"
ssh_target="${PIHOLE_SSH_TARGET:-truenas}"

case "${mode}" in check | apply) ;; *)
  echo "usage: $0 check|apply <public hostname>" >&2
  exit 2
  ;;
esac
if [[ ! "${host}" =~ ^[a-z0-9.-]+\.albandrieu\.com$ || "${host}" == *.int.albandrieu.com ]]; then
  echo "refusing '${host}': only public *.albandrieu.com names, never *.int (pihole-dns-sync owns them)" >&2
  exit 2
fi

ftl() { ssh -o BatchMode=yes "${ssh_target}" "sudo -n docker exec pihole pihole-FTL --config dns.hosts $*"; }

current="$(ftl)"
# FTL prints "[ IP name, IP name ]" unquoted, but takes a JSON array when setting.
# Each record is "IP name [name...]"; match the exact name as a whole word.
remaining="$(python3 -c '
import json, sys
host = sys.argv[1]
raw = sys.stdin.read().strip()
assert raw.startswith("[") and raw.endswith("]"), raw[:80]
entries = [e.strip() for e in raw[1:-1].split(",") if e.strip()]
kept = [e for e in entries if host not in e.split()[1:]]
print(json.dumps(kept) if len(kept) != len(entries) else "")
' "${host}" <<<"${current}")"

if [[ -z "${remaining}" ]]; then
  echo "PIHOLE_OVERRIDE_ABSENT ${host}"
  exit 0
fi
if [[ "${mode}" == check ]]; then
  echo "PIHOLE_OVERRIDE_PRESENT ${host} (apply would remove it)"
  exit 1
fi

# shortcut: replaces the whole array; an *.int record pihole-dns-sync adds in the
# same second would be dropped until its next reconcile pass, which re-adds it.
ftl "$(printf '%q' "${remaining}")" >/dev/null
echo "PIHOLE_OVERRIDE_REMOVED ${host}"
