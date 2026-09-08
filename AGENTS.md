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

## Tool and context efficiency

The goal is to minimize the context required to reach a reliable result, never to reduce capability, validation depth, security coverage, or diagnostic quality.

### Tool classification for this repository

**First-class capabilities** — use without functional restriction whenever the task needs them, but load only the smallest useful result:

- local Git/shell inspection (`git status`, `git diff`, `git ls-files`, `rg`) and targeted repository files;
- GitHub repository/PR operations and GitHub Actions status, jobs, logs, artifacts, and deployment-related evidence;
- Docker Compose configuration and the repository Compose validation path;
- `pre-commit`, `scripts/quality-gate.sh`, repository generators/tests, Gitleaks, Checkov, CodeQL, MegaLinter, and the existing security/quality gates;
- TrueNAS runtime/API evidence for the production homelab and FastAPI Sample homelab status/health endpoints when runtime verification is required;
- Vaultwarden plus the Bitwarden CLI/secret contract for secret inventory, rendering, migration, and deployment work;
- OpenTofu/Terragrunt for the TrueNAS/Talos infrastructure code and Doco-CD for the deployment flows that explicitly use it.

**On-demand integrations** — keep available, but discover/load/invoke only for tasks that need them:

- MCP servers in `.mcp.json` / `.cursor/mcp.json`: `truenas-readonly`, `fastapi-sample`, `sentry`, `bitwarden-local`/`bitwarden`, Homarr, Gatus, and Uptime Kuma;
  the Sentry MCP uses the direct LAN endpoint on TrueNAS rather than the Cloudflare-protected public hostname; keep its User Auth Token outside Git and use the read-only `inspect` skill by default;
- pfSense API/network diagnostics and `.agents/skills/pfsense-api-debugging/SKILL.md`; whenever a task touches pfSense/Netgate, PF, HAProxy, Snort, pfBlockerNG, Unbound, Kea or pflow/IPFIX, read that skill before proposing appliance commands and do not depend on prior-chat context;
- Homarr/Gatus/Uptime Kuma runtime APIs when generated repository contracts are insufficient to diagnose their live state;
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
- Preserve all existing tests and quality gates. Never reduce test coverage, scanner coverage, deployment verification, or security checks to save context.
- For Playwright/Cypress/E2E failures, inspect the failing test/report first; fetch screenshots, traces, videos, or the complete artifact whenever they materially improve diagnosis, especially for intermittent or browser-only failures.
- For TrueNAS, FastAPI Sample, Sentry, deployment platforms, and other observability APIs, request the narrowest evidence that answers the question, then widen when necessary.
- A final CI/deployment verification explicitly requested by the task is mandatory even when earlier evidence looks sufficient.

### Polling policy

Do not repeatedly poll workflow, deployment, job, check, or observability status in a tight loop. Read once, perform other useful analysis/fixes while the result cannot change the next action, then re-read when a state transition could materially affect the decision. Always perform the required final verification before reporting completion.

### Instruction source of truth

`AGENTS.md` is the canonical cross-agent repository policy. Agent-specific entry files such as `CLAUDE.md`, `.claude/CLAUDE.md`, and `.github/copilot-instructions.md` should point here and contain only adapter-specific routing that cannot live here. Do not duplicate this policy across agent files.

## Validation

For a focused change, run the closest relevant formatter/linter first.

After an editing batch, use the repository-specific agent workflow:

```bash
bash scripts/agent-quality-gate.sh --fix
# review deterministic generator/formatter changes, then commit them
bash scripts/agent-quality-gate.sh
```

The strict agent gate checks branch freshness, suspicious large truncations, executable bits for shebang scripts, generated topology/consumer synchronization, and the lightweight unit/contract suite before delegating to the canonical quality gate.

`scripts/quality-gate.sh` remains the canonical cross-Nabla formatter/linter/security gate. Publication mode is still `scripts/quality-gate.sh --publish`, reached through `scripts/agent-quality-gate.sh --publish`.

Compose files remain validated with:

```bash
docker compose config --quiet --no-interpolate --no-env-resolution
```

Do not start the homelab stack merely to validate configuration. Do not run MegaLinter locally unless diagnosing a MegaLinter-specific failure. Keep validation output compact: fix the first deterministic failure, rerun locally, and publish one validated batch rather than using CI as an edit/test loop.

## Mandatory agent publish policy

Agents must never publish changes immediately after editing files.

Before every `git push`, GitHub API file update, or other remote repository mutation:

1. Run `bash scripts/agent-quality-gate.sh --fix` after the editing batch whenever a local checkout is available.
2. Review deterministic generator/formatter changes and commit them.
3. Run `bash scripts/agent-quality-gate.sh --publish` until it exits successfully.
4. Fix every formatter, linter, YAML, Compose, workflow, generated-contract, unit-test, executable-bit, destructive-diff, or security-check failure caused by the change.
5. Verify `git status --short` is empty.
6. Publish the complete validated batch once.

Keep iterative agent pull requests as **drafts** until the strict local agent gate is green. Expensive PR jobs may skip drafts; the cheap deterministic preflight still runs on every PR and runs again when the PR becomes ready.

When `mise run hooks` has been run, the normal Git `pre-commit` hook validates commits and the versioned pre-push hook invokes `scripts/agent-quality-gate.sh --publish`.

An API-only agent must not silently treat remote API writes as a way to bypass local hooks. If its runtime cannot execute a checkout, it must disclose that limitation, reproduce the closest deterministic validations available, keep the patch minimal, inspect resulting CI, and never claim the local gate passed. When several files form one logical patch, batch them into one Git tree/commit when the API supports it so each synchronize event does not start another CI cycle.

Never bypass repository hooks with `git push --no-verify`. Never weaken or disable formatter, lint, security, YAML, Compose, or validation rules merely to make a push or CI build pass.

## Changes

Make the smallest safe patch. Fix deterministic formatter/linter output directly instead of reasoning around it. Never commit secrets. Keep GitHub Actions pinned to commit SHAs and use least-privilege permissions.

## Completion

Report:

1. what changed;
2. checks executed;
3. unresolved failures or risks.
