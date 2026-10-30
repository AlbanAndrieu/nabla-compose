# Development environments and hook isolation

Read this reference only when dependencies, worktrees or hook environments are
part of the failure.

## Python worktrees

- Read `.python-version`, `mise.toml`, `pyproject.toml` and `uv.lock` before
  interpreting dependency failures.
- Keep one `.venv` per worktree. Share only the uv download cache.
- Use `scripts/quality/with-worktree-python.sh`; it runs locked sync without
  installing the project and reuses a dependency fingerprint.
- Never source `.envrc`, run `direnv allow`, install into global Python, change
  lockfiles for a test, or use `--break-system-packages`.
- Missing pytest/PyYAML is `BLOCKED`, not a generator regression.
- Run generators with `--check`, then targeted tests, then `agent-loop`. Run the
  complete suite only at `agent-pre-push`.

`just topology-qa` is the canonical topology path. Intentional projection
updates use `topology-artifacts-refresh` after reviewing the drift.

## Git hook environment

Git hooks export repository-location variables such as `GIT_DIR`,
`GIT_INDEX_FILE`, `GIT_WORK_TREE` and `GIT_COMMON_DIR`. Synthetic repositories
must remove them before any `git init`, `git add` or `git commit`; otherwise a
fixture can alter the caller repository.

Repository tests share this isolation through `tests/git_test_env.py` and the
`tests` package bootstrap. New test helpers must reuse it instead of open-coding
another variable list. Continue to disable inherited commit signing in fixtures
that create commits.

## Node fast path

The repository pin remains Node 24. When Node 22.x and npm 10.x are already
available, `just node22-fast` (or `npm --offline run test:fast:node22`) provides
L1 compatibility evidence. Do not run npm install/ci/npx or download tools for
this fast path. It never replaces `agent-pre-push`.
