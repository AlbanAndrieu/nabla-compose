#!/usr/bin/env bash
# Workstation-only SSH-FIDO2 approval. It NEVER dispatches an apply itself.
set -euo pipefail
fail() { echo "ENTRA_SIGN_DENIED: $1" >&2; exit 2; }
[[ "${AGENT_EXECUTION_MODE:-offline}" == workstation ]] || fail "verified workstation session required"
[[ $# -eq 1 && "$1" =~ ^[0-9]+$ ]] || fail "usage: bash scripts/entra/sign-approval.sh <successful-plan-run-id>"
for bin in gh jq ssh-keygen base64; do
  command -v "$bin" >/dev/null 2>&1 || fail "missing $bin"
done
run_id="$1"
key="${ENTRA_SIGNING_KEY:-$HOME/.ssh/id_ed25519_sk_backup}"
[[ -f "$key" && -f "$key.pub" ]] || fail "expected existing SSH FIDO2 key and public key"
grep -q '^sk-ssh-ed25519@openssh.com ' "$key.pub" || fail "only hardware-backed FIDO2 ed25519 key is accepted"
out="${XDG_STATE_HOME:-$HOME/.local/state}/nabla-compose/entra-approvals/$run_id"
umask 077
mkdir -p "$out"
[[ ! -e "$out/challenge.json.sig" ]] || fail "run already signed locally, refuse duplicate"
gh run download "$run_id" --repo AlbanAndrieu/nabla-compose \
  --name "entra-challenge-$run_id" --dir "$out"
test -s "$out/challenge.json" || fail "no approval challenge artifact"
jq -e --argjson run "$run_id" --arg repo "AlbanAndrieu/nabla-compose" \
  '.run_id == $run and .repository == $repo and .schema == "nabla-entra-plan-approval/v1"' \
  "$out/challenge.json" >/dev/null || fail "wrong repository/run ID"
printf '\nReview the SANITIZED challenge below (tenant, SHA, changes, expiry):\n'
jq '{repository,sha,tenant,hcp_organization,hcp_workspace,run_id,changes,expires_at,plan_sha256}' "$out/challenge.json"
printf '\nType SIGN to use the YubiKey (no Terraform mutation): '
read -r approval
[[ "$approval" == SIGN ]] || fail "operator did not approve"
ssh-keygen -Y sign -n nabla-entra-apply -f "$key" "$out/challenge.json"
test -s "$out/challenge.json.sig" || fail "hardware did not produce a signature"
sha="$(jq -r '.sha' "$out/challenge.json")"
printf '\nHardware signature created. It is not an apply.\n'
printf 'To submit the signed apply manually, execute:\n'
printf 'gh workflow run entra-id-lab.yml -R AlbanAndrieu/nabla-compose --ref master -f operation=apply -f expected_sha=%q -f plan_run_id=%q -f signature_b64="$(base64 -w0 %q)"\n' \
  "$sha" "$run_id" "$out/challenge.json.sig"
