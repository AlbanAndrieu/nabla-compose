#!/usr/bin/env bash
set -euo pipefail
umask 077

if (($# != 1)); then
  echo "usage: $0 <infrastructure-dir>" >&2
  exit 2
fi

workdir="$1"
case "${workdir}" in
  infrastructure/*) ;;
  *)
    echo "Expected an infrastructure/<unit> directory, got: ${workdir}" >&2
    exit 2
    ;;
esac

for command in aws jq mktemp sha256sum; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Missing required command: ${command}" >&2
    exit 1
  fi
done

for name in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing environment variable: ${name}" >&2
    exit 1
  fi
done

endpoint="${GARAGE_S3_ENDPOINT:-https://s3.int.albandrieu.com}"
bucket="${GARAGE_STATE_BUCKET:-opentofu-state}"
relative="${workdir#infrastructure/}"
state_key="${relative%/}/tfstate.json"
unit_name="${relative//\//-}"
state_home="${XDG_STATE_HOME:-${HOME}/.local/state}"
backup_root="${NABLA_STATE_BACKUP_DIR:-${state_home}/nabla-compose/opentofu-state-backups}"
backup_dir="${backup_root}/${unit_name}"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

if [[ "${backup_root}" != /* ]]; then
  echo "NABLA_STATE_BACKUP_DIR must resolve to an absolute path." >&2
  exit 1
fi

case "${backup_root}" in
  "${repo_root}" | "${repo_root}"/*)
    echo "Refusing to store sensitive state backups inside the Git checkout: ${backup_root}" >&2
    exit 1
    ;;
esac

export AWS_EC2_METADATA_DISABLED=true
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

mkdir -p "${backup_dir}"
chmod 0700 "${backup_root}" "${backup_dir}" 2>/dev/null || true

head_err="$(mktemp)"
trap 'rm -f "${head_err}" "${tmp_state:-}"' EXIT INT TERM

set +e
aws --endpoint-url "${endpoint}" s3api head-object \
  --bucket "${bucket}" \
  --key "${state_key}" \
  >/dev/null 2>"${head_err}"
head_rc=$?
set -e

if ((head_rc != 0)); then
  if grep -Eiq '404|Not Found|NoSuchKey' "${head_err}"; then
    echo "ℹ️  no existing remote state to back up: ${state_key}"
    exit 0
  fi

  echo "Unable to verify existing remote state before apply: ${state_key}" >&2
  echo "Refusing apply because the current state cannot be backed up safely." >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
git_sha="$(git rev-parse --short HEAD 2>/dev/null || printf 'unknown')"
target="${backup_dir}/${timestamp}-${git_sha}-tfstate.json"
tmp_state="$(mktemp "${backup_dir}/.tfstate.XXXXXX")"

aws --endpoint-url "${endpoint}" s3api get-object \
  --bucket "${bucket}" \
  --key "${state_key}" \
  "${tmp_state}" \
  >/dev/null

if ! jq -e 'type == "object" and has("version") and has("serial")' "${tmp_state}" >/dev/null; then
  echo "Downloaded state does not look like a valid OpenTofu state; refusing apply." >&2
  exit 1
fi

mv "${tmp_state}" "${target}"
tmp_state=""
chmod 0600 "${target}"
sha256sum "${target}" >"${target}.sha256"
chmod 0600 "${target}.sha256"

echo "✅ remote state backup created: ${target}"
echo "   state key: ${state_key}"
