# Agent instructions

This repository orchestrates the Nabla homelab with Docker Compose. Keep context small, changes scoped, and configuration secure.

## Source of truth

`AGENTS.md` is the canonical repository-wide instruction file for coding agents, including Codex and OpenCode. Tool-specific files should stay thin and add only native scoping or integration metadata; do not duplicate these instructions.

Reusable task knowledge belongs in `.agents/skills/`. Load a skill only when the task needs it.

## Before editing

1. Inspect the task, `git status`, and only relevant files.
2. Prefer targeted search (`rg`, `git diff`, `git ls-files`) over recursive repository reads.
3. Do not inspect submodules, generated files, caches, reports, lockfiles, vendored trees, or unrelated application directories unless required.
4. Reuse existing Compose, security, and CI conventions. Do not introduce a new tool when an existing one covers the check.

## Editing rules

- Make the smallest safe patch and preserve unrelated behavior.
- Never commit credentials, tokens, private keys, or generated secrets.
- Keep GitHub Actions pinned to immutable commit SHAs and use least-privilege permissions.
- Prefer Compose Specification syntax; do not add the obsolete top-level `version` key.
- Keep environment-specific values in environment/config files rather than duplicating service definitions.
- Preserve existing networks, volumes, health checks, resource limits, and dependency semantics unless the task explicitly changes them.
- Fix deterministic formatter/linter output directly instead of reasoning around it.

## Validation

Use the narrowest validation that proves the change:

- Run pre-commit on changed files before committing.
- For changed Compose files, run `docker compose config --quiet --no-interpolate --no-env-resolution` against those files.
- Before pushing, run the installed pre-push hook when available.
- Do not start the homelab stack merely to validate configuration.
- Do not run MegaLinter locally unless diagnosing a CI-specific failure.

If a required validation cannot run, report exactly what was not validated and why.

## Done

A change is complete when the requested behavior is implemented, relevant targeted checks pass, secrets are not exposed, and documentation is updated only where the change requires it.
