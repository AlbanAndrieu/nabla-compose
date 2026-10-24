#!/usr/bin/env bash
# Repair only currently unreadable Prometheus YAML rules. Never touch TSDB/WAL.
set -euo pipefail
umask 077

MODE=--check
EXPECTED=""
ACK=""
usage() {
  printf 'Usage: sudo bash %s --check | --apply --expected-unreadable N --acknowledge I_ACCEPT_PROMETHEUS_RULES_PERMISSION_REPAIR\n' "$0" >&2
}
while (($#)); do
  case "$1" in
    --check|--apply) MODE="$1"; shift ;;
    --expected-unreadable)
      (($# >= 2)) || { usage; exit 2; }
      EXPECTED="$2"; shift 2 ;;
    --acknowledge)
      (($# >= 2)) || { usage; exit 2; }
      ACK="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
fail() { printf 'BLOCKED Prometheus rules: %s\n' "$*" >&2; exit 1; }
(( EUID == 0 )) || fail 'sudo is required for effective identity tests'
if [[ "$MODE" == --apply ]]; then
  [[ "$ACK" == 'I_ACCEPT_PROMETHEUS_RULES_PERMISSION_REPAIR' ]] ||
    fail 'explicit scoped repair acknowledgement required'
  [[ "$EXPECTED" =~ ^[1-9][0-9]*$ ]] ||
    fail '--expected-unreadable must be a positive reviewed count'
else
  [[ -z "$EXPECTED" && -z "$ACK" ]] ||
    fail 'apply flags are not valid with --check'
fi

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
CONFIG_DIR="${ROOT}/apps/prometheus"
RULES="${CONFIG_DIR}/rules"
for binary in docker getent cut find stat chmod chgrp setpriv; do
  command -v "$binary" >/dev/null 2>&1 || fail "missing $binary"
done
[[ -d "$CONFIG_DIR" && ! -L "$CONFIG_DIR" &&
   -d "$RULES" && ! -L "$RULES" ]] || fail 'unsafe or absent config/rules directory'
apps_gid="$(getent group apps | cut -d: -f3)" ||
  fail 'TrueNAS apps group missing'
[[ "$apps_gid" == 568 ]] || fail 'unexpected TrueNAS apps group GID'
runtime_user="$(docker inspect prometheus --format '{{.Config.User}}' 2>/dev/null)" ||
  fail 'Prometheus container missing'
[[ "$runtime_user" == '568:568' ]] || fail 'Prometheus not running as UID:GID 568:568'
mount="$(docker inspect prometheus --format '{{range .Mounts}}{{if eq .Destination "/etc/prometheus"}}{{println .Source}}{{end}}{{end}}' 2>/dev/null)" ||
  fail 'cannot inspect Prometheus configuration bind'
[[ "$mount" == "$CONFIG_DIR" ]] || fail 'Prometheus bind source drifted'
[[ -z "$(find "$RULES" -type l -print -quit 2>/dev/null)" ]] ||
  fail 'symlink inside rules; refusing mutation'

declare -a denied=()
files=0
dirs=0
while IFS= read -r -d '' folder; do
  dirs=$((dirs + 1))
  setpriv --reuid 568 --regid 568 --clear-groups /usr/bin/test -x "$folder" ||
    fail 'rule subdirectory not traversable by 568:568'
done < <(find "$RULES" -type d -print0)
while IFS= read -r -d '' file; do
  files=$((files + 1))
  [[ -f "$file" && ! -L "$file" ]] || fail 'unsafe YAML rules file'
  if ! setpriv --reuid 568 --regid 568 --clear-groups \
      /usr/bin/test -r "$file"; then
    denied+=("$file")
  fi
done < <(find "$RULES" -type f \( -name '*.yml' -o -name '*.yaml' \) -print0)
printf 'rules_total=%d dirs=%d unreadable=%d identity=568:568\n' \
  "$files" "$dirs" "${#denied[@]}"
if [[ "$MODE" == --check ]]; then
  for index in "${!denied[@]}"; do
    stat -c "inaccessible_index=$((index + 1)) uid=%u gid=%g mode=%a type=%F" \
      -- "${denied[$index]}"
  done
  if (("${#denied[@]}" > 0)); then
    printf 'BLOCKED: %d rule files need explicit reviewed repair\n' "${#denied[@]}" >&2
    exit 1
  fi
  printf 'OK: all rule files readable under UID/GID 568\n'
  exit 0
fi

(("${#denied[@]}" == EXPECTED)) ||
  fail 'unreadable file count drifted since operator reviewed it'
# File-by-file only: preserve owner and inode, do not touch readable files.
for index in "${!denied[@]}"; do
  file="${denied[$index]}"
  [[ -f "$file" && ! -L "$file" ]] || fail 'rule file type changed'
  inode="$(stat -c '%d:%i' -- "$file")"
  chgrp -- 568 "$file"
  chmod 0640 -- "$file"
  [[ "$(stat -c '%d:%i:%g:%a' -- "$file")" == "${inode}:568:640" ]] ||
    fail 'post-repair inode/GID/mode check failed'
  setpriv --reuid 568 --regid 568 --clear-groups /usr/bin/test -r "$file" ||
    fail 'ZFS ACL still denies 568; inspect ACL privately, no recursive changes'
  printf 'repaired_index=%d group=568 mode=0640 effective_read=ok\n' "$((index + 1))"
done
printf 'OK: only %d unreadable rules repaired; no restart or data changes\n' "${#denied[@]}"
