# Agent instructions

Keep context small and changes scoped.

## Before editing

1. Inspect `git status`, the task, and only relevant files.
2. Prefer targeted search (`rg`, `git diff`, `git ls-files`) over recursive repository reads.
3. Do not inspect submodules, generated files, caches, reports, lockfiles, or vendored trees unless the task requires them.
4. Reuse existing Compose patterns and CI conventions; do not introduce a new tool when an existing one covers the check.

## Validation

For a focused change, run the closest relevant formatter/linter first.

Before considering a substantial change complete, run the repository quality gate:

```bash
bash scripts/quality-gate.sh
```

The gate runs the repository pre-commit policy against the branch diff. This includes the configured safe formatters and base linters such as Biome, Prettier, shell checks, GitHub workflow validation, Hadolint, Gitleaks, and filesystem/config validation where applicable.

For Compose changes, the installed pre-push hook additionally validates changed Compose files with:

```bash
docker compose config --quiet --no-interpolate --no-env-resolution
```

Do not start the homelab stack in order to validate configuration. Do not run MegaLinter locally unless diagnosing a CI-specific failure.

## Mandatory agent push policy

Agents must never push immediately after changing files.

Before every `git push`:

1. Run `bash scripts/quality-gate.sh`.
2. Fix every formatter, linter, pre-commit, workflow, configuration, or security-check failure caused by the change.
3. If the gate modifies files, review and commit those changes.
4. Run `bash scripts/quality-gate.sh` again until it exits successfully with a clean working tree.
5. Verify `git status --short` is empty.
6. Only then run `git push`.

The repository also installs `quality-gate-pre-push`, which invokes the same gate automatically as a final safety net.

Never bypass repository hooks with `git push --no-verify`. Never weaken or disable formatter, lint, security, or validation rules merely to make a push or CI build pass.

## Changes

Make the smallest safe patch. Fix deterministic formatter/linter output directly instead of reasoning around it. Never commit secrets. Keep GitHub Actions pinned to commit SHAs and use least-privilege permissions.

## Completion

Report:

1. what changed;
2. checks executed;
3. unresolved failures or risks.
