#!/usr/bin/env bash
# Safely recover an isolated PR #274 worktree after /tmp has been cleared.
# Operates only on Git metadata and a new, private workstation directory.
# Does not modify the primary checkout, restart services, or deploy anything.
set -Eeuo pipefail
umask 077

BRANCH='fix/homelab-operator-diagnostics-followup-20261024'
ACTION='check'
PFSENSE=false

usage() {
  cat <<'EOF'
Usage: bash scripts/workstation/run-pr274-after-reboot.sh --check [--with-pfsense]
       bash scripts/workstation/run-pr274-after-reboot.sh --prepare-only

Creates a unique, persistent detached worktree for PR #274 and pins its commit.
--check         Run local pfSense contracts and WhatsApp Web checks.
--with-pfsense  Also run read-only pfSense SSH diagnostics. Requires --check.
--prepare-only  Fetch and create the worktree without running diagnostics.

Optional environment: NABLA_COMPOSE_REPO, NABLA_WORKTREES_ROOT.
Never run this script with sudo. It does not change an existing checkout.
EOF
}

if (($# == 0)); then usage >&2; exit 2; fi
while (($#)); do
  case "$1" in
    --check) ACTION='check' ;;
    --prepare-only) ACTION='prepare' ;;
    --with-pfsense) PFSENSE=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done
if [[ "$ACTION" == prepare && "$PFSENSE" == true ]]; then
  echo 'ERROR: --with-pfsense requires --check' >&2
  exit 2
fi
if (( EUID == 0 )); then
  echo 'ERROR: run from the workstation as an ordinary user, not root' >&2
  exit 2
fi

repo="${NABLA_COMPOSE_REPO:-}"
if [[ -z "$repo" ]]; then
  for candidate in "$HOME/w/nabla-compose" "$HOME/work/nabla-compose" "$HOME/nabla-compose"; do
    if [[ -d "$candidate/.git" || -f "$candidate/.git" ]]; then
      repo="$candidate"
      break
    fi
  done
fi
if [[ -z "$repo" || ! -d "$repo" ]]; then
  echo 'ERROR: nabla-compose checkout not found; set NABLA_COMPOSE_REPO' >&2
  exit 2
fi
repo="$(cd -- "$repo" && pwd -P)"
if ! root="$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null)"; then
  echo 'ERROR: the checkout is not a Git worktree' >&2
  exit 2
fi
if [[ "$(cd -- "$root" && pwd -P)" != "$repo" ]]; then
  echo 'ERROR: NABLA_COMPOSE_REPO must point to the repository root' >&2
  exit 2
fi
remote_url="$(git -C "$repo" config --get remote.origin.url || true)"
case "$remote_url" in
  git@github.com:AlbanAndrieu/nabla-compose|git@github.com:AlbanAndrieu/nabla-compose.git|\
  https://github.com/AlbanAndrieu/nabla-compose|https://github.com/AlbanAndrieu/nabla-compose.git|\
  ssh://git@github.com/AlbanAndrieu/nabla-compose|ssh://git@github.com/AlbanAndrieu/nabla-compose.git)
    ;;
  *) echo 'ERROR: origin does not reference AlbanAndrieu/nabla-compose' >&2; exit 2 ;;
esac
for required in git mktemp flock; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "ERROR: missing command: $required" >&2
    exit 2
  fi
done
if [[ "$ACTION" == check ]] && ! command -v just >/dev/null 2>&1; then
  echo 'ERROR: just is missing; cannot run the local checks' >&2
  exit 2
fi

root_dir="${NABLA_WORKTREES_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/nabla/worktrees}"
if [[ "$root_dir" != /* || "$root_dir" == / || "$root_dir" == "$repo" ]]; then
  echo 'ERROR: worktree storage must be a dedicated absolute directory' >&2
  exit 2
fi
mkdir -p -- "$root_dir"
root_dir="$(cd -- "$root_dir" && pwd -P)"
if [[ "$repo" == "$root_dir"/* || "$root_dir" == "$repo"/* ]]; then
  echo 'ERROR: worktree storage must be outside the Git checkout' >&2
  exit 2
fi

# The operator may have submodule and untracked changes. Never reset or clean.
echo "source_checkout=$repo"
echo 'source_status_start'
git -C "$repo" status --short
echo 'source_status_end'

# A lock prevents parallel agents racing on the shared origin tracking ref.
exec 9>"$root_dir/.pr274-worktree.lock"
flock -x 9
expected="${NABLA_PR274_EXPECTED_SHA:-}"
if [[ -z "$expected" ]]; then
  git -C "$repo" -c submodule.recurse=false fetch --no-tags --no-recurse-submodules \
    origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
elif [[ ! "$expected" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'ERROR: NABLA_PR274_EXPECTED_SHA must be a full, verified commit SHA' >&2
  exit 2
fi
sha="$(git -C "$repo" rev-parse --verify "refs/remotes/origin/$BRANCH^{commit}")"
if [[ -n "$expected" && "$sha" != "$expected" ]]; then
  echo 'ERROR: tracked PR head changed; fetch and retry the bootstrap' >&2
  exit 2
fi
worktree="$(mktemp -d "$root_dir/pr274-XXXXXXXX")"
# Git accepts a freshly created empty directory as the worktree destination.
git -C "$repo" -c submodule.recurse=false worktree add --detach "$worktree" "$sha"
flock -u 9

echo "worktree=$worktree"
echo "pr274_head=$sha"
if [[ "$ACTION" == prepare ]]; then
  echo 'RESULT=PREPARED; no tests or pfSense probes executed'
  exit 0
fi

cd -- "$worktree"
echo '=== Local checks (no GitHub Actions) ==='
just pfsense-unbound-wifi-test
just whatsapp-web-path-check
if [[ "$PFSENSE" == true ]]; then
  echo '=== pfSense read-only SSH evidence ==='
  bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check
fi
printf 'RESULT=PASS pr274_head=%s worktree=%s\n' "$sha" "$worktree"
