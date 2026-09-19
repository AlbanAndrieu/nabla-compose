# shellcheck shell=bash
# Shared secret-file validation helpers. Never print secret values.

secrets_fail() {
  printf 'ERROR: %s\n' "$*" >&2
  return 1
}

secrets_assert_file() {
  local file="${1:?secret file required}"
  shift || true
  [[ -f "${file}" ]] || secrets_fail "missing secret file: ${file}" || return 1
  [[ -s "${file}" ]] || secrets_fail "secret file is empty: ${file}" || return 1

  local metadata
  metadata="$(stat -c '%U:%G %a' "${file}")"
  [[ "${metadata}" == "root:root 600" ]] ||
    secrets_fail "${file} owner/mode=${metadata}; expected root:root 600" || return 1

  local key
  for key in "$@"; do
    grep -Eq "^${key}=.+$" "${file}" ||
      secrets_fail "${file} must define non-empty ${key}" || return 1
  done
}

secrets_get_value() {
  local file="${1:?secret file required}"
  local key="${2:?secret key required}"
  python3 - "${file}" "${key}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
wanted = sys.argv[2]
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key != wanted:
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        value = value[1:-1].replace("\\'", "'").replace("\\\\", "\\")
    elif len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    sys.stdout.write(value)
    raise SystemExit(0)
raise SystemExit(1)
PY
}
