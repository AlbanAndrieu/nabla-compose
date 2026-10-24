#!/usr/bin/env bash
# One-shot PR #274 read-only verification in a disposable, isolated Git worktree.
# Never executes git pull/reset, changes the operator checkout, accesses PIN or writes PIV.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf 'Execute with bash; never source this script.\n' >&2
  return 2
fi
set -Eeuo pipefail
umask 077

repo='/tmp/nabla-yubikey-pr259'
evidence_dir="$HOME/.local/share/nabla/yubikey-f9-public"
remote='https://github.com/AlbanAndrieu/nabla-compose.git'
branch='fix/homelab-operator-diagnostics-followup-20261024'
observed_f9='6C:6E:14:0A:69:81:14:C3:51:14:0C:1B:68:C4:B1:16:A7:D9:B4:49:29:76:62:39:2F:61:F1:78:54:90:34:DF'
expected_root='63ece914e54dd87915f34033c85af4c0696ba1512f8add66ced738331207b546'
root_url='https://developers.yubico.com/PKI/yubico-piv-ca-1.pem'
usage() {
  printf 'Usage: bash run-age-yubikey-pr274-readonly.sh [--repo /tmp/nabla-yubikey-pr259] [--evidence-dir PATH]\n'
  printf 'Fetch PR #274 and create isolated worktree; test offline, then check saved public F9 against pinned root.\n'
  printf 'Does not git pull, switch operator checkout, write PIV, request PIN or change SOPS.\n'
}
while (($#)); do
  case "$1" in
    --repo)
      (($# >= 2)) || { usage >&2; exit 2; }
      repo="$2"; shift 2 ;;
    --evidence-dir)
      (($# >= 2)) || { usage >&2; exit 2; }
      evidence_dir="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
# Test harness may substitute a local bare repo, never on a production invocation.
if [[ "${NABLA_YUBIKEY_TEST_MODE:-0}" == 1 && -n "${NABLA_YUBIKEY_TEST_REMOTE:-}" ]]; then
  remote="$NABLA_YUBIKEY_TEST_REMOTE"
fi

die() { printf 'NO-GO: %s\n' "$*" >&2; exit 3; }
command -v git >/dev/null || die 'Git unavailable'
command -v flock >/dev/null || die 'flock unavailable'
[[ -d "$repo" ]] || die "Repository missing: $repo"
repo_root="$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null)" || die "Not a Git worktree: $repo"
[[ "$repo_root" == "$(cd -- "$repo" && pwd -P)" ]] || die 'Repository path must be its worktree root'
[[ -d "$HOME" ]] || die 'HOME unavailable'
worktree_base="$HOME/.local/share/nabla/agent-worktrees"
[[ ! -L "$worktree_base" ]] || die 'Agent worktree directory must not be a symlink'
mkdir -p -m 0700 -- "$worktree_base"
[[ -d "$worktree_base" ]] || die 'Unable to create private agent worktree directory'

# Advisory lock only protects this script's fetch/worktree metadata updates.
exec 9>"$worktree_base/.pr274-fetch.lock"
flock -w 20 9 || die 'Another agent has the PR #274 fetch lock'
original="$(git -C "$repo" rev-parse --verify HEAD)" || die 'Cannot resolve source HEAD'
if [[ -n "$(git -C "$repo" status --porcelain --untracked-files=normal)" ]]; then
  printf 'WARN: original checkout has changes; leaving all files untouched\n'
fi
printf 'INFO: source checkout %s at %.12s (unchanged, even if detached)\n' "$repo" "$original"
printf 'INFO: git pull skipped: explicit snapshot fetch is safe for detached HEAD\n'

# Resolve exactly one branch tip from the server, then verify it exists locally.
ref="refs/heads/$branch"
response="$(git ls-remote --exit-code "$remote" "$ref")" || die 'Remote branch lookup failed; no checkout changed'
IFS=$'\t' read -r sha ref_name <<< "$response"
[[ "$sha" =~ ^[0-9a-f]{40}$ && "$ref_name" == "$ref" ]] || die 'Unexpected remote branch response'
if ! git -C "$repo" cat-file -e "$sha^{commit}" 2>/dev/null; then
  git -C "$repo" fetch --no-tags --no-write-fetch-head "$remote" "$ref" || die 'Fetch failed; no checkout changed'
fi
git -C "$repo" cat-file -e "$sha^{commit}" || die 'Verified remote commit not present after fetch'
# Never rely on FETCH_HEAD: other agents may fetch in parallel.

tmp_root=""
parent="$(mktemp -d "$worktree_base/pr274.XXXXXXXX")" || die 'Unable to reserve isolated worktree'
worktree="$parent/source"
cleanup() {
  local status=$?
  trap - EXIT
  if [[ -n "${tmp_root:-}" && -f "$tmp_root" ]]; then
    rm -f -- "$tmp_root"
  fi
  # Never force-delete a worktree. Preserve any unexpected file changes for inspection.
  if [[ -d "${worktree:-}" ]] && git -C "$worktree" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [[ -z "$(git -C "$worktree" status --porcelain --untracked-files=normal 2>/dev/null)" ]]; then
      git -C "$repo" worktree remove "$worktree" >/dev/null 2>&1 || \
        printf 'WARN: could not remove clean isolated worktree: %s\n' "$worktree" >&2
    else
      printf 'WARN: isolated worktree has changed; preserved at %s\n' "$worktree" >&2
    fi
  fi
  if [[ -d "${parent:-}" ]]; then
    rmdir "$parent" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT

git -C "$repo" worktree add --detach "$worktree" "$sha" >/dev/null || die 'Failed to create isolated worktree'
flock -u 9
printf 'INFO: isolated PR snapshot %.12s at %s\n' "$sha" "$worktree"
[[ "$(git -C "$worktree" rev-parse HEAD)" == "$sha" ]] || die 'Snapshot SHA differs from remote branch tip'
[[ -f "$worktree/scripts/workstation/verify-age-yubikey-offline.sh" && \
   -f "$worktree/scripts/workstation/verify-age-yubikey-f9-root-offline.py" ]] || \
  die 'Required verification scripts missing from pinned PR SHA'

# The offline gate is already hardware-free; abort on any failure.
(cd -- "$worktree" && bash scripts/workstation/verify-age-yubikey-offline.sh) || die 'Offline gate failed; F9 validation not attempted'

[[ ! -L "$evidence_dir" ]] || die 'Evidence directory is a symlink'
mkdir -p -m 0700 -- "$evidence_dir"
f9="$evidence_dir/f9-22916048.pem"
root="$evidence_dir/yubico-piv-ca-1.pem"
[[ ! -L "$f9" && ! -L "$root" ]] || die 'Refusing symlink evidence'
if [[ ! -f "$f9" ]]; then
  # Explicitly read-only YubiKey export. Never overwrite existing certificates.
  printf 'INFO: stored public F9 missing, attempting one read-only export of secondary 22916048\n'
  bash "$worktree/scripts/workstation/inspect-age-yubikey-f9-chain.sh" \
    --serial 22916048 --save-public-f9 "$f9" || die 'Read-only F9 export failed'
fi
if [[ ! -f "$root" ]]; then
  command -v curl >/dev/null || die 'curl unavailable to acquire public root'
  command -v openssl >/dev/null || die 'openssl unavailable to fingerprint public root'
  tmp_root="$(mktemp "$evidence_dir/.yubico-root.XXXXXXXX")" || die 'Unable to stage public root'
  # tmp is a public certificate downloaded over HTTPS, not an executable.
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
    --connect-timeout 5 --max-time 20 --output "$tmp_root" "$root_url" || die 'Official Yubico root download failed'
  actual_root="$(openssl x509 -in "$tmp_root" -outform DER | sha256sum | cut -d' ' -f1)" || die 'Cannot fingerprint Yubico root'
  if [[ "$actual_root" != "$expected_root" ]]; then
    rm -f -- "$tmp_root"
    die 'Official root fingerprint mismatches pinned SHA256'
  fi
  (set -C; cat "$tmp_root" >"$root") || die 'Cannot save root without clobbering existing evidence'
  rm -f -- "$tmp_root"
  tmp_root=""
  printf 'INFO: pinned Yubico legacy public root downloaded and verified\n'
fi
python_bin="$HOME/.local/share/nabla/piv-sdk-venv/bin/python"
if [[ "${NABLA_YUBIKEY_TEST_MODE:-0}" == 1 && -n "${NABLA_YUBIKEY_TEST_PYTHON:-}" ]]; then
  python_bin="$NABLA_YUBIKEY_TEST_PYTHON"
fi
[[ -x "$python_bin" ]] || die 'Isolated PIV SDK Python missing'
"$python_bin" "$worktree/scripts/workstation/verify-age-yubikey-f9-root-offline.py" \
  --serial 22916048 --firmware 5.4.3 \
  --f9 "$f9" --root "$root" --expected-f9-sha256 "$observed_f9" || \
  die 'Public F9 certificate failed pinned legacy-root validation'
printf 'PASS: snapshot %.12s, offline gate and observed secondary F9 public trust\n' "$sha"
printf 'NO-GO: no PIN, AES256 authentication, PIV82 generation or SOPS mutation was authorized\n'
