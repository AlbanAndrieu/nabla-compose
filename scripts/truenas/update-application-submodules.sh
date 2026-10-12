#!/usr/bin/env bash
set -euo pipefail

# Update only the reviewed application submodules; never deploy or push implicitly.
ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"
MODE="${1:---check}"
MODULES=(fastapi-sample apps/nabla-site-alban)

case "${MODE}" in --check|--update) ;; *) echo "Usage: $0 [--check|--update]" >&2; exit 2;; esac
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || {
  echo "Refusing to update a dirty superproject." >&2
  exit 1
}
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
