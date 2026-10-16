# Watchtower, logical services and controlled upgrades

Status: proposed / NOT deployed. Upstream `containrrr/watchtower` was archived on 2025-12-17. Check maintained alternatives before production use.

## Safety baseline (2026-10-16)

- Explicit allowlist: `WATCHTOWER_LABEL_ENABLE=true`. Missing label means excluded.
- Initial global `WATCHTOWER_MONITOR_ONLY=true`: no automatic upgrades until runtime validation.
- No stopped or restarting workloads, no image deletion, no public API, no credentials committed.
- WARNING: mounting `/var/run/docker.sock:ro` grants effectively root-equivalent Docker API access; read-only socket bind does **not** make it read-only. Prefer an authenticated policy-enforcing proxy or isolated update runner, but confirm needed Docker API methods and threat model.
- Never deploy automatically from PR or publicly triggered GitHub Actions.
- Images pinned to immutable digests for critical workloads and upgrades via reviewed PR, backups, compatibility tests and explicit rollout.
- Do not use Watchtower rolling-restart as a substitute for atomic multi-container Compose transactions. Watchtower does not guarantee unit-level coherent image upgrades, dependency ordering or rollback.

## Initial intended allowlist (requires Compose/runtime audit)

| Service | Desired | Gating condition |
| --- | --- | --- |
| it-tools | auto, low risk | Find authoritative Compose; health smoke |
| karakeep | evaluate, monitor-only initially | Find stack, database/storage dependencies and backup |
| homarr | monitor-only initially | Current stack includes `homarr-sync`; classify both as one unit |
| postgres, clickhouse, redis, kafka, garage | excluded from automatic upgrades | Controlled backup and orchestrated deployment |
| traefik, cloudflared, vaultwarden | excluded | Security and availability-critical |

Neither `apps/it-tools/compose.yml` nor `apps/karakeep/compose.yml` exists on the checked master branch. Do not invent or duplicate TrueNAS application ownership. Reconcile the live catalog before writing labels.

## Canonical model (proposal)

Canonical source: `nabla-compose` `x-nabla` with generated normalized catalog. FastAPI is a consumer/observer, **not** an administrator.

- `logicalServiceId`: identity shown on dashboards; preserves existing endpoint IDs.
- `deploymentUnitId`: TrueNAS app / Docker Compose project. All Compose members have the same unit.
- `componentId`: concrete service or container; separate endpoint identities are retained.
- `criticality`: `critical|high|medium|low`; default `unclassified` until audited, never silently `low`.
- `stateful`, `dataClassification`, `environment`, `dependsOn`, `recoveryTier`, `upgradePolicy`, `probePolicy`.
- `upgradePolicy`: `excluded|observe|automatic|controlled`; if missing => `excluded`.
- `probePolicy`: `primaryEndpoint`, ordered `secondaryEndpoints`, `timeoutSeconds`, `concurrencyLimit`, `cooldownSeconds`, `dependencyGate`.

One deployment unit must not have contradictory auto-update settings. Unit risk = maximum criticality of its components plus any critical dependencies; never average risk.

### Example: Garage

`deploymentUnitId: truenas:garage`; components: `garage` S3 :3900, `garage-admin` :3903, `garage-webui` :3909. Distinct IDs, probes, access rules and exposition policy remain intact.

Probe sequence: S3 read-only lightweight request (primary), Admin API only when permitted and needed, WebUI separately (auth-aware). Cache results and deduplicate concurrent requests per deployment unit. Prefer one budgeted sequence, not three parallel network fan-outs. If S3 fails, mark the unit unhealthy; dependent component health may be unknown, not automatically down. HTTP 403/302 under Access can indicate protected access, not necessarily service outage.

Upgrade: all members are **excluded** from Watchtower. A separate unit-aware controller must lock `truenas:garage`, inspect versions and dependency graph, validate backups, deploy the Compose stack as one reviewed change, then smoke endpoints in explicit dependency order, with failure stop and documented recovery. Compose itself does not provide atomic rollback.

## Implementation sequence

- **P0 / 2026-10-17: inventory**: diff canonical `x-nabla`, FastAPI catalog, TrueNAS app and Compose project labels; resolve `it-tools` and `karakeep` ownership; list multi-container projects and identify upstream drift.
- **P1: schema**: define and validate IDs, criticality and unit membership; preserve legacy IDs, generate FastAPI JSON and downstream Gatus/Homarr/AutoKuma from one source.
- **P1: probes**: bounded per-unit scheduling; deduplication/singleflight, cache TTL, backoff, dependency-aware ordering and per-endpoint results; synthetic Garage tests, auth edge cases and non-parallel fan-out regression.
- **P2: upgrades**: approved allowlist for complete low-risk single-container units only; multi-container stacks via separate dry-run/approval orchestrator; locks, digest tracking, maintenance windows, preflight/backup, rollout, smoke and stop-on-failure.
- **P2: security**: eliminate raw socket exposure where possible; audit API authorization, telemetry, image provenance, version and SBOM; compare supported alternatives to archived Watchtower.
- **P3: validation**: local-first pre-commit/Compose lint, catalog schema and contract tests, simulated upgrades and rollback runbooks; no TrueNAS deploy and no merge before approval.

Acceptance: a catalog edit is enough to regenerate observers and update policy; no unidentified container auto-updates; no parallel duplicate Garage probe groups; critical and multi-container units cannot be automatically partially upgraded.
