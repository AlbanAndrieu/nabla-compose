#!/usr/bin/env bash
set -euo pipefail

# Update only the reviewed application submodules; never deploy or push implicitly.
ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"
MODE="${1:---check}"
MODULES=(fastapi-sample apps/nabla-site-alban)

case "${MODE}" in --check|--update) ;; *) echo "Usage: $0 [--check|--update]" >&2; exit 2;; esac
# A read-only --check should explain what blocks the update rather than
# presenting a generic error. --update still refuses all tracked dirt.
DIRTY="$(git status --porcelain --untracked-files=no)"
if [[ -n "${DIRTY}" ]]; then
  echo "superproject_dirty=true"
  git status --short --untracked-files=no
  echo "Review tracked changes, staged files and dirty submodules separately."
  for module in "${MODULES[@]}"; do
    if [[ -d "${module}" ]]; then
      if [[ -n "$(git -C "${module}" status --porcelain)" ]]; then
        echo "⚠️  Dirty submodule: ${module}"
        echo "  git -C ${module} status --short"
        echo "  # If source changes are INTENDED, stage specific files inside the child:"
        echo "  git -C ${module} add -- <reviewed-files>"
        echo "  git -C ${module} diff --cached --check"
        echo "  git -C ${module} commit -m 'fix: reviewed submodule changes [skip ci]'"
        echo "  # Only after the child commit, update the superproject gitlink:"
        echo "  git add -- ${module}"
        echo "  git diff --cached --submodule=log"
        echo "  git commit -m 'chore(submodules): record reviewed ${module} pointer [skip ci]'"
      fi
    fi
  done
  echo "No reset, stash, clean or submodule checkout was performed."
  if [[ "${MODE}" == "--update" ]]; then
    echo "Refusing to update a dirty superproject." >&2
    exit 1
  fi
  exit 2
fi
echo "superproject_dirty=false"
for module in "${MODULES[@]}"; do
  git config --file .gitmodules --get "submodule.${module}.path" >/dev/null ||
    { echo "Missing .gitmodules entry: ${module}" >&2; exit 1; }
  echo "module=${module} pinned=$(git rev-parse HEAD:"${module}")"
done
if [[ "${MODE}" == "--check" ]]; then
  echo "Read-only check complete. Use --update to fetch remote master revisions."
  exit 0
fi
for module in "${MODULES[@]}"; do
  git submodule update --init -- "${module}"
  [[ -z "$(git -C "${module}" status --porcelain)" ]] || {
    echo "Refusing dirty submodule: ${module}" >&2
    exit 1
  }
  git -C "${module}" fetch --no-tags origin master
  git -C "${module}" switch --detach "$(git -C "${module}" rev-parse origin/master)"
  echo "updated=${module} sha=$(git -C "${module}" rev-parse HEAD)"
done
git diff --submodule=log -- fastapi-sample apps/nabla-site-alban
echo "Review and commit the updated gitlinks in nabla-compose; no push or deployment performed."
