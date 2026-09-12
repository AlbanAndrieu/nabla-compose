#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP_FILTER="${2:-}"

case "${MODE}" in
  --check | --apply) ;;
  *)
    printf 'ERROR: usage: %s [--check|--apply] [app]\n' "$0" >&2
    exit 1
    ;;
esac

if [[ -n "${APP_FILTER}" && ! "${APP_FILTER}" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  printf 'ERROR: invalid app filter: %s\n' "${APP_FILTER}" >&2
  exit 1
fi

bash scripts/truenas/bootstrap-repository-storage.sh "${MODE}" "${APP_FILTER}"
bash scripts/truenas/bootstrap-repository-env-files.sh "${MODE}" "${APP_FILTER}"
