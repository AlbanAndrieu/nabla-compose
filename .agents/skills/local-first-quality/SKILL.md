---
name: local-first-quality
description: Converge formatter, lint, generated artifacts, targeted contracts and the final publication gate locally before consuming remote CI.
---

# Local-first quality

Use this skill for CI failures, quality-gate work, PR continuation, formatter/linter
fixes, or any task where remote CI should remain a safety net rather than the
edit loop.

## Principle

Use the cheapest deterministic evidence that can falsify the current patch, then
widen only after it is green:

```text
just context
  -> just preflight
  -> targeted test/config check
  -> just loop
  -> review deterministic diff
  -> commit logical batch
  -> mise run agent-pre-push
  -> one push
  -> inspect existing remote checks without rerunning them
```

Never claim the complete local gate is green unless `agent-pre-push` (or the
equivalent complete gate) actually passed on the exact published HEAD.

Use explicit evidence levels in reports:

- **L0 · static**: exact-HEAD file/config inspection only;
- **L1 · targeted**: narrow unit/contract/config checks executed;
- **L2 · loop**: deterministic fixes plus changed-file Pre-commit contracts converged;
- **L3 · publication**: full local `agent-pre-push` passed on the exact HEAD.

Only L3 may be summarized as the complete local quality gate being green.

## Iteration loop

Before installing dependencies or widening the test scope, get bounded context
and run the Git-only safety gate:

```bash
just context
just preflight
# equivalent: mise run agent-context && mise run agent-preflight
```

This catches protected-branch, stale-base, destructive-diff and executable-bit
problems before spending time on Python/tool installation. Preflight is
branch-wide; it sees the complete PR delta against the comparison base.

After one bounded edit batch, run:

```bash
mise run agent-loop
# or
just loop
```

`agent-loop` runs `scripts/agent-quality-gate.sh --loop`. Its validation
scope is deliberately limited to the uncommitted working tree, staged files and
untracked files; already-committed PR history is revalidated by preflight and
the final publication gate. It:

- preserves the branch/base guard and checks destructive/executable-bit changes
  in the current edit batch;
- regenerates deterministic service artifacts;
- converges safe formatter/autofixer hooks on changed files;
- executes pre-commit contracts selected by the changed paths;
- runs expensive topology/runtime-primitive checks only when their inputs changed;
- deliberately defers the complete repository pytest suite to the publication gate.

If a deterministic tool modifies files, review that compact diff. Keep only
changes caused by the logical batch; do not accept unrelated generated churn.

If a check fails without changing files, fix the first concrete failure. Do not
repeat the same command and do not switch to GitHub Actions for diagnosis.

## Publication gate

Once the logical batch is committed:

```bash
mise run agent-pre-push
# or
just pre-push
```

This is the authoritative local publication evidence. It reruns deterministic
fixes, the complete unit/contract suite and the canonical formatter/linter/security
gate, and requires a publication-clean superproject.

If it exits with `QG_AUTOFIX_APPLIED`, review and commit/amend only those
changes, then rerun the same local command. Do not push before it is green.

## Remote CI policy

Remote checks are evidence, not an editor:

- inspect current PR/check status before starting another improvement when useful;
- never manually rerun a workflow merely to discover deterministic formatting,
  lint or unit-test failures that are reproducible locally;
- when the task explicitly requests no CI or credits are constrained, keep
  iterative commits CI-silent (for example with the repository's accepted
  `[skip ci]` convention) and rely on the local publication gate;
- after a push, inspect only the first failing workflow/job/step and widen logs
  only when necessary;
- do not weaken hooks, tests, security checks or generated-contract validation.

## API-only fallback / source archives

When the execution environment cannot obtain a complete Git checkout:

1. pin every read/write to the exact PR branch/HEAD SHA and use optimistic file
   SHA updates so concurrent edits cannot be overwritten silently;
2. batch the smallest logical patch on the dedicated branch;
3. run source-tree-safe contracts when available. Generators should reuse
   archive-aware discovery such as `nabla_ops.compose_paths` instead of
   requiring `.git` merely to enumerate Compose files;
4. reproduce the narrowest deterministic checks possible and classify the
   evidence as L0 or L1, never L2/L3;
5. compare branch freshness and inspect existing workflow/check state without
   rerunning CI;
6. if the HEAD moves while working, refetch the touched file and reconcile
   instead of retrying a stale write;
7. disclose which complete local gates could not be executed and never label
   the PR locally green from static inspection alone.

This fallback is for continuity, not a substitute for the publication gate.

## Tooling choice

Prefer existing widely adopted tooling over new repository-specific code:

- Pre-commit for changed-file hook selection and hook environments;
- Ruff/Biome/Prettier/shfmt/ShellCheck for formatting and linting;
- pytest for Python contracts;
- Betterleaks for secret scanning;
- JSON Schema/check-jsonschema for declarative JSON/YAML structure where it
  replaces repetitive validation code;
- Just/Mise as thin command entry points.
- Context7 via `context7-docs` for current external-library documentation only; use anonymous/free access first and keep repository/runtime evidence authoritative.

Do not add another task runner, formatter or test selector if the existing stack
already expresses the required contract.
