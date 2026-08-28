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

- MCP servers in `.mcp.json` / `.cursor/mcp.json`: `truenas-readonly`, `fastapi-sample`, `bitwarden-local`/`bitwarden`, Homarr, Gatus, and Uptime Kuma;
- pfSense API/network diagnostics and `.agents/skills/pfsense-api-debugging/SKILL.md`;
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
