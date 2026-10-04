#!/usr/bin/env bash
set -euo pipefail

repos="${DSOMM_BASELINE_REPOS:-AlbanAndrieu/nabla-compose}"
output="${DSOMM_BASELINE_OUTPUT:-/reports/dsomm-baseline.csv}"
summary_output="${DSOMM_BASELINE_SUMMARY_OUTPUT:-${output%.csv}.md}"

[[ -n "${GH_TOKEN:-}" ]] || {
  printf 'ERROR: GH_TOKEN is required via the DSOMM runtime secret file\n' >&2
  exit 2
}

for report_path in "${output}" "${summary_output}"; do
  case "${report_path}" in
    /reports/*) ;;
    *)
      printf 'ERROR: DSOMM report paths must stay under /reports: %s\n' "${report_path}" >&2
      exit 2
      ;;
  esac
done

mkdir -p -- "$(dirname -- "${output}")" "$(dirname -- "${summary_output}")"
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
python3 /usr/local/bin/summarize-dsomm-baseline.py \
  "${output}" "${summary_output}" \
  --context-map /config/repository-contexts.yaml
chmod 0600 "${summary_output}"
printf 'OK: DSOMM baseline report written to %s\n' "${output}"
printf 'OK: DSOMM human-review summary written to %s\n' "${summary_output}"
