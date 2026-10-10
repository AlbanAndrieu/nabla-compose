#!/bin/sh
# pfSense FreeBSD: run explicitly using /bin/sh, NEVER paste POSIX assignments into tcsh.
# Read-only central CrowdSec LAPI authentication using the existing local bouncer key.
set -eu
CONFIG=/usr/local/etc/crowdsec/bouncers/crowdsec-firewall-bouncer.yaml
LAPI=http://172.17.0.24:8084
[ -r "$CONFIG" ] || { echo "ERROR: bouncer config unreadable"; exit 2; }
command -v curl >/dev/null 2>&1 || { echo "ERROR: curl unavailable"; exit 2; }
KEY=$(awk '
  /^[[:space:]]*api_key[[:space:]]*:/ {
    sub(/^[^:]*:[[:space:]]*/, "")
    sub(/[[:space:]]+#.*$/, "")
    gsub(/^[[:space:]]+|[[:space:]]+$/, "")
    if (substr($0,1,1) == "\"" && substr($0,length($0),1) == "\"")
      $0=substr($0,2,length($0)-2)
    if (substr($0,1,1) == "\047" && substr($0,length($0),1) == "\047")
      $0=substr($0,2,length($0)-2)
    print
    exit
  }' "$CONFIG")
[ -n "$KEY" ] || { echo "ERROR: empty bouncer key"; exit 2; }
# Reject values needing curl-config escaping. Do not print the key.
case "$KEY" in
  *\"*|*\\*|*'
'*) echo "ERROR: unsupported key encoding"; unset KEY; exit 2 ;;
esac
# curl reads the header from stdin rather than command argv or a secret-bearing file.
# HTTP GET is read-only for PF tables; LAPI may update last_pull metadata.
HTTP_CODE=$(
  {
    printf 'url = "%s/v1/decisions?ip=192.0.2.1"\n' "$LAPI"
    printf 'header = "X-Api-Key: %s"\n' "$KEY"
    printf 'output = "/dev/null"\n'
    printf 'silent\nshow-error\n'
    printf 'connect-timeout = 3\nmax-time = 8\n'
    printf 'write-out = "%%{http_code}"\n'
  } | curl --config -
) || { unset KEY; echo "ERROR: curl failed"; exit 1; }
unset KEY
printf 'central_lapi_http=%s\n' "$HTTP_CODE"
case "$HTTP_CODE" in 200) exit 0 ;; *) exit 1 ;; esac
