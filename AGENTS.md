# Agent instructions

Keep context small and changes scoped.

## Before editing

1. Inspect `git status`, the task, and only relevant files.
2. Prefer targeted search (`rg`, `git diff`, `git ls-files`) over recursive repository reads.
3. Do not inspect submodules, generated files, caches, reports, lockfiles, or vendored trees unless the task requires them.
4. Reuse existing Compose patterns and CI conventions; do not introduce a new tool when an existing one covers the check.

## Validation

Before committing, run pre-commit on changed files. Before pushing, run the installed pre-push hook. For Compose changes, validate only changed Compose files with `docker compose config --quiet --no-interpolate --no-env-resolution`.

Do not start the homelab stack in order to validate configuration. Do not run MegaLinter locally unless diagnosing a CI-specific failure.

## Changes

Make the smallest safe patch. Fix deterministic formatter/linter output directly instead of reasoning around it. Never commit secrets. Keep GitHub Actions pinned to commit SHAs and use least-privilege permissions.
