# Agent instructions

Keep context small and changes scoped.

## Repository bootstrap

Git hook configuration is versioned, but Git does not install repository hooks automatically after clone. On a new checkout, run:

```bash
mise run hooks
```

This explicitly installs the configured `pre-commit`, `commit-msg`, and `pre-push` hooks. CI remains the authoritative enforcement layer because local hooks can be absent or explicitly bypassed.

## Before editing

1. Inspect `git status`, the task, and only relevant files.
2. Prefer targeted search (`rg`, `git diff`, `git ls-files`) over recursive repository reads.
3. Do not inspect submodules, generated files, caches, reports, lockfiles, or vendored trees unless the task requires them.
4. Reuse existing Compose patterns and CI conventions; do not introduce a new tool when an existing one covers the check.
5. When adding, renaming, removing, or materially reconnecting a Compose service, read `.agents/skills/nabla-service-catalog/SKILL.md` and keep its `x-nabla` metadata and generated catalog contracts synchronized.

## Validation

For a focused change, run the closest relevant formatter/linter first.

Before considering a substantial change complete, and always before publishing repository changes, run:

```bash
bash scripts/quality-gate.sh
```

The gate validates files touched by the branch **and** staged, unstaged, or untracked working-tree files. It invokes the repository `pre-commit` stage, including safe formatters and base linters such as Biome, Prettier, shell checks, YAML parsing, GitHub workflow validation, Hadolint, Gitleaks, catalog generation, and Compose configuration validation where applicable.

Compose files are validated during the normal `pre-commit` stage with:

```bash
docker compose config --quiet --no-interpolate --no-env-resolution
```

This means Compose/YAML failures must be caught at commit time and again by the pre-push quality gate before CI. Do not start the homelab stack in order to validate configuration. Do not run MegaLinter locally unless diagnosing a CI-specific failure.

## Mandatory agent publish policy

Agents must never publish changes immediately after editing files.

Before every `git push`, GitHub API file update, or other remote repository mutation:

1. Run `bash scripts/quality-gate.sh` from a local checkout whenever shell access is available.
2. Fix every formatter, linter, YAML, Compose, workflow, configuration, generated-file, or security-check failure caused by the change.
3. If the gate modifies files, review and commit those changes.
4. Run `bash scripts/quality-gate.sh` again until it exits successfully with a clean working tree.
5. Verify `git status --short` is empty.
6. Only then publish the changes.

When `mise run hooks` has been run, the normal Git `pre-commit` hook validates the commit and `quality-gate-pre-push` invokes the full gate automatically before push.

An API-only agent must not silently treat remote API writes as a way to bypass local hooks. If its runtime cannot obtain or execute a checkout, it must explicitly report that limitation, reproduce the closest deterministic validations available, keep the remote patch minimal, and inspect the resulting CI immediately. It must never claim that the local quality gate passed when it was not executed.

Never bypass repository hooks with `git push --no-verify`. Never weaken or disable formatter, lint, security, YAML, Compose, or validation rules merely to make a push or CI build pass.

## Changes

Make the smallest safe patch. Fix deterministic formatter/linter output directly instead of reasoning around it. Never commit secrets. Keep GitHub Actions pinned to commit SHAs and use least-privilege permissions.

## Completion

Report:

1. what changed;
2. checks executed;
3. unresolved failures or risks.
