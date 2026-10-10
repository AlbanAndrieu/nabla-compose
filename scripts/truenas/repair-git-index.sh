#!/usr/bin/env bash
# Bounded Git index repair for TrueNAS; do not run this script with sudo.
set -euo pipefail
MODE="$1"
case "$MODE" in
  --check|--repair|--restore-two|--stash-list|--audit) ;;
  *) printf 'Usage: bash %s --check|--repair|--restore-two|--stash-list|--audit\n' "$0" >&2; exit 2 ;;
esac
ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
[[ "$(id -un)" == albandrieu ]] || { echo "ERROR: run as albandrieu, without sudo" >&2; exit 1; }
GIT_DIR="$(git rev-parse --absolute-git-dir)"
[[ "$GIT_DIR" == "$ROOT/.git" ]] || { echo "ERROR: unexpected git dir" >&2; exit 1; }
INDEX="$GIT_DIR/index"
[[ -f "$INDEX" && ! -L "$INDEX" ]] || { echo "ERROR: missing/symlink index" >&2; exit 1; }
printf 'index=%s owner=%s mode=%s\n' "$INDEX" "$(stat -c '%U:%G' "$INDEX")" "$(stat -c '%a' "$INDEX")"
case "$MODE" in
  --check)
    [[ -w "$INDEX" && -w "$GIT_DIR" ]] || { echo "ERROR: index/directory not writable; inspect ACL" >&2; exit 1; }
    git status --short --branch
    ;;
  --repair)
    [[ "$(stat -c '%u:%G' "$INDEX")" == '0:apps' ]] || { echo "ERROR: index not root:apps; inspect before mutation" >&2; exit 1; }
    sudo chown albandrieu:apps -- "$INDEX"
    sudo chmod 0644 -- "$INDEX"
    [[ "$(stat -c '%U:%G %a' "$INDEX")" == 'albandrieu:apps 644' ]] || exit 1
    git status --short --branch
    ;;
  --restore-two)
    git restore --source=HEAD --staged --worktree --       scripts/quality/check-compose-config.sh       scripts/workstation/openclaw-auth-presence.py
    git status --short
    ;;
  --stash-list)
    git stash list --format='%gd %cr %s'
    echo "Review: git stash show --stat 'stash@{N}'"
    echo "Delete individual reviewed entry: git stash drop 'stash@{N}'"
    echo "Indices renumber after each drop; re-list first."
    ;;
  --audit)
    echo '==> Cron identity and schedule (no command contents)'
    if command -v midclt >/dev/null && command -v jq >/dev/null; then
      midclt call cronjob.query 2>/dev/null |
        jq -r '.[] | [.id, .enabled, (.user // ""), (.schedule.minute // ""), (.schedule.hour // "")] | @tsv' || true
    fi
    echo '==> Relevant processes (no arguments)'
    ps -eo pid,user,comm | awk '$3 ~ /^(git|sudo|cron|crond)$/ {print}'
    echo '==> Timer names'
    systemctl list-timers --all --no-pager --no-legend 2>/dev/null |
      awk '{print $(NF-1), $NF}' | head -40 || true
    echo '==> Sudo journal Git events (command lines redacted)'
    journalctl --since '24 hours ago' -t sudo --no-pager -q 2>/dev/null |
      grep -Ei 'COMMAND=.*git|git status' |
      sed -E 's/COMMAND=.*/COMMAND=<redacted>/' | tail -30 || true
    ;;
esac
