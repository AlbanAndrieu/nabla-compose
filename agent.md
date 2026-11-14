# Local agent runbook (OpenCode and smaller models)

`AGENTS.md` is authoritative; this file is a compact execution adapter.
Never preload the entire repository, all skills, generated files or historical logs.

## Start with capability, then scope

- **Connected workstation:** set `AGENT_EXECUTION_MODE=workstation` only when the shell and LAN are genuinely available; run `mise run agent-context`. Work with one Git worktree and use the local CPU and installed toolchain.
- **Remote Codex/API-only:** default `AGENT_EXECUTION_MODE=offline`. Use GitHub refs, targeted source diffs and offline checks; no TrueNAS, pfSense, Vaultwarden or other LAN calls. If no checkout/mise exists, do not attempt a workstation command. Mark unavailable checks `NOT_RUN`.
- Runtime diagnostic router: `bash scripts/agent-diagnostics.sh --help`; offline `--runtime` is intentionally refused.

## Route to the smallest skill

| Task | Skills |
| --- | --- |
| Compose service, catalog or env migration | `docker-compose-orchestration`, `nabla-service-catalog`; add `homelab-secrets` for credentials |
| TrueNAS service acceptance | `homelab-runtime-status` and matching service skill (workstation only) |
| pfSense, HAProxy, Snort, Unbound | `pfsense-api-debugging` |
| Quality, CI or PR continuation | `local-first-quality` |
| Security review | `security-audit` only when the task requests a security audit |

## Delivery loop

1. Confirm the selected PR and exact SHA, changed paths and nearest tests.
2. Load the matching skill and only the reference subsection needed.
3. Make one bounded patch; execute narrow L1 checks.
4. Workstation only: `mise run agent-loop` → `mise run agent-fix` → review/commit → `mise run agent-pre-push`.
5. Remote API-only: one Draft PR with expected-SHA updates; disclose missing local L2/L3 and runtime, do not silently trigger CI.
6. Never mutate `master`, print secrets, bypass hooks or delete data without authorization. Record remaining acceptance in the roadmap.

Use the [conditional playbook](docs/agent-execution-playbook.md) for detailed commands, operator recovery and CI troubleshooting.
