# Watchtower, logical services and controlled upgrades

Status: proposed / NOT deployed. The old `containrrr/watchtower` was archived on 2025-12-17; use maintained `nickfedor/watchtower:1.23.1` (2026-10-13), whose exact tag was verified on Docker Hub. Verify image digest, signatures and Docker API compatibility before a manual start.

## Safety baseline (2026-10-16)

- Explicit allowlist: `WATCHTOWER_LABEL_ENABLE=true`. Missing label means excluded.
- Initial global `WATCHTOWER_MONITOR_ONLY=true`: no automatic upgrades until runtime validation. `profiles: [manual-audit]` avoids accidental activation by standard Compose deployment. Monitor-only may still pull images; enforce disk and network budgets.
- No stopped or restarting workloads, no image deletion, no public API, no credentials committed.
- WARNING: mounting `/var/run/docker.sock:ro` grants effectively root-equivalent Docker API access; read-only socket bind does **not** make it read-only. Prefer an authenticated policy-enforcing proxy or isolated update runner, but confirm needed Docker API methods and threat model.
- Never deploy automatically from PR or publicly triggered GitHub Actions.
- Images pinned to immutable digests for critical workloads and upgrades via reviewed PR, backups, compatibility tests and explicit rollout.
- Do not use Watchtower rolling-restart as a substitute for atomic multi-container Compose transactions. Watchtower does not guarantee unit-level coherent image upgrades, dependency ordering or rollback.

## Initial intended allowlist (requires Compose/runtime audit)

| Service | Desired | Gating condition |
| --- | --- | --- |
| it-tools | candidate for future automatic updates; currently not opted in | Find authoritative TrueNAS app/Compose, verify no database and smoke check |
| karakeep | candidate for future monitoring only; currently not opted in | Find stack, database/storage dependencies and backup; catalog legacy description may be stale |
| homarr | opted in for monitoring only (`enable=true`, `monitor-only=true`) | Current stack includes `homarr-sync` (explicitly excluded); unit is stateful and not eligible for automatic partial upgrades |
| postgres, clickhouse, redis, kafka, garage | excluded from automatic upgrades | Controlled backup and orchestrated deployment |
| traefik, cloudflared, vaultwarden | excluded | Security and availability-critical |

Neither `apps/it-tools/compose.yml` nor `apps/karakeep/compose.yml` exists on the checked master branch. Do not invent or duplicate TrueNAS application ownership. Reconcile the live catalog before writing labels.

## Canonical model (proposal)

Canonical source: `nabla-compose` `x-nabla` with generated normalized catalog. FastAPI is a consumer/observer, **not** an administrator.

- `logicalServiceId`: identity shown on dashboards; preserves existing endpoint IDs.
- `deploymentUnitId`: TrueNAS app / Docker Compose project. All Compose members have the same unit.
- `componentId`: concrete service or container; separate endpoint identities are retained.
- `operationalCriticality`: `critical|high|medium|low`; map legacy `x-nabla.criticality` without silently overwriting it. Keep independent BIA-derived `businessCriticality` when available; either missing value blocks auto-upgrade. Never silently classify unknown as `low`.
- `stateful`, `dataClassification`, `environment`, `dependsOn`, `recoveryTier`, `upgradePolicy`, `probePolicy`.
- `upgradePolicy`: `excluded|observe|automatic|controlled`; if missing => `excluded`. An automatic decision additionally requires a single-container Compose unit, `stateful=false`, low operational and business impact, no critical dependencies, and validated smoke/recovery.
- `probePolicy`: `primaryEndpoint`, ordered `secondaryEndpoints`, `timeoutSeconds`, `concurrencyLimit`, `cooldownSeconds`, `dependencyGate`.

One deployment unit must not have contradictory auto-update settings. Unit operational risk = maximum operational criticality of its components plus critical dependencies; business impact is an independent BIA axis and never averaged. Do not equate upgrade grouping with user-facing logical endpoints.

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

## Concrete repository changes (PR #257)

- `apps/watchtower/compose.yml`: maintained fork pinned to release tag, default-deny label filter, global monitor-only, manual audit profile, no cleanup and no stopped/restarting containers. **Not deployed**.
- `apps/homarr/compose.yml`: one unit (Homarr plus sync job), monitor `homarr` only; do not auto-update or revive `homarr-sync`.
- `apps/garage/compose.yml`: one high-risk unit; both containers explicitly ineligible for Watchtower updates. The separate Admin endpoint remains attached to the Garage container and retains its own health/exposure identity.
- `truenas-file-structure.sh`: remove unsafe legacy Watchtower definition to avoid a second, unrestricted updater.
- `scripts/security/check-watchtower-unit-policy.py --check`: reject auto-update for multi-container, stateful, medium/high/critical units or missing unit metadata. Synthetic tests cover selection and rejection.
- The `x-nabla.deploymentUnit` blocks are **metadata staging** for the canonical generator; the current `scripts/generate-service-topology.py` does not yet export them to `catalog/services.json`. The coordinated catalog-v2 cutover is still pending. Do not treat this metadata as an effective FastAPI runtime change.

## FastAPI / health probe integration contract

The live FastAPI #342 implementation reserves 10 high-priority selections and 2 rotating selections from a 12-target cycle. Replace the *selection accounting* with unit-aware cost accounting, but preserve anti-starvation rotation, budget caps and observer separation:

1. Deduplicate concurrent requests on `deploymentUnitId` (singleflight), cache within a short bounded TTL and expose `lastObservationAt`, `stale`, `skipped` and `evidenceSource`.
2. For Garage, one LAN probe sequence: S3 :3900 primary; Admin :3903 only when authorized/indicated; WebUI :3909 when needed. Keep three endpoint statuses and three exposure policies, with service-wide summary computed from primary/dependency evidence.
3. Derive prerequisite ordering from `dependsOn`/`consumesApi`, plus an explicit low-cost fallback order. Do not accidentally probe a protected Admin endpoint with unauthenticated high-frequency requests.
4. Count each unit once for scheduling, but track endpoint-level coverage and guarantee rotation even if the top-priority units saturate the budget.
5. Internal-only `external=false` means *policy*, not proof of network isolation. TrueNAS inventory + valid LAN probes establish internal runtime health; external observer provides separate outside-in WAN/Cloudflare evidence. No LAN evidence never means DOWN, and a Cloudflare timeout alone is warning/unknown, not service failure.
6. Record probe policy and upgrade policy separately: Watchtower never consumes health results directly for automatically restarting a multi-container stack. An update controller reads reviewed unit-level deployment policy and holds a per-unit lock.

## Required security gates

- Check for an existing Watchtower app/container on TrueNAS before creating any new one. **Two simultaneous controllers are forbidden.**
- Docker Unix socket mounted `:ro` is **not** read-only authorization; it is root-equivalent. Initial profile requires explicit administrator action; test a policy-enforcing read-only proxy or separate image-update checker before unattended operation.
- Pin the release image by immutable digest after verification, scan it for vulnerabilities, and confirm the fork's update cadence. No untrusted automatic updates of images pinned to immutable digest.
- Keep PostgreSQL, Redis, Kafka, ClickHouse, Garage, Traefik, Cloudflared, Vaultwarden, Homarr and any unreconciled TrueNAS Native Apps out of unattended upgrades.
- Automatic upgrades of any container require backup compatibility, a post-update smoke, observable rollback preparation and a reviewed ownership mapping. Compose `up -d` is not an atomic transaction.
- Run `python3 scripts/security/check-watchtower-unit-policy.py --check` and `python3 -m pytest -q tests/test_watchtower_unit_policy.py` in the real checkout, then full local-first quality gate. No merge or TrueNAS deployment before acceptance.

References: https://github.com/nicholas-fedor/watchtower/releases/tag/v1.23.1 and https://watchtower.nickfedor.com/.
