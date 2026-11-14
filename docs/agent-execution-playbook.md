# Agent execution playbook — conditional reference

> Loaded **only** for tasks requiring detailed operations. `AGENTS.md` remains the canonical cross-agent policy. Do not preload this file for routine changes.

## Workstation vs remote execution

| Capability | Workstation: explicit `AGENT_EXECUTION_MODE=workstation` | API-only/Codex remote: default `offline` |
| --- | --- | --- |
| Source and PR state | Git worktree + GitHub, compare exact SHA | GitHub/ref snapshots and minimal diffs |
| Formatting / tests | Run locally using mise, Just, uv, pre-commit and installed dependencies | Run only tests supported by available checkout/toolchain; otherwise `NOT_RUN` |
| TrueNAS / pfSense / Talos | Bounded, scoped read-only probes **if reachable** | No private IP/SSH/API probing; provide command for workstation |
| Secrets | Value-blind inventory; Vaultwarden only on authorized host/session | No secret access or unlock |
| Delivery | Local L1→L2→L3; Draft PR until proofs | Draft PR; report missing L2/L3/CI/runtime, never fabricate |

Examples:

```bash
# Claude Code on connected workstation:
AGENT_EXECUTION_MODE=workstation bash scripts/agent-diagnostics.sh --static
AGENT_EXECUTION_MODE=workstation bash scripts/agent-diagnostics.sh --runtime gatus prometheus

# Remote Codex/limited checkout:
AGENT_EXECUTION_MODE=offline bash scripts/agent-diagnostics.sh --static
# --runtime intentionally returns exit 2 and NOT_RUN in offline mode.
```

The runtime diagnostic runs checks against *only the explicitly named services*; do not send every catalog service to the live LAN on every task. It uses the existing observability verifier and neither mutates TrueNAS nor authenticates to private applications automatically. Review runtime identities and targets before interpreting failures.

## Conditional tools and policies

- For Compose, load `.agents/skills/docker-compose-orchestration/SKILL.md` and `.agents/skills/nabla-service-catalog/SKILL.md`; validate without starting Apps. The active Backstage V2 contract stays authoritative.
- For secret migration, load `.agents/skills/homelab-secrets/SKILL.md` and its detailed reference. Existing runtime materializations are `root:root 0600` under `/mnt/cpool/secrets/runtime/`; no secret values in Git/logs.
- For Talos/CSI, inspect the installed driver and storage class: historic references to `democratic-csi` are **not** runtime proof of the selected TrueNAS CSI driver.
- For pfSense, load `.agents/skills/pfsense-api-debugging/SKILL.md`, use read-only posture commands first, and do not assume network access outside the workstation.
- For GitHub Actions: PR metadata → failed check → failed step → bounded log, then widen only if needed. Preserve required security checks. Review local deterministic formatter output before push; never burn CI credits as a formatting loop.
- For OpenCode/smaller models, `python3 scripts/agent-task-context.py` is a bounded path-only router. A missing base or disconnected runtime is `NOT_VERIFIED`, not a clean bill of health.
- For interactive Bash UX use `scripts/workstation/shell-status.sh` where available, honor `NO_COLOR` and avoid altering JSON/exit contracts.
- New checkout: `mise run hooks` installs repository hooks; on no toolchain run `bash scripts/agent-offline-check.sh` for L1 syntax only.

## Detailed conditional references

- [Agent skill architecture](agent-skills-architecture.md)
- [Script entry points and compatibility](../scripts/README.md)
- [Local-first quality skill](../.agents/skills/local-first-quality/SKILL.md)
- [Secrets migration](../.agents/skills/homelab-secrets/references/secrets-migration.md)
- [Runtime inspection](../.agents/skills/homelab-runtime-status/references/runtime-inspection.md)
- [Current portfolio H01–H19](roadmap-portfolio.md)

The reference documents are read only when the task needs those details. **Keep the output small, not the validation shallow.**
