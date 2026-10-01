#!/usr/bin/env bash
set -euo pipefail

repos="${DSOMM_BASELINE_REPOS:-AlbanAndrieu/nabla-compose}"
output="${DSOMM_BASELINE_OUTPUT:-/reports/dsomm-baseline.csv}"

[[ -n "${GH_TOKEN:-}" ]] || {
  printf 'ERROR: GH_TOKEN is required via the DSOMM runtime secret file\n' >&2
  exit 2
}

case "${output}" in
  /reports/*) ;;
  *)
    printf 'ERROR: DSOMM_BASELINE_OUTPUT must stay under /reports: %s\n' "${output}" >&2
    exit 2
    ;;
esac

mkdir -p -- "$(dirname -- "${output}")"
umask 077

if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  printf 'ERROR: GH_TOKEN is not accepted by GitHub CLI\n' >&2
  exit 2
fi

printf 'INFO: running supported + manual DSOMM inventory for %s\n' "${repos}"
printf 'y\nALL\n%s\ncsv\n%s\ny\n' "${repos}" "${output}" |
  python3 /opt/dsomm-baseline/main.py

[[ -s "${output}" ]] || {
  printf 'ERROR: DSOMM baseline did not create a non-empty report: %s\n' "${output}" >&2
  exit 1
}

chmod 0600 "${output}"
printf 'OK: DSOMM baseline report written to %s\n' "${output}"
