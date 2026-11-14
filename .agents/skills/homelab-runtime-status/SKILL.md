---
name: homelab-runtime-status
description: Validate declared, observed, functional, and exposure status of Nabla services; load deep runtime checks only when authorized.
---

# Homelab runtime status — compact router

Use on deployment/recovery/health tasks only. Read `AGENTS.md` first; this skill does **not** authorize a live change.

- **Disconnected Codex:** no LAN probing; inspect declarative sources, run offline contracts, and return `NOT_RUN`/missing proof. Do not infer `DOWN` from a stale sample or `DENIED`.
- **Connected workstation Claude Code:** use `AGENT_EXECUTION_MODE=workstation` and `scripts/agent-diagnostics.sh --runtime <service>` (max 3). **FastAPI on TrueNAS** `/api/homelab/status` and `/api/homelab/health` comes **first**, then independent **FastAPI Cloud** `/sickz` outside-in. Direct Gatus/Prometheus checks are targeted follow-ups, not the initial fan-out.
- **Distinct evidence:** declaration/catalog `entityRef` ≠ container RUNNING ≠ TCP reachability ≠ application healthy ≠ externally exposed. Correlate timestamps, vantage, `catalogRevision` and exact target; mark uncertainty explicitly.
- **Security:** private Access `403` may be expected; unknown/stale/NOT_RUN is not `DOWN`; no secrets or Docker socket exposure. A risky persistent-state migration needs a restoration path.
- **Completion:** supply SHA/target/observation and update the owning roadmap for unverified work.

**Load specific sections only** from [runtime endpoints, migration and acceptance checks](references/runtime-inspection.md) for API endpoint semantics, native→Compose migration, NPMplus acceptance, or deeper failure classification.
