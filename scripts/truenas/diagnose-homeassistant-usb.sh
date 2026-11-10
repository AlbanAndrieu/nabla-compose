#!/usr/bin/env bash
# Read-only diagnosis of the USB radio dongles plugged into the TrueNAS host
# (Zigbee, Thread, Z-Wave, EnOcean, RFXtrx, Bluetooth) and of their hand-off
# to Home Assistant: USB enumeration -> serial driver -> Docker device mapping
# -> config entry that uses the device.
#
#   sudo bash scripts/truenas/diagnose-homeassistant-usb.sh [--check]
#
# Changes nothing. Prints USB vendor/product identifiers, /dev/serial/by-id
# names (they embed the dongle serial: a hardware identifier, not a secret),
# Docker device mappings and the /dev paths referenced by Home Assistant config
# entries. Never prints kernel log lines, entry titles or any other entry data.
# NABLA_HOST_ROOT points the /sys and /dev lookups at a fixture (tests only).
set -euo pipefail

if [[ $# -gt 1 || "${1:---check}" != --check ]]; then
  echo 'Usage: sudo bash scripts/truenas/diagnose-homeassistant-usb.sh [--check]' >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/diagnostic-ui.sh
source "${SCRIPT_DIR}/../lib/diagnostic-ui.sh"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"
# shellcheck source=../lib/homeassistant.sh
source "${SCRIPT_DIR}/../lib/homeassistant.sh"
diag_ui_init "${DIAG_COLOR:-auto}" "${DIAG_ICONS:-auto}" || exit 2

for cmd in docker jq readlink find python3 grep; do
  command -v "${cmd}" >/dev/null 2>&1 || {
    printf 'ERROR missing=%s\n' "${cmd}" >&2
    exit 2
  }
done

HOST_ROOT="${NABLA_HOST_ROOT:-}"
USB_SYSFS="${HOST_ROOT}/sys/bus/usb/devices"
TTY_SYSFS="${HOST_ROOT}/sys/class/tty"
SERIAL_BY_ID="${HOST_ROOT}/dev/serial/by-id"
COMPOSE_FILE="${NABLA_HA_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}/apps/homeassistant/compose.yml"
RADIO_DOMAINS='zha zwave_js enocean rfxtrx deconz mqtt otbr bluetooth homeassistant_sky_connect homeassistant_connect_zbt1 homeassistant_connect_zbt2'

declare -A USB_KIND=() TTY_BY_ID=() TTY_USB=() MAPPED=() USED_BY=()

# Device strings are attacker-influenced (any USB gadget sets them): keep a
# conservative printable subset.
sanitize() { LC_ALL=C tr -cd 'A-Za-z0-9 ._()+/-' <<<"$1" | cut -c1-60; }
sysfs_read() {
  local value=''
  [[ -r "$1" ]] && value="$(<"$1")"
  printf '%s' "${value}"
}

# Radio kind from the USB strings first, then VID:PID. "Probable" kinds are
# generic USB-serial bridges used by many sticks: the by-id name decides.
usb_radio_kind() {
  local vid="$1" pid="$2" text="${3,,}" iface_classes="$4"
  case "${text}" in
  *enocean*)
    echo enocean
    return
    ;;
  *rfxtrx* | *rfxcom*)
    echo rfxtrx
    return
    ;;
  *conbee* | *raspbee*)
    echo zigbee
    return
    ;;
  *skyconnect* | *zbt-1* | *zbt-2* | *"connect zbt"*)
    echo zigbee-thread
    return
    ;;
  *zigbee* | *zbdongle* | *cc2652* | *cc2531* | *slzb*)
    echo zigbee
    return
    ;;
  *z-wave* | *zwave* | *z-stick* | *zst10* | *zst39*)
    echo zwave
    return
    ;;
  *bluetooth*)
    echo bluetooth
    return
    ;;
  esac
  case "${vid}:${pid}" in
  1cf1:0030) echo zigbee ;;       # dresden elektronik ConBee II
  10c4:8a2a) echo zigbee-zwave ;; # Nortek HUSBZB-1
  0658:0200) echo zwave ;;        # Sigma Designs / Aeotec Z-Stick
  10c4:ea60 | 1a86:55d4 | 1a86:7523 | 0403:6001 | 0403:6015)
    echo serial-radio-probable
    ;; # CP210x, CH9102/CH340, FTDI bridges
  *)
    if [[ " ${iface_classes} " == *" e0 "* ]]; then echo bluetooth; else echo other; fi
    ;;
  esac
}

usb_parent_of_tty() {
  local path
  path="$(readlink -f -- "${TTY_SYSFS}/$1/device" 2>/dev/null)" || return 1
  while [[ -n "${path}" && "${path}" != / ]]; do
    if [[ -r "${path}/idVendor" ]]; then
      printf '%s\n' "${path##*/}"
      return 0
    fi
    path="${path%/*}"
  done
  return 1
}

container_name_of_pid() {
  local id
  id="$(grep -oE '[0-9a-f]{64}' "/proc/$1/cgroup" 2>/dev/null | head -n 1 || true)"
  [[ -n "${id}" ]] || {
    echo host
    return
  }
  docker inspect --type container --format '{{.Name}}' "${id}" 2>/dev/null | sed 's#^/##' || echo "container:${id:0:12}"
}

# "name" for every process holding the device open (root only, real host only).
tty_holders() {
  local device="$1" pid
  [[ -z "${HOST_ROOT}" && "${EUID}" -eq 0 ]] || return 1
  { find /proc -maxdepth 3 -path '/proc/[0-9]*/fd/*' -lname "${device}" 2>/dev/null || true; } |
    awk -F/ '{print $3}' | sort -u |
    while read -r pid; do
      printf '%s(%s)\n' "$(container_name_of_pid "${pid}")" "$(sysfs_read "/proc/${pid}/comm")"
    done | sort -u | paste -sd ' ' -
}

rdev_of() { python3 -I -c 'import os,sys; s=os.stat(sys.argv[1]); print(f"{os.major(s.st_rdev)}:{os.minor(s.st_rdev)}")' "$1"; }

diag_section '1/5' 'USB devices on the host (no serial numbers)'
radio_count=0 other_count=0
for dev in "${USB_SYSFS}"/*; do
  [[ -r "${dev}/idVendor" && -r "${dev}/idProduct" ]] || continue
  name="${dev##*/}"
  vid="$(sysfs_read "${dev}/idVendor")"
  pid="$(sysfs_read "${dev}/idProduct")"
  class="$(sysfs_read "${dev}/bDeviceClass")"
  [[ "${vid}" == 1d6b || "${class}" == 09 ]] && continue
  iface_classes=''
  for iface in "${dev}/${name}":*; do
    [[ -r "${iface}/bInterfaceClass" ]] && iface_classes+=" $(sysfs_read "${iface}/bInterfaceClass")"
  done
  manufacturer="$(sanitize "$(sysfs_read "${dev}/manufacturer")")"
  product="$(sanitize "$(sysfs_read "${dev}/product")")"
  kind="$(usb_radio_kind "${vid}" "${pid}" "${manufacturer} ${product}" "${iface_classes}")"
  if [[ "${kind}" == other ]]; then
    other_count=$((other_count + 1))
    continue
  fi
  USB_KIND["${name}"]="${kind}"
  radio_count=$((radio_count + 1))
  printf 'usb=%s id=%s:%s kind=%s manufacturer="%s" product="%s"\n' \
    "${name}" "${vid}" "${pid}" "${kind}" "${manufacturer:--}" "${product:--}"
done
printf 'radio_candidates=%s other_usb_devices=%s\n' "${radio_count}" "${other_count}"
if ((radio_count == 0)); then
  diag_warn 'No USB radio detected on this host: check the plug, a powered hub, or whether the dongle is passed to a VM instead'
fi

diag_section '2/5' 'Serial device nodes and kernel drivers'
tty_count=0
for link in "${SERIAL_BY_ID}"/*; do
  [[ -L "${link}" ]] || continue
  target="$(readlink -f -- "${link}")"
  tty="${target##*/}"
  driver="$(basename -- "$(readlink -f -- "${TTY_SYSFS}/${tty}/device/driver" 2>/dev/null || echo unknown)")"
  usb="$(usb_parent_of_tty "${tty}" || echo unknown)"
  by_id="/dev/serial/by-id/${link##*/}"
  TTY_BY_ID["/dev/${tty}"]="${by_id}"
  TTY_USB["/dev/${tty}"]="${usb}"
  tty_count=$((tty_count + 1))
  printf 'by_id=%s tty=/dev/%s driver=%s usb=%s kind=%s\n' \
    "${by_id}" "${tty}" "${driver}" "${usb}" "${USB_KIND[${usb}]:-unclassified}"
done
printf 'serial_nodes=%s\n' "${tty_count}"
for usb in "${!USB_KIND[@]}"; do
  [[ "${USB_KIND[${usb}]}" == bluetooth ]] && continue
  bound=0
  for tty in "${!TTY_USB[@]}"; do
    [[ "${TTY_USB[${tty}]}" == "${usb}" ]] && bound=1
  done
  ((bound)) || diag_fail "USB radio ${usb} (${USB_KIND[${usb}]}) has no serial node: kernel driver missing or not bound"
done
if command -v journalctl >/dev/null 2>&1 && [[ -z "${HOST_ROOT}" ]]; then
  kernel_log="$(journalctl -k -b --no-pager -o cat 2>/dev/null || true)"
  usb_drops="$(grep -cE 'USB disconnect' <<<"${kernel_log}" || true)"
  tty_drops="$(grep -cE 'now disconnected from tty' <<<"${kernel_log}" || true)"
  # Counts only: kernel lines carry serial numbers and topology.
  printf 'kernel_usb_disconnects_since_boot=%s serial_disconnects_since_boot=%s\n' "${usb_drops}" "${tty_drops}"
  ((tty_drops == 0)) || diag_warn 'A serial adapter dropped since boot: check cable, power, and use a USB 2.0 extension away from USB 3 ports (2.4 GHz interference)'
else
  diag_unknown 'Kernel USB disconnect history unavailable (journalctl missing or fixture mode)'
fi

diag_section '3/5' 'Home Assistant container device mapping'
cid="$(ha_find_container || true)"
running=0
if [[ -z "${cid}" ]]; then
  diag_fail "Home Assistant container not found (apps ${HA_APP_ID} / ${HA_NATIVE_APP_ID}); set NABLA_HA_CONTAINER"
else
  docker inspect --type container --format 'container={{.Name}} status={{.State.Status}} privileged={{.HostConfig.Privileged}} network_mode={{.HostConfig.NetworkMode}}' "${cid}"
  [[ "$(docker inspect --type container --format '{{.State.Status}}' "${cid}")" == running ]] && running=1
  ((running)) || diag_warn 'Container not running: in-container checks skipped'
  [[ "$(docker inspect --type container --format '{{.HostConfig.Privileged}}' "${cid}")" == false ]] ||
    diag_warn 'Privileged container: every host device is visible; replace with explicit devices: entries'
  mappings="$(docker inspect --type container --format '{{json .HostConfig.Devices}}' "${cid}" |
    jq -r '.[]? | [.PathOnHost, .PathInContainer, (.CgroupPermissions // "")] | @tsv')"
  [[ -n "${mappings}" ]] || diag_info 'No device is mapped into the container'
  while IFS=$'\t' read -r host_path container_path perms; do
    [[ -n "${host_path}" ]] || continue
    printf 'mapping host=%s container=%s permissions=%s\n' "${host_path}" "${container_path}" "${perms}"
    case "${host_path}" in
    /dev/serial/by-id/*) ;;
    /dev/ttyUSB* | /dev/ttyACM*) diag_warn "Mapping ${host_path} depends on enumeration order: use its /dev/serial/by-id path" ;;
    esac
    if [[ ! -e "${HOST_ROOT}${host_path}" ]]; then
      diag_fail "Mapped host device ${host_path} is absent (dongle unplugged or renamed)"
      continue
    fi
    resolved="$(readlink -f -- "${HOST_ROOT}${host_path}")"
    MAPPED["${resolved#"${HOST_ROOT}"}"]="${container_path}"
    if ((running)) && [[ -z "${HOST_ROOT}" ]]; then
      inner="$(docker exec "${cid}" python3 -I -c 'import os,sys; s=os.stat(sys.argv[1]); print(f"{os.major(s.st_rdev)}:{os.minor(s.st_rdev)}")' "${container_path}" 2>/dev/null || true)"
      outer="$(rdev_of "${host_path}" 2>/dev/null || true)"
      if [[ -z "${inner}" ]]; then
        diag_fail "${container_path} is missing inside the container"
      elif [[ "${inner}" != "${outer}" ]]; then
        diag_fail "${container_path} points to device ${inner} but the host node is now ${outer}: the dongle re-enumerated, restart the App"
      else
        diag_ok "${container_path} present in the container (device ${inner})"
      fi
    fi
  done <<<"${mappings}"
fi
if [[ -r "${COMPOSE_FILE}" ]]; then
  printf 'repo_compose_devices_blocks=%s\n' "$(grep -cE '^[[:space:]]+devices:' "${COMPOSE_FILE}" || true)"
fi

diag_section '4/5' 'Home Assistant integrations using a device (paths only)'
if entries="$(ha_config_entries_offline 2>/dev/null)"; then
  device_entries=0
  while IFS=$'\t' read -r domain disabled source paths; do
    [[ -n "${paths}" ]] || continue
    device_entries=$((device_entries + 1))
    printf 'entry domain=%s status=%s source=%s devices=%s\n' "${domain}" "${disabled}" "${source}" "${paths}"
    IFS=',' read -r -a entry_paths <<<"${paths}"
    for path in "${entry_paths[@]}"; do
      USED_BY["${path}"]="${domain}"
      case "${path}" in
      /dev/ttyUSB* | /dev/ttyACM*) diag_warn "Integration ${domain} uses ${path}: prefer the stable /dev/serial/by-id path" ;;
      esac
      if ((running)) && [[ "${disabled}" == enabled ]] && ! docker exec "${cid}" test -e "${path}"; then
        diag_fail "Integration ${domain} references ${path}, absent inside the container"
      fi
    done
  done <<<"${entries}"
  printf 'config_entries_with_devices=%s\n' "${device_entries}"
else
  diag_unknown "Config entries unreadable (${HA_CONFIG_DIR}/.storage/core.config_entries): run as root"
fi
token_rc=0
ha_load_token || token_rc=$?
if ((token_rc == 0)); then
  if states="$(ha_api_get /api/config/config_entries/entry |
    jq -r --arg radios "${RADIO_DOMAINS}" '
      ($radios | split(" ")) as $r
      | .[] | select(.domain as $d | $r | index($d)) | "\(.domain)\t\(.state)\t\(.disabled_by // "enabled")"')"; then
    while IFS=$'\t' read -r domain state disabled; do
      [[ -n "${domain}" ]] || continue
      printf 'entry_state domain=%s state=%s status=%s\n' "${domain}" "${state}" "${disabled}"
      if [[ "${disabled}" == enabled && "${state}" != loaded ]]; then
        diag_fail "Integration ${domain} is ${state}"
      fi
    done <<<"${states}"
  else
    diag_warn 'Home Assistant API unavailable for config entry states'
  fi
elif ((token_rc == 1)); then
  diag_info "No API token (${HA_SECRETS_FILE}, key HA_TOKEN): runtime integration states not checked"
else
  diag_fail "API token file ${HA_SECRETS_FILE} is unsafe or malformed (expected root:root 600 with HA_TOKEN=)"
fi

diag_section '5/5' 'Dongle to Home Assistant hand-off'
for tty in "${!TTY_BY_ID[@]}"; do
  by_id="${TTY_BY_ID[${tty}]}"
  kind="${USB_KIND[${TTY_USB[${tty}]}]:-unclassified}"
  container_path="${MAPPED[${tty}]:-}"
  domain="${USED_BY[${by_id}]:-${USED_BY[${tty}]:-}}"
  [[ -z "${domain}" && -n "${container_path}" ]] && domain="${USED_BY[${container_path}]:-}"
  holders="$(tty_holders "${tty}" || echo unknown)"
  printf 'dongle=%s kind=%s mapped_to=%s used_by=%s holders=%s\n' \
    "${by_id}" "${kind}" "${container_path:--}" "${domain:--}" "${holders:-none}"
  if [[ -n "${container_path}" && -n "${domain}" ]]; then
    diag_ok "${by_id} reaches Home Assistant integration ${domain}"
  elif [[ -n "${container_path}" ]]; then
    diag_warn "${by_id} is mapped but no integration uses it: add the ${kind} integration in Home Assistant"
  elif [[ -n "${holders}" && "${holders}" != unknown && "${holders}" != *homeassistant* ]]; then
    diag_info "${by_id} is held by ${holders}: Home Assistant must reach that service (MQTT or WebSocket), not the device"
  else
    diag_warn "${by_id} is not passed to Home Assistant"
    diag_info "Add to apps/homeassistant/compose.yml (service homeassistant), then redeploy the App:"
    printf '    devices:\n      - %s:%s\n' "${by_id}" "${by_id}"
  fi
done
((${#TTY_BY_ID[@]} > 0)) || diag_info 'No USB serial node: nothing to hand off'

diag_summary
((DIAG_FAILURES == 0))
