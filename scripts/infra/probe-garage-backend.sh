#!/usr/bin/env bash
set -euo pipefail

endpoint="${GARAGE_S3_ENDPOINT:-https://s3.int.albandrieu.com}"
bucket="${GARAGE_STATE_BUCKET:-opentofu-state}"

for command in aws cmp mktemp; do
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

export AWS_EC2_METADATA_DISABLED=true
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

tmpdir="$(mktemp -d)"
key=".nabla-preflight/${USER:-operator}-$$-$(date +%s)"
body_a="${tmpdir}/body-a"
body_b="${tmpdir}/body-b"
download="${tmpdir}/download"
conditional_err="${tmpdir}/conditional.err"

cleanup() {
  aws --endpoint-url "${endpoint}" s3api delete-object \
    --bucket "${bucket}" \
    --key "${key}" \
    >/dev/null 2>&1 || true
  rm -rf "${tmpdir}"
}
trap cleanup EXIT INT TERM

printf 'nabla-compose Garage backend probe A\n' >"${body_a}"
printf 'nabla-compose Garage backend probe B\n' >"${body_b}"

echo "🔎 checking Garage S3 backend: ${endpoint}/${bucket}"
aws --endpoint-url "${endpoint}" s3api head-bucket --bucket "${bucket}" >/dev/null

aws --endpoint-url "${endpoint}" s3api put-object \
  --bucket "${bucket}" \
  --key "${key}" \
  --body "${body_a}" \
  >/dev/null

aws --endpoint-url "${endpoint}" s3api get-object \
  --bucket "${bucket}" \
  --key "${key}" \
  "${download}" \
  >/dev/null

if ! cmp -s "${body_a}" "${download}"; then
  echo "Garage S3 round-trip content mismatch." >&2
  exit 1
fi

echo "✅ Garage state bucket read/write round-trip succeeded"

set +e
aws --endpoint-url "${endpoint}" s3api put-object \
  --bucket "${bucket}" \
  --key "${key}" \
  --body "${body_b}" \
  --if-none-match '*' \
  >/dev/null 2>"${conditional_err}"
conditional_rc=$?
set -e

if ((conditional_rc == 0)); then
  echo "⚠️  Backend accepted an overwrite guarded by If-None-Match: *."
  echo "    Native OpenTofu S3 lockfile semantics are not safe on this backend."
elif grep -Eq 'PreconditionFailed|412' "${conditional_err}"; then
  echo "✅ Backend rejected the conditional overwrite with 412 Precondition Failed."
  echo "   Re-evaluate root.hcl: the backend may now support native S3 locking."
elif grep -Eq 'Unknown options|unknown option|Invalid choice' "${conditional_err}"; then
  echo "⚠️  Installed AWS CLI cannot test --if-none-match; basic S3 round-trip is still valid."
else
  echo "⚠️  Conditional-write result was inconclusive (exit ${conditional_rc})."
  echo "    Native OpenTofu S3 locking must remain disabled until verified."
fi

aws --endpoint-url "${endpoint}" s3api delete-object \
  --bucket "${bucket}" \
  --key "${key}" \
  >/dev/null

echo "✅ Garage state bucket delete succeeded"
