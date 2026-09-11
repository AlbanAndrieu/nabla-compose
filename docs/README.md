# Documentation map

This directory is intentionally split by document purpose. Keep one canonical
owner for each kind of information and link to it instead of copying procedures
between files.

## Canonical documents

| Purpose | Canonical document | Keep here |
| --- | --- | --- |
| Current priorities/status | [`roadmap.md`](./roadmap.md) | concise state, ordering, open work |
| Controlled TrueNAS reboot procedure | [`homelab-reboot-runbook.md`](./homelab-reboot-runbook.md) | operator steps, gates, rollback |
| 2026-09-11 reboot evidence | [`truenas-reboot-incident-20260911.md`](./truenas-reboot-incident-20260911.md) | historical facts and lessons only |
| 2026-09-11 Sentry Taskbroker/project-config incident — **resolved 2026-09-12** | [`sentry-taskbroker-project-config-incident-20260911.md`](./sentry-taskbroker-project-config-incident-20260911.md) | Kafka membership/backlog evidence, false-green health signals, root-cause boundary, guardrails and final end-to-end acceptance |
| Functional observability/exporter strategy | [`observability-exporters.md`](./observability-exporters.md) | Sentry/Taskbroker StatsD, Kafka group lag, Suricata EVE stats and Wazuh metric strategy |
| CSI orphan diagnosis | [`truenas-csi-orphan-datasets.md`](./truenas-csi-orphan-datasets.md) | correlation and cleanup acceptance |
| Kubernetes CSI setup/preflight | [`kubernetes-csi-preflight.md`](./kubernetes-csi-preflight.md) | installation and validation contract |
| Platform migration design | [`homelab-platform-migration-roadmap.md`](./homelab-platform-migration-roadmap.md) | long-form target architecture/migration |
| TrueNAS operator tooling | [`truenas-operator-tools.md`](./truenas-operator-tools.md) | installed tools and invocation patterns |

## Debt-control rules

1. `roadmap.md` is an index, not a runbook: record status and link to detailed
   procedures/evidence.
2. Runbooks describe the **current** supported operation; incident documents
   preserve what happened historically.
3. Design/migration documents explain target architecture and trade-offs; they
   must not become a second copy of live operator commands.
4. Prefer links over copied command blocks. If the same procedure appears in
   two documents, choose one canonical owner and replace the other copy with a
   link.
5. Date-specific evidence belongs in incident documents, not evergreen runbooks.
6. Keep generated/reference material separate from hand-maintained operational
   guidance.

These rules let historical evidence stay detailed while keeping the active
operator surface small and reviewable.
