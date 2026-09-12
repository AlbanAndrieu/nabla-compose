#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"

case "${MODE}" in
  --check | --apply) ;;
  *)
    printf 'ERROR: usage: %s [--check|--apply]\n' "$0" >&2
    exit 1
    ;;
esac

bash scripts/truenas/bootstrap-repository-storage.sh "${MODE}"
bash scripts/truenas/bootstrap-repository-env-files.sh "${MODE}"
