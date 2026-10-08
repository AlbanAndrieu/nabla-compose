# Agent instructions

Keep context small and changes scoped.

## Repository bootstrap

Git hook configuration is versioned, but Git does not install repository hooks automatically after clone. On a new checkout, run:

```bash
mise run hooks
```

This explicitly installs the configured `pre-commit`, `commit-msg`, and `pre-push` hooks. CI is a remote safety net; deterministic formatting, linting, generators and the full repository unit/contract suite must be completed locally before a push.

## Before editing

1. Inspect `git status`, the task, and only relevant files.
2. Prefer targeted search (`rg`, `git diff`, `git ls-files`) over recursive repository reads.
3. Do not inspect submodules, generated files, caches, reports, lockfiles, or vendored trees unless the task requires them.
4. Reuse existing Compose patterns and CI conventions; do not introduce a new tool when an existing one covers the check.
5. When adding, renaming, removing, or materially reconnecting a Compose service, read `.agents/skills/nabla-service-catalog/SKILL.md` and keep its `x-nabla` metadata and generated catalog contracts synchronized.

## Tool and context efficiency

The goal is to minimize the context required to reach a reliable result, never to reduce capability, validation depth, security coverage, or diagnostic quality.

### Tool classification for this repository

**First-class capabilities** — use without functional restriction whenever the task needs them, but load only the smallest useful result:

- local Git/shell inspection (`git status`, `git diff`, `git ls-files`, `rg`) and targeted repository files;
- GitHub repository/PR operations and GitHub Actions status, jobs, logs, artifacts, and deployment-related evidence;
- Docker Compose configuration and the repository Compose validation path;
- `pre-commit`, `scripts/quality-gate.sh`, repository generators/tests, Betterleaks, Checkov, CodeQL, MegaLinter, and the existing security/quality gates;
- TrueNAS runtime/API evidence for the production homelab and FastAPI Sample homelab status/health endpoints when runtime verification is required;
- Vaultwarden plus the Bitwarden CLI/secret contract for secret inventory, rendering, migration, and deployment work;
- OpenTofu/Terragrunt for the TrueNAS/Talos infrastructure code and Doco-CD for the deployment flows that explicitly use it.

**On-demand integrations** — keep available, but discover/load/invoke only for tasks that need them:

- MCP servers in `.mcp.json` / `.cursor/mcp.json`: `truenas-readonly`, `fastapi-sample`, `sentry`, `bitwarden-local`/`bitwarden`, Homarr, Gatus, Uptime Kuma and Context7;
  the Sentry MCP uses the direct LAN endpoint on TrueNAS rather than the Cloudflare-protected public hostname; keep its User Auth Token outside Git and use the read-only `inspect` skill by default;
- pfSense API/network diagnostics and `.agents/skills/pfsense-api-debugging/SKILL.md`; whenever a task touches pfSense/Netgate, PF, HAProxy, Snort, pfBlockerNG, Unbound, Kea or pflow/IPFIX, read that skill before proposing appliance commands and do not depend on prior-chat context;
- Homarr/Gatus/Uptime Kuma runtime APIs when generated repository contracts are insufficient to diagnose their live state;
- Context7 is documentation-only and free-first: use the anonymous MCP/CLI path for current external-library APIs, then free login/OAuth if the anonymous quota is insufficient. `CONTEXT7_API_KEY` is optional non-interactive automation, never a repository requirement. Load `context7-docs` only when external/version-specific documentation materially affects the implementation; repository/runtime evidence remains authoritative;
- AWS/ECR, Renovate, Kubernetes/Talos, Helm, Argo CD, Keycloak, Vault, and other platform-specific tooling outside a task that touches those systems;
- specialized skills under `.agents/skills/**`: read the matching skill only when its trigger applies rather than preloading every skill.

**Out of scope by default** — do not discover schemas or invoke unrelated global connectors merely because they are installed. Examples include Gmail, Google Calendar/Contacts, Slack, LinkedIn, Vercel, Supabase, and other account/SaaS integrations with no current role in the task or repository path being changed. Do not uninstall or disconnect them; an installed but undiscovered integration costs less project context and remains available if a future task explicitly needs it.

### Discovery and retrieval rules

1. For connector/MCP tools, discover the specific function needed, not the complete connector schema. Reuse functions already discovered in the current conversation.
2. Reuse previously fetched files, responses, resource URIs, commit/PR metadata, and runtime snapshots while they remain current enough for the decision. Do not repeat an identical call just to reconfirm unchanged data.
3. Prefer specialized operations over broad generic endpoints: PR metadata before full PR patches, combined status before jobs, jobs before logs, targeted file/range reads before whole files, and service-specific health rows before full API payloads.
4. Expand progressively only when the smaller result cannot answer the next decision. A token/context budget is never a reason to skip evidence that is actually required.
5. For large generated JSON/YAML, reports, logs, traces, or API responses, search/select the relevant service, failure, field, or range first. Retrieve the complete artifact when targeted evidence is inconclusive.

### CI/CD, tests, and observability

Use progressive failure analysis:

`workflow/check status -> failing job -> failing step -> targeted logs -> complete logs/artifact/trace when needed`

- Do not download every job log or artifact for a green workflow.
- Prefer the compact local agent gate output over remote CI logs. When CI still fails, inspect only the failing workflow/job/step first and widen to full logs only when needed.
- A CI failure caused only by formatter/autofixer output is a **local workflow defect**, not a remote-debugging task: fix the local hook/gate contract so the same class of failure is prevented before the next push.
- Preserve all existing tests and quality gates. Expensive or complete regression work may run locally before push while PR CI performs equivalent changed-file contracts and independent remote security checks.
- For Playwright/Cypress/E2E failures, inspect the failing test/report first; fetch screenshots, traces, videos, or the complete artifact whenever they materially improve diagnosis, especially for intermittent or browser-only failures.
- For TrueNAS, FastAPI Sample, Sentry, deployment platforms, and other observability APIs, request the narrowest evidence that answers the question, then widen when necessary.
- A final CI/deployment verification explicitly requested by the task is mandatory even when earlier evidence looks sufficient.

### Polling policy

Do not repeatedly poll workflow, deployment, job, check, or observability status in a tight loop. Read once, perform other useful analysis/fixes while the result cannot change the next action, then re-read when a state transition could materially affect the decision. Always perform the required final verification before reporting completion.

### Instruction source of truth

`AGENTS.md` is the canonical cross-agent repository policy. Agent-specific entry files such as `CLAUDE.md`, `.claude/CLAUDE.md`, and `.github/copilot-instructions.md` should point here and contain only adapter-specific routing that cannot live here. Do not duplicate this policy across agent files.

## OpenCode and smaller-model execution

OpenCode uses this `AGENTS.md` as its repository instruction entry point.
`agent.md` is allowed only as a **non-authoritative execution runbook** for the
smaller workstation model; this file always wins on conflict. Keep
`opencode.json` and `.opencode/**` as thin execution adapters. OpenCode can
discover the repository `.agents/skills/<name>/SKILL.md` files on demand, so
reuse those skills rather than copying them into an OpenCode-only tree.

At the start of a non-trivial OpenCode implementation task, run
`mise run agent-context`. The helper is path-only/value-blind: it summarizes
branch/worktree scope and suggests likely skills without reading secret values.

The workstation OpenCode profile intentionally uses `openai/gpt-4.1-mini`.
Make its workflow deterministic:

1. inspect `git status` and the smallest relevant file set;
2. load only the skills matching the task;
3. prefer a repository script/test to an ad-hoc command or inferred procedure;
4. change one bounded service/logical unit at a time;
5. run the narrowest contract first and fix the first deterministic failure;
6. widen validation only after the targeted contract is green;
7. never read or print live `.env` / `.env.*` values; use the value-blind
   secret inventory/materialization tooling.

Task-to-skill routing:

- `.env`, `.env.secrets`, `env_file`, Vaultwarden or secret materialization:
  load `homelab-secrets`, `docker-compose-orchestration` and
  `nabla-service-catalog`;
- Compose service/runtime/dependency edits: load
  `docker-compose-orchestration` and `nabla-service-catalog`;
- TrueNAS live-state acceptance: additionally load `homelab-runtime-status`;
- pfSense/HAProxy/PF/Snort/pfBlockerNG: load `pfsense-api-debugging`;
- explicit security audit, vulnerability review or source-first pen-test request:
  load `security-audit`; use its full six-phase/report workflow only when the
  request explicitly asks for an audit/report, and preserve its sandbox,
  independent-validation and incomplete-run rules;
- quality/CI failures, PR continuation or local validation workflow changes:
  load `local-first-quality`.
- current/version-specific external library or tool API questions (for example Dagger, Docker/Compose, Kubernetes/Talos, Python/JavaScript libraries): load `context7-docs` on demand; do not use it to infer repository or runtime state;

For **P0.3**, runtime env normalization and Backstage v2 preparation are one
service migration bundle. A touched service must have a canonical
`/mnt/cpool/secrets/runtime/<service>/...` contract, reviewed
`apps/<service>/catalog-info.yaml`, and
`com.albandrieu.nabla.entity-ref` binding before runtime acceptance. Validate
that bundle with:

```bash
python scripts/check-service-migration-bundle.py --app <service>
```

Keep transitional `x-nabla` compatibility metadata until the coordinated v2
cutover; do not independently remove it during P0.3.

## Protected default-branch policy

Agents must **never** commit, push, create, update, delete, or otherwise mutate files directly on `master`, and must never move, force-update, or write the `master` ref directly.

This applies equally to Git CLI pushes, GitHub API/Contents writes, generated files, documentation-only changes, trivial fixes and emergency fixes. Before every remote mutation, verify that the destination is a dedicated non-default branch. If an API defaults a missing `branch`/`ref` argument to the repository default branch, omitting that argument for a write is prohibited.

All agent-authored changes must use a branch and pull request. Leave the merge to the user/maintainer unless the user explicitly asks the agent to merge. Never use `git push --no-verify`, never force-update `master`, and never weaken quality/security controls to get a change published.

## Local-first validation

For quality/CI work and PR continuation, load
`.agents/skills/local-first-quality/SKILL.md`. Keep `AGENTS.md` limited to the
cross-agent invariants; the skill owns the detailed execution loop.

```bash
mise run agent-loop
# review deterministic changes, then commit
mise run agent-pre-push
```

`agent-loop` is the iterative changed-file gate. `agent-pre-push` is the
authoritative complete local publication gate and is also enforced by the
pre-push hook. Never bypass it. Do not use remote CI as the edit/format/lint feedback loop.

`scripts/quality-gate.sh` remains the canonical cross-Nabla formatter/linter/
security gate. Validate Compose without starting services:

```bash
docker compose config --quiet --no-interpolate --no-env-resolution
```

## Mandatory agent publish policy

Agents must never publish changes immediately after editing files.

Before every `git push` or other normal remote publication from a checkout:

1. Confirm the target is a dedicated non-default branch and is not `master`.
2. Run `mise run agent-fix` after the editing batch and allow all convergence passes to finish.
3. Review deterministic generator/formatter changes and commit them with the logical change.
4. Run `mise run agent-pre-push`; the same script is also enforced by the pre-push hook.
5. If `QG_AUTOFIX_APPLIED` is reported, amend/commit only those deterministic changes and rerun the same local command; do not push yet.
6. Fix every non-autofixable formatter, linter, YAML, Compose, workflow, generated-contract, unit-test, executable-bit, destructive-diff, or security-check failure caused by the change.
7. Verify the superproject has no uncommitted changes. Local unstaged submodule
   checkout/HEAD drift may be ignored because it cannot alter the published
   superproject commit; any staged submodule gitlink change must still block
   publication until committed or unstaged.
8. Push the complete validated batch once.

Keep iterative agent pull requests as **drafts** until the strict local agent gate is green. Expensive PR jobs may skip drafts; the cheap deterministic preflight still runs on every PR and runs again when the PR becomes ready.

When `mise run hooks` has been run, the normal Git `pre-commit` hook validates commits and the versioned pre-push hook performs convergence plus the complete local publication gate.

An API-only agent must not silently treat remote API writes as a way to bypass local hooks. If its runtime cannot execute a checkout, it must disclose that limitation, batch the entire logical patch before opening/updating the PR, reproduce the closest deterministic validations available, inspect only the first failing remote step, and never claim the local gate passed. If CI reports only deterministic formatter output, apply that exact formatter diff once, compact/squash the branch again, and do not broaden the investigation into unrelated logs.

Never bypass repository hooks with `git push --no-verify`. Never weaken or disable formatter, lint, security, YAML, Compose, or validation rules merely to make a push or CI build pass.

## Changes

Make the smallest safe patch. Fix deterministic formatter/linter output directly instead of reasoning around it. Never commit secrets. Keep GitHub Actions pinned to commit SHAs and use least-privilege permissions.

## Completion

Report:

1. what changed;
2. checks executed;
3. unresolved failures or risks.
