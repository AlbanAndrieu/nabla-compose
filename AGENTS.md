# Agent instructions — Nabla Compose

Read this file first; load only the task-specific skill and the smallest relevant source/test slice. Detailed commands belong to [the operator playbook](docs/agent-execution-playbook.md), not every agent's startup context.

## Required skill precedence for the Nabla homelab

1. Explicit operator constraints and this `AGENTS.md`.
2. **Nabla project skills** under `.agents/skills/` matching the task.
3. **externally installed skills**, including `docker-compose-patterns` and `kubernetes-specialist`, only where compatible.
4. Vendor examples. See [docs/agent-skills-architecture.md](docs/agent-skills-architecture.md) for scoped architectural decisions.

Always preserve TrueNAS-managed ZFS bind mounts `/mnt/cpool/<service>`, Vaultwarden and protected `/mnt/cpool/secrets/runtime/<service>/` (never live repository `.env`), shared networks/platform services, and the existing `democratic-csi`/TrueNAS NFS integration until the installed CSI driver has been identified and reviewed. **Do not run** host `apt` on TrueNAS/Talos or apply `docker compose up/down`, `kubectl apply`, `helm upgrade`, migrations or restarts as incidental validation. **Ask the user before installing** external skills or making an unreviewed architecture change. Local policy wins when skills conflict.

## Safety and ownership

- Homelab downtime and reversible upgrades are acceptable; **data destruction, secret leakage, weakened authentication or new public exposure are not**. Preserve a tested recovery path for important persistent data. Never print secret values or activate shell tracing around credentials.
- Only modify an explicitly created feature branch; never write directly to `master`, bypass a hook, force-push protected refs, weaken security gates or merge without approval.
- Compose owns TrueNAS/Talos/pfSense, secrets, Cloudflare, monitoring targets and Backstage catalog. FastAPI owns API/observer/UI; Site Alban owns its UI; OpenClaw owns heartbeat. Link across repositories rather than copying procedures.
- `CODED` is not `TESTED`, `DEPLOYED` or `ACCEPTED`. A `DENIED`, `NOT_RUN` or stale sample is not a verified `DOWN`. Report exact SHA and observation vantage, not inferred runtime health.

## Execution modes — choose by actual capability, never by agent name

- **Workstation / Claude Code:** when this process really runs on the workstation with Git checkout, dependencies and reachable homelab, explicitly select `AGENT_EXECUTION_MODE=workstation`. Use local CPU, installed mise/Just/uv, targeted tests, bounded LAN diagnostics and real read-only observations. Network access must be demonstrated, not assumed from an IP in docs. Live changes still require task authorization.
- **Remote Codex / API-only / disconnected:** default `AGENT_EXECUTION_MODE=offline`. Use GitHub file/PR metadata, local source inspection if available, static syntax, targeted tests and documentation/roadmap cleanup. **Never** attempt LAN SSH, Docker sockets, TrueNAS/pfSense API, Vaultwarden unlock or speculative runtime checks. Report `NOT_RUN` and provide the workstation acceptance command.
- The mode is an execution *capability*, not an identity claim. `workstation` must be opted into explicitly; no auto-probing of private hosts.
- Canonical router: `python3 scripts/agent-task-context.py`; read-only diagnostic entry: `bash scripts/agent-diagnostics.sh --help`. `--runtime` is only allowed in workstation mode.

## Service diagnostic observer precedence

On a connected workstation, read FastAPI Sample on **TrueNAS first**:
`http://172.17.0.24:8091/api/homelab/status` and
`/api/homelab/health` (internal API/probe privileges). Then query
`https://fastapi-sample.fastapicloud.dev/sickz`: this is an **independent
outside-in probe executed in FastAPI Cloud**, not a test from the LAN.
Cloud HTTP 200 alone never proves the target service exposed or healthy;
403/401, stale/unavailable Cloudflare, timeouts and missing data are
`DENIED`/`UNVERIFIED`, never automatic `DOWN`.
Run the bounded canonical `scripts/agent-diagnostics.sh --runtime <service>`
only with `AGENT_EXECUTION_MODE=workstation`. Details:
`docs/agent-execution-modes.md`.

## Token and tool budget

1. Inspect the selected PR's state and exact HEAD, `git status --short` and changed paths. Read matching code + tests and one relevant roadmap section; do not recursively ingest 1,800 files, submodules, vendored skill references, old incidents or entire logs.
2. Load **one or two relevant** `.agents/skills/*/SKILL.md` files on demand. Follow their reference links only when needed. `nabla-service-catalog` is mandatory for service/metadata edits, `homelab-secrets` for credential paths, `pfsense-api-debugging` for pfSense, and `local-first-quality` for CI/release.
3. Run a small L1 test, then local convergence. Request failing CI job/step and bounded log excerpt before full logs. Reuse fetched evidence while current; batch read-only calls and one logical Git tree with expected-SHA lease.
4. **Context7 is documentation-only and free-first**; load `context7-docs` on demand for external versioned APIs. The `repository/runtime evidence remains authoritative`; Context7 never proves deployed state. No unrelated connector discovery.
5. Use short failure summaries with pointers to private logs instead of echoing entire responses. A token limit does not excuse missing security/functional validation.

## Git workflow and acceptance

- Prefer a dedicated worktree and a Draft PR. Workstation: `mise run agent-context` → narrow L1 → `mise run agent-loop` → `mise run agent-fix` → review/commit → `mise run agent-pre-push` on the exact committed HEAD. The full publication gate is not the targeted loop.
- Remote/API-only: bounded offline checks and static review, a Draft PR with expected-SHA writes; **never claim** that L2/L3 or runtime ran. Preserve CI/SAST/SCA/secret scanning; no invented PASS or disabled gate to save credits.
- Do not start the full Compose stack to validate. For service modifications use the dedicated catalog/Compose contract; for operational acceptance use task-specific read-only probes before any authorized mutation.
- Record remaining work in [docs/roadmap-portfolio.md](docs/roadmap-portfolio.md) and [docs/roadmap.md](docs/roadmap.md); include what changed, checks **actually** executed and missing proofs. Preserve old wrappers while consumers/tests still use them.

Consult [the conditional playbook](docs/agent-execution-playbook.md) for agent/hook recovery, shell UX, GitHub CI, service migrations and local environment setup. `CLAUDE.md` and `.claude/CLAUDE.md` are thin adapters only.
