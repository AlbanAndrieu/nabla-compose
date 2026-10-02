# Documentation map

The active documentation is organized by **purpose**, with one canonical owner
for each kind of information. Prefer links over duplicated procedures.

## Start here

| Need | Canonical document |
| --- | --- |
| Current priorities / next actions | [`roadmap.md`](./roadmap.md) |
| Documentation ownership / navigation | this file |
| Controlled TrueNAS reboot | [`homelab-reboot-runbook.md`](./homelab-reboot-runbook.md) |
| Platform migration architecture | [`homelab-platform-migration-roadmap.md`](./homelab-platform-migration-roadmap.md) |
| Security tooling architecture | [`security-tooling-control-architecture.md`](./security-tooling-control-architecture.md) |
| Service catalog / graph architecture | [`service-catalog-security-graph.md`](./service-catalog-security-graph.md) |

## Incidents and historical evidence

All date-specific incidents belong under [`incidents/`](./incidents/).

- [2026-09-11 · TrueNAS controlled reboot](./incidents/2026-09-11-truenas-reboot.md)
- [2026-09-11 · Sentry Taskbroker / project-config](./incidents/2026-09-11-sentry-taskbroker-project-config.md)
- [2026-09-11 · post-reboot runtime recovery notes](./incidents/2026-09-11-runtime-service-recovery.md)
- [2026-09-27 · pfSense/Talos DNS dependency after TrueNAS reboot](./incidents/2026-09-27-pfsense-dns-truenas-dependency.md)

Incident documents retain evidence needed for diagnosis: symptoms, commands,
observations, root cause, recovery boundary and acceptance. They are not the
place for current priorities.

## Current runbooks and diagnostics

Keep supported operator procedures in focused runbooks, for example:

- [TrueNAS reboot](./homelab-reboot-runbook.md)
- [pfSense diagnosis/recovery](./pfsense-diagnose-recover.md)
- [Kubernetes CSI preflight](./kubernetes-csi-preflight.md)
- [TrueNAS application lifecycle](./truenas-app-lifecycle.md)
- [TrueNAS runtime layout](./truenas-runtime-layout.md)
- [Runtime baseline tests](./runtime-baseline-tests.md)
- [OpenWebUI backup / PRA](./openwebui-backup-pra.md)

A runbook describes the **current supported operation**. Historical command
output belongs in an incident document instead.

## Architecture and detailed workstreams

Long-form design belongs in specialized documents rather than in the main
roadmap. The main active families are:

- platform/runtime migration: [`homelab-platform-migration-roadmap.md`](./homelab-platform-migration-roadmap.md);
- secrets: [`secrets-migration-roadmap.md`](./secrets-migration-roadmap.md);
- security inventory/SBOM/findings: [`security-inventory-tooling-roadmap.md`](./security-inventory-tooling-roadmap.md);
- service catalog v2: [`service-catalog-v2-normalization.md`](./service-catalog-v2-normalization.md);
- pfSense WAN exposure: [`pfsense-wan-exposure-roadmap.md`](./pfsense-wan-exposure-roadmap.md).

## Debt-control rules

1. `roadmap.md` is an index, not a runbook: keep status, ordering and next actions.
2. Completed roadmap work is compacted into accepted milestones; detailed proof
   remains in tests, commits, runbooks or incident documents.
3. Runbooks own supported procedures; incident documents own historical evidence.
4. Architecture documents own target state and trade-offs.
5. Prefer links over copied command blocks.
6. Keep a diagnostic only when it helps answer at least one of: **what failed,
   how to prove it, how to recover, how to validate recovery**.
7. Remove superseded planning documents once their still-relevant actions are
   represented in the canonical roadmap/design document.


## Security audit evidence

- [Security audits](./security-audits/README.md) — source-first audit runs, ledgers, findings and explicit validation gaps.
