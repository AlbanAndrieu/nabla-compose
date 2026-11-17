#!/bin/sh
# Netgate 1100 eMMC wear (docs.netgate.com troubleshooting/disk-lifetime), streamed over SSH:
#   ssh -p 9922 admin@172.17.0.1 "/bin/sh -s -- check" < scripts/pfsense/emmc-health.sh
# check reads only. apply first installs mmc-utils (operator decision 17/11): it writes to the
# failing pool and needs the WAN. LIFE A/B 0x01..0x0b = 10 % steps of rated life used;
# PRE_EOL 0x01 normal, 0x02 warning (80 % reserved blocks used), 0x03 urgent (90 %).
mode="${1:-check}"
case "${mode}" in
  check|apply) ;;
  *) echo "ERROR: mode must be check or apply"; exit 2 ;;
esac
if ! command -v mmc >/dev/null 2>&1; then
  if [ "${mode}" = check ]; then
    echo "INFO: mmc-utils absent, eMMC wear not read"
    exit 0
  fi
  echo "CHANGE: installing mmc-utils"
  timeout 300 pkg install -y mmc-utils || { echo "ERROR: pkg install mmc-utils failed"; exit 1; }
  hash -r
fi
timeout 20 mmc extcsd read "${MMC_DEVICE:-/dev/mmcsd0rpmb}" 2>&1 | awk '
  /Life Time Estimation A/ { a = $NF } /Life Time Estimation B/ { b = $NF } /Pre EOL/ { e = $NF }
  /BKOPS_STATUS/ { k = $NF; sub(/\]$/, "", k) }
  END {
    if (a == "" && b == "" && e == "") { print "ERROR: no LIFE/EOL field read"; exit 1 }
    printf "INFO: life_used_A=%s life_used_B=%s pre_eol=%s bkops_status=%s\n", a, b, e, k
    life = (hex2dec(a) > hex2dec(b)) ? hex2dec(a) : hex2dec(b)
    if (e == "0x03") { print "WARN: pre_eol=urgent (over 90 % of reserved blocks used)"; warned = 1 }
    else if (e == "0x02") { print "WARN: pre_eol=warning (over 80 % of reserved blocks used)"; warned = 1 }
    if (life >= 11) { print "WARN: rated life exhausted (0x0b = 100-110 % used)"; warned = 1 }
    else if (life >= 9) { print "WARN: over 80 % of rated life used"; warned = 1 }
    # BKOPS_STATUS 0x03: the chip is behind on internal maintenance, so writes can stall (17/11 timeouts).
    if (k == "0x03") { print "WARN: background operations critical (BKOPS_STATUS 0x03), expect write stalls"; warned = 1 }
    if (!warned) print "OK: wear indicators below warning levels (they do not predict controller timeouts)"
  }
  function hex2dec(h) { return index("0123456789abcdef", tolower(substr(h, 3, 1))) * 16 - 16 + index("0123456789abcdef", tolower(substr(h, 4, 1))) - 1 }
'
