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

## Disconnected development and token budget

When `github.com`, PyPI or hook repositories are unavailable, do not retry
network operations in a loop. Use `just offline` for a **syntax-only L1**
check (Bash syntax, Python AST and whitespace). Without a cached comparison
ref, it checks the entire local tracked/untracked source set. It does not stop
at an arbitrary 200-file limit; `AGENT_OFFLINE_MAX_PATHS` remains an optional
explicit resource bound, default `0` (unlimited). A limited scan refuses to
claim success if its bound is exceeded.

Keep `agent-pre-push` authoritative for L3. Missing tools or dependencies
are not interpreted as passing quality. Resume cached Pre-commit, Betterleaks,
full Pytest and generated contracts when the environment permits.

For smaller agents, run `mise run agent-context` first and show only the
first failing test or job, its path, a bounded error excerpt and exact HEAD.
Never send successful full logs or complete generated catalogs into context.
Escalate from a concise failure to full logs only when required.

## Mandatory executable validation in the agent environment

For every Bash or Python patch, **execute the affected source locally before
publishing through GitHub**. A GitHub connector supplies file bytes, not an
excuse to stop at static inspection. In a network-isolated agent environment:

1. Pin the PR HEAD; fetch the exact changed files with the GitHub connector.
   Reconstruct them under a clean temporary working directory, including any
   imports and minimal fixtures needed by the targeted test. Mark unavailable
   dependencies explicitly. Do not modify the operator's live TrueNAS paths.
2. Run `bash -n path.sh` on every changed Bash file and execute the matching
   ShellCheck/shfmt versions if installed; **syntax-only does not equal lint**.
   For Python run `python -m py_compile path.py` (or AST parsing when imports
   are unavailable), then the smallest matching `pytest`/unittest module.
   For scripts invoked in live mode, never run mutating `--apply` remotely:
   exercise read-only checks and hermetic mocks/contracts instead.
   For subprocess/diagnostic tests, explicitly isolate inherited control flags
   (`NABLA_DIAGNOSTIC_WRAPPED`, `DIAGNOSTIC_FULL_OUTPUT`,
   `DIAGNOSTIC_COMPACT_OUTPUT`) when the fixture intends a fresh invocation.
   Reproduce with those flags injected as well as absent so the test does not
   accidentally depend on how an operator entered their shell.
   For mocked executable tools (e.g. fake `docker` in Python tests), do not
   assume `/tmp` permits execution on TrueNAS. Create executable fixtures on
   the writable repository filesystem or an explicitly verified exec-capable
   temporary directory, prepend that directory to `PATH`, and scrub exported
   `BASH_FUNC_*` overrides and `BASH_ENV`. Verify the mock was invoked rather
   than accidentally calling the real tool. Never relax the production check
   because of an invalid test fixture.
3. When a failure depends on Git semantics (submodules, missing paths,
   detached HEAD, origin refs or index modes), create a **temporary Git
   repository** and execute the exact helper/function against the failing
   fixture. Cover the observed failure **and** a passing ordinary-file case.
4. Report precisely what ran and where: "L1 exact-file local execution"
   versus "L1 partial reproduction". Do not describe an isolated snippet
   as proof that the full original file passed. If exact-file materialization
   is impossible, say why and supply a reproducible operator command.
5. Publish only after available L1 tests pass. Run pre-commit and the complete
   repository gate when the checkout/dependencies exist; never claim L2/L3
   based on L1, and never ask the operator to run checks that the agent can
   execute itself. Preserve security hooks and avoid shell/CI bypasses.

Do not use network failures as a reason to stop at L0: use fetched file
contents to construct small reproducible tests, but **validate the actual
changed behavior**, not unrelated illustrative code. If the user later
provides full TrueNAS output, compare it with the L1 claim and correct gaps.

## Exact-HEAD source recovery when shell DNS is blocked

Use the GitHub connector as a **control plane** when a local shell cannot
resolve `github.com`, `codeload.github.com`, or `raw.githubusercontent.com`:

1. Inspect PR metadata once and pin its `head_sha`. Read check status for
   that SHA; do not infer a green run from an earlier SHA.
2. Check *existing* workflow artifacts for a source snapshot of exactly that
   SHA. `nabla-site-alban` uses
   `source-snapshot-<HEAD_SHA>`, produced with `git archive` and short
   retention. This repository does **not** yet guarantee such an artifact.
3. If an exact-HEAD artifact already exists, download it through the GitHub
   connector, check artifact/run provenance, and extract into a clean isolated
   source tree. Treat the archive as source-only; it has **no .git** and cannot
   validate merge ancestry, hooks, or the exact publication proof.
4. Otherwise use narrow connector `fetch_file` / per-file PR patches with
   file SHA leases. For a reproducible local test, reconstruct only the
   affected files and their required fixtures. Label that proof **L1 targeted
   reproduction**, not L3 or a full repository checkout.
5. Do not repeatedly `git clone`, `curl`, or `pip install` against a
   known-blocked host. Missing dependencies remain unverified; never use
   `SKIP`, `--no-verify`, or empty file selections to claim green.
6. Preserve failing command exit codes. Show only the first actionable
   failure and a bounded excerpt in agent context. Retain detailed evidence
   separately when policy permits, without exposing credentials.

This fallback is inspired by the `nabla-maintenance` and `nabla-quality`
skills in `nabla-site-alban`. It must not silently create an expensive new
GitHub Actions run just to transport sources.

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

## Experimental Dagger PoC

Dagger remains an optional parity experiment. It does not replace the canonical
publication gate and must never bypass Pre-commit or `agent-pre-push`.

Use this sequence:

```bash
just dagger-sync            # resolve/refresh dagger.lock, then review it
just dagger-list            # refuses to run without dagger.lock
just dagger-native-parity   # official ShellCheck + pinned non-mutating Biome
just dagger-poc             # refuses to run without dagger.lock
just dagger-bench           # warm-cache comparison with Hyperfine
```

Reproducibility comes before performance:

- `@biomejs/biome` is an exact `2.4.12` dev dependency and package-lock
  entry, matching the existing Pre-commit Biome toolchain;
- the Dagger Biome module is pinned to an official 2026-10-05 commit, uses an
  explicit digest-pinned Node image, forces npm and installs with
  `--ignore-scripts`;
- the native ShellCheck reference uses the official
  `koalaman/shellcheck-precommit` hook at `v0.11.0`, replacing the legacy
  wrapper that depended on an unpinned system binary;
- ShellCheck exclusions mirror the relevant native `.sh` exclusions;
- the official ShellCheck module currently references a mutable
  `koalaman/shellcheck-alpine` image internally, so the generated
  `dagger.lock` must prove that Dagger resolved that image to immutable state
  before ShellCheck parity can be accepted;
- `DAGGER_WORKSPACE_RELEASE` is the single repository value for the beta
  workspace surface; do not repeat the beta version in individual task commands;
- `dagger-list`, `dagger-poc` and `dagger-bench` fail closed when the
  reviewed lockfile is absent.

The native Biome reference is `node_modules/.bin/biome check`, never the
Pre-commit `biome-check` hook because that hook uses `--write`. Run
`npm ci --ignore-scripts` before parity work; the task fails closed when the pinned local
Biome binary is absent.

Hyperfine is the benchmark runner; do not add a repository-specific timer.
`just dagger-bench` benchmarks `just dagger-native-parity` against
`just dagger-poc` with three runs and one warmup. Do not delete Docker/Dagger/shared caches merely to manufacture a
"cold" number. Record cold-start behavior only from a naturally cold/fresh
environment and label it separately.

Treat successful Dagger checks as **L1 targeted evidence** until native parity is
demonstrated and the full `agent-pre-push` gate passes on the exact HEAD.
Dagger benchmark success is performance evidence, not publication evidence.

The PoC intentionally excludes Pytest until the repository has a clean root
Python project marker compatible with the official Dagger Pytest discovery
contract. Ruff remains native because adding a local Dagger wrapper would
duplicate an already-working tool.

Keep secrets and live homelab mutation out of this workspace:
`defaults_from_dotenv=false`, no Vaultwarden/TrueNAS credentials, and no
appliance deployment/recovery checks. Mise may load repository operator
`.env*` files for other tasks, but this PoC never uses them as Dagger module
settings or constructor defaults; any future credential must be an explicit Dagger `Secret` input and must trigger a separate security review.

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
