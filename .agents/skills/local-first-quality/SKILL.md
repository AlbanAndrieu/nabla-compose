---
name: local-first-quality
description: Converge formatter, lint, generated artifacts, targeted contracts and the final publication gate locally before consuming remote CI.
---

# Local-first quality

## Consignes de rédaction (inspirées de l'ASD-STE100)

Explique les diagnostics et les procédures en français clair. Utilise
des phrases simples et directes. Décris **une seule action par étape de
procédure**. Évite les synonymes inutiles et conserve les noms exacts
des commandes, paramètres, chemins, services et états. Distingue les
faits observés, les mesures non vérifiées et les actions proposées.

Cette règle s'inspire de l'ASD-STE100. Elle ne prétend pas établir une
conformité formelle à la norme.

## Exécution opérateur en une seule commande (obligatoire)

Lorsqu'une validation nécessite réellement la workstation, TrueNAS ou un accès
matériel, fournir à l'opérateur **un seul bloc Bash prêt à coller**. Il doit
fonctionner **depuis n'importe quel répertoire de travail** et indiquer un
chemin absolu de checkout déjà connu (par exemple
/tmp/nabla-yubikey-pr259), sans supposer un cd, un HEAD à jour ou une
branche active. Ne pas demander à l'opérateur de répéter des contrôles
qu'un agent peut exécuter lui-même.

- Mettre la séquence dans un **script versionné** du dépôt dès qu'elle comporte
  plusieurs étapes : détection, préflight, git status --short, vérification
  de branche/PR/SHA, fetch seulement si nécessaire, qualité locale, preuves
  runtime en lecture seule et résultat PASS/NO-GO.
- Pour le premier lancement, si le script n'est pas dans le checkout local,
  proposer un seul bootstrap qui extrait le script depuis un commit distant
  vérifié, puis l'exécute sans modifier le HEAD existant.
- Préférer git worktree add --detach avec un répertoire privé **unique pour
  chaque agent/run** (mktemp -d, umask 077). Ne jamais partager un checkout
  mutable entre agents. Tester dans ce worktree isolé ; verrouiller les
  écritures Git entre instances (flock) et utiliser un SHA exact, jamais
  FETCH_HEAD après qu'un autre agent a pu le modifier.
- **Ne pas lancer git pull automatiquement** dans un checkout détaché,
  divergent ou sale. Dans une branche propre avec suivi explicite,
  git pull --ff-only est possible si réellement nécessaire. Ne jamais
  utiliser reset --hard, clean -fd, checkout -f, suppression forcée
  du worktree ou force-push pour « synchroniser ».
- Toute opération doit être placée après les validations bloquantes :
  set -Eeuo pipefail, contrôles de chemins et dépendances, pinning des
  commits et certificats, arrêt au premier échec. Nettoyer uniquement
  **le worktree temporaire créé par le même script et demeuré propre**.
- Ne pas répéter une opération de lecture de carte si les preuves publiques
  locales déjà validées restent présentes : réutiliser les fichiers et
  confirmer leurs empreintes. Ne pas recréer de secrets ni écraser
  des certificats. Les opérations matérielles mutantes exigent
  une approbation distincte et explicite.
- Dans la réponse, donner au maximum **une commande/un bloc opérateur**,
  placé après les résultats agent. Il doit inclure le chemin absolu de
  référence, la synchronisation Git nécessaire, les contrôles enchaînés
  et l'arrêt automatique. Éviter les commandes fractionnées et les
  questions de routine ; demander l'exécution uniquement pour un accès
  matériel/runtime que l'agent ne possède pas.

Exemple : scripts/workstation/run-age-yubikey-pr274-readonly.sh découvre la
branche PR #274, crée un worktree privé, lance les tests offline puis
vérifie la preuve publique F9. Il n'effectue aucun git pull sur
/tmp/nabla-yubikey-pr259, n'y change pas de branche et
n'authentifie aucune YubiKey.

## Skills externes : contrôle local avant installation

`AGENTS.md` et `docs/agent-skills-architecture.md` définissent la
priorité des instructions. Avant de proposer l'installation d'un skill
externe, lire le `SKILL.md` et ses scripts, vérifier les autorisations,
les accès réseau et les alertes de sécurité. Demander **l'accord explicite**
de l'utilisateur pour chaque skill, même si la roadmap le prévoit.

Préférer une installation **limitée au projet de développement**, jamais
directement sur TrueNAS/Talos. Ne jamais lancer de mutation, de
redéploiement ou de CI payante pour valider une documentation de skill.
Exécuter `just agent-skills-check` pour détecter une dérive des règles
du dépôt avant une PR Ready, puis les contrôles locaux applicables.

## Efficiency for multi-repository security changes

- Inspect the exact selected PR head and only relevant files and failed checks.
  For the very large roadmap, read only bounded section ranges.
- Batch related edits into one Git tree/commit, use expected-HEAD compare-and-swap
  updates and reconcile a concurrent writer by comparing changed paths.
- Run offline targeted tests and formatting before a commit whenever possible;
  do not repeatedly poll GitHub checks without new evidence.
- Fetch only the failing job's relevant log lines, never full successful logs.
  CI remains a security gate: do not silence BetterLeaks, CodeQL, Trivy,
  Checkov, formatter or executor-mode failures to save time.
- Distinguish static preparedness, CI success at exact HEAD and actual
  TrueNAS/Vaultwarden/DefectDojo runtime acceptance.


Use this skill for CI failures, quality-gate work, PR continuation, formatter/linter
fixes, or any task where remote CI should remain a safety net rather than the
edit loop.

## Branch and environment ownership (mandatory)

- Resolve the **user-selected open PR and its head branch** before editing.
  When the user specifies a branch, use exactly that branch for all writes.
- **Never push, commit or update refs directly on `master` or another
  protected base branch.** Use a reviewed feature branch and its open PR;
  do not merge unless explicitly requested.
- Do not switch to a different PR for thematic reasons without the
  operator's explicit authorization. Code already merged into master
  remains available to the PR through its base; do not duplicate it merely
  because it is absent from the PR's *Files changed* tab.
- Make code, documentation and Git file-mode changes in the **agent
  environment first**. Run available syntax and targeted contract tests,
  publish to the chosen PR, and verify the exact remote HEAD and Git
  `100755` index modes before declaring completion.
- Request actions on TrueNAS, a workstation or production **only as a
  last resort**, for hardware-dependent/runtime acceptance or a proven
  agent-side blocker. Prefer read-only validation; never delegate ordinary
  repository edits and chmod fixes to the operator by default.
- If the agent's GitHub branch write fails, report the exact failure and
  avoid claiming publication. Recover within agent tools before proposing
  a minimal, reversible operator workaround.

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

For the October 2026 TrueNAS/Git permission anomalies, duplicated Bash functions,
failed mocked executables and local-first troubleshooting, see
[`docs/incidents/2026-10-10-local-first-quality-truenas-git-permissions.md`](../../../docs/incidents/2026-10-10-local-first-quality-truenas-git-permissions.md).

## Git executable contract versus filesystem permissions

Git records executable files as `100755` regardless of actual checkout
permissions, including `0700` on a locked-down TrueNAS dataset. In portable
tests, assert `S_IXUSR` for operator execution and `git ls-files --stage`
`100755` for repository distribution. Do **not** insist on `S_IXGRP` or
`S_IXOTH` merely because the Git mode is `100755`. Never `chmod 755`
private operator scripts to make a CI test pass. Verify the effective ACL and
the operator identity separately if runtime execution is denied.

If a local checkout has `core.fileMode=false` or ACL/chmod policies diverge
from the Git index, distinguish **index**, **stat**, **getfacl**, and
**shebang** evidence. A staged mode fix uses `git add --chmod=+x`; changing
the filesystem execute bit for the owning operator uses `chmod u+x` (only
when actually needed). Do not use `git reset --hard` to reconcile modes.
Never treat a permission-mode mismatch as permission to skip pre-commit.

The `agent-quality-gate.sh --preflight` checks **all tracked shebang files**
against Git index mode `100755`, including files not changed by this PR.
This prevents old `100644` executable scripts escaping changed-file checks.
In fix mode, `git add --chmod=+x` corrects the index; if needed, only
`chmod u+x` corrects the owner's filesystem execute bit. Never silently
normalize a private `0700` TrueNAS file to `0755`. Examine the staged diff
before committing; the publication gate must refuse dirty staged changes.


## Node.js dependency for security audit contracts

The vendored Cloudflare `security-audit` validation is an **enforced** Node.js
quality gate: `tests/test_security_audit_skill_contract.py` invokes both
`validate-findings.cjs` and `validate-coverage-ledger.cjs`. TrueNAS may have
Python, Pre-commit and hook-isolated JavaScript tooling but **no `node` on
the operator's effective PATH**. A passing Biome/Pre-commit hook is not proof
that a system Node runtime is available to the Python subprocess.

Node is pinned in `mise.toml`. From the TrueNAS operator checkout use
`mise install node`, then verify `mise exec -- node --version` and run the
targeted security-audit contract under `mise exec -- python -m pytest ...`.
If the Python dev venv is needed, invoke its interpreter through `mise exec`
or activate the venv first. Do not skip the assertion requiring Node, and do
not translate a missing runtime into a passing audit validation.

## Mandatory reproduction before GitHub writes

When a failure log names a deterministic pytest module, test function, or
standalone shell helper, reproduce it in the **agent's own environment before
editing or asking the operator to rerun it**. Prefer an exact-HEAD isolated
checkout with the unchanged source, dependency fixtures and targeted pytest.
If network access prevents that checkout, fetch files through the GitHub
connector and reconstruct the exact test and helper in a disposable directory.
First observe the failure on the original behavior, then run the corrected
behavior, including a negative regression. Merely evaluating a string
assertion in memory is **L1 partial reproduction**, not an executed pytest
module, and must be reported as such.

Before publishing a Python/test patch, compile or AST-parse the **entire
modified file** and execute the affected test where dependencies are available.
Avoid repeated connector edits that have not received even syntax validation.
If the full test cannot be run locally, state the missing prerequisite and
do not claim it was validated. Request operator validation only for behavior
that genuinely depends on their TrueNAS/workstation runtime.

For tests that mock external executables, especially on TrueNAS with
`/tmp noexec`, do not assume a `chmod(0o755)` shim on `tmp_path` will
be executed. Prefer Bash functions injected with `BASH_ENV` when invoking a
Bash script, or a verified exec-capable fixture location. Confirm that the
mock intercepts the intended command, so an unexpected success cannot
silently bypass the negative test. Preserve the fail-closed assertion.

## TrueNAS noexec fixtures and branch divergence

TrueNAS may mount `/tmp` as `tmpfs rw,nosuid,nodev,noexec` (confirmed
2026-10-10). A fixture placed there can have POSIX `0700` and Git index
`100755` but still fail Bash `[[ -x file ]]` due to the mount. **Do not**
remount `/tmp` with `exec`, run as root, force `chmod 755`, or weaken the
production executable-bit gate to make tests green.

Before a test needs an executable fixture, inspect
`findmnt -T "${TMPDIR:-/tmp}" -o TARGET,FSTYPE,OPTIONS`. Prefer an
exec-capable isolated directory on the repository dataset (or an explicitly
verified scratch mount), create it with `0700`, and clean it afterwards.
For index-only semantics, use `git update-index --chmod=+x` and inspect
`git ls-files --stage` without trying to execute a file. If a test
intentionally exercises effective execution on `noexec`, assert the denied
case separately; any skip must name the unmet environmental prerequisite and
must not hide a failing negative security test.

Regression fixtures must execute against the **same filesystem semantics**
as the production assertion. `chmod(0o700)` alone is not proof that
`[[ -x file ]]` succeeds. When a fixture is simulated with a temporary Git
repo, check both the index mode and Bash's effective `-x` result. Validate
Python syntax and the exact generated file before publishing, avoiding
literal `\\n` text accidentally injected into Python source.

When a local permission-only commit is created while the remote PR HEAD has
advanced, `git pull --ff-only` will legitimately fail. Never reset, force-push,
or drop the commit. Use `git status --short`, `git log --oneline
--left-right HEAD...@{upstream}` and then, if the working tree is clean,
`git merge --no-ff @{upstream}` (or a reviewed rebase). Retest on the
resulting HEAD before pushing. Outputs from `git pull` and pytest are not
shell commands and must never be pasted back as executable input.

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

## Shell operator experience and refactoring

When creating or refactoring operator-facing Shell scripts, source
`scripts/lib/common.sh` and use `ok` / `warn` / `fail` / `info` / `section`
for consistent ✅/⚠️/❌/ℹ️ statuses and green/yellow/red/cyan terminal colors
(`nabla_ui_init` exposes `NABLA_UI_*` colors for custom lines). Read-only
diagnostics with warning/failure counters use `scripts/lib/diagnostic-ui.sh`.
Never redefine `fail()` locally after sourcing `common.sh`.
Preserve plain, stable text in CI, logs and redirected output; respect
`NO_COLOR`, `TERM=dumb`, and `NABLA_UI_ASCII=1`. Never color JSON, probes,
machine-readable records or secrets. Do not pipe errors through a coloring
filter that changes exit status.

Prefer reuse of existing `scripts/lib/truenas.sh` job/provenance/lifecycle
helpers, `scripts/lib/diagnostic.sh` wrapper, and `scripts/lib/probe.sh`
network primitives over another local copy. Before moving a widely used
function, search call sites and record signatures/error codes; preserve
public CLI switches and outputs and test them locally. Refactor in small
batches with ShellCheck, shfmt and targeted contracts before widening scope.
