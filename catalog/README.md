# Nabla service topology

`service-topology.json` is the **legacy v1** generated design-time graph. It remains operational until the coordinated v2 cutover.

The v2 target is Backstage-native: `catalog-info.yaml` owns entity identity and standard relations, Docker Compose owns runtime facts, provider resources own routing/exposure, and FastAPI derives observed state. See `docs/service-catalog-v2-normalization.md`.

Compose `depends_on` remains authoritative for same-project startup dependencies. Backstage `spec.dependsOn` becomes authoritative for cross-entity functional dependencies. Do not repeat either relation in x-nabla.

## Observed resource reference (RAM / GPU / storage)

The canonical v2 `entityRef` is the join key for runtime resource
samples, not a field hand-edited into Backstage descriptors.
`scripts/truenas/collect-service-resource-evidence.py --check`
produces private, versioned `nabla-service-resources/v1` snapshots
of Docker working-set RAM, attributable NVIDIA GPU process memory,
Docker writable layers, and ZFS datasets mounted by a service.

No resource quantity is inferred from a container's name or image.
Unavailable data uses `null` with `unverified` status, never zero;
shared ZFS datasets are marked and must not be summed into a
per-service exclusive storage total. The service website can import
snapshots in OWNER mode without a public endpoint or cloud upload.
See [the resource runbook](../docs/runbooks/2026-10-26-homelab-service-resource-inventory.md).

## Web icon source of truth

`catalog/service-icons.json` owns two distinct *presentation projections*:
`icons` (legacy graph emoji) and `webAssets` (per-service bundled file names).
Neither is a runtime-health authority. A child service may inherit a parent
application icon. Product-specific original pictograms are permitted when an
upstream logo is unavailable; record attribution at the website asset. All new Backstage Components/Resources, legacy graph icon names and homelab service IDs
must resolve to a specific `webAssets` entry (or to a parent entry).
`tests/test_service_icon_web_assets.py` enforces this contract.

The website owns the actual licensed SVG/PNG files, **not** the service-to-icon
mapping. Synchronize its checked-in generated TypeScript snapshot offline:

```sh
cd ../nabla-site-alban
node scripts/sync-homelab-icons.mjs --source ../nabla-compose/catalog/service-icons.json
node scripts/sync-homelab-icons.mjs --source ../nabla-compose/catalog/service-icons.json --check
```

No Next.js build-time GitHub download, runtime icon CDN, or separate hand-edited
site catalog is required. The older `catalog/homelab-services.json.iconSrc`
fields are deprecated legacy v1 output; do not add new icon ownership there.
Retire them after the last v1 consumer migrates.

## Ownership

### Current v1

Current generation still reads service-local `x-nabla` plus transitional static
topology and emits `services.json` / `service-topology.json`.

### Target v2

Use one authority per concern:

- Backstage `catalog-info.yaml`: entity identity, title/description, type,
  lifecycle, ownership, System/Domain membership and standard relations;
- Compose: project/service/image/ports/networks/healthcheck/profiles/depends_on;
- Traefik / Cloudflare / pfSense HAProxy / Kubernetes Gateway API: routing and
  exposure;
- TrueNAS/Docker/Kubernetes EndpointSlice: observed runtime backends;
- minimal x-nabla: exceptional `after/before/wants`, rare edge enrichment,
  structured risk acceptance, and temporary desired exposure intent only when a
  provider still lacks a native Git/IaC desired-state source.

The preferred v2 service has **no x-nabla block**.

### Consumer projections already on v2 (PR #265)

Backstage + Compose now generate Homarr entries and enrich Gatus monitor IDs.
Gatus probe targets/conditions are maintained **in Gatus-native format**
at `config/monitoring/gatus-endpoints.yml`, outside the mounted Gatus
runtime configuration directory. AutoKuma is derived from those same probes:
no independent monitor inventory or generic-port monitoring fallback.

```bash
python scripts/generate-service-consumers.py --check
python scripts/generate-catalog-v2-artifacts.py --check
```

The v2 read models are `catalog/generated/entities.json` and
`catalog/generated/homelab.cdx.json`. Current coverage (20 October 2026):
95 Backstage entities, 85 Homarr entries, 85 Gatus probes and 85 AutoKuma
monitors; the CycloneDX projection represents 92 Component/Resource/API entities
and excludes organizational entities (Group/System/Domain). The 143 historical Homarr entries were migrated once from exact Compose service\nprovenance into Backstage descriptors and explicit entity-ref labels. Their\noriginal v1 inventory is not needed by the three consumers.

`catalog/service-consumers.static.yml` has been removed; Homarr's Docker
proxy endpoint/network and the homelab host binding are now derived from its
Compose file.

The v1 JSONs remain temporarily for **other** scripts and repositories;
they are not read by the three updated consumers.

The migration mapping from legacy x-nabla fields to Backstage/Compose/provider
sources is intentionally retained in
`docs/service-catalog-v2-normalization.md` as documentation after cutover.

## Criticality and business continuity

Do not collapse all forms of importance into one field.

- `metadata.labels['albandrieu.com/operational-criticality']` is the technical
  service criticality and projects to OpenTelemetry `service.criticality`.
- `metadata.labels['albandrieu.com/business-criticality']` is calculated from
  Business Impact Analysis inputs and remains independent from runtime health,
  vulnerability severity and graph centrality.
- BIA inputs are scalar Backstage annotations using MTPD/DMTP (DIMA/DMIA
  business concept), RTO, applicable RPO, MBCO/OMCA, impact dimensions,
  assessment status and review date.
- `catalog/business-criticality-policy.yaml` is the single source for the
  Nabla tier thresholds; the standards define the BIA concepts, not those local
  numeric/time boundaries.
- Current pilot BIA values are `provisional`; only reviewed assessments may
  become `validated`.
- Every materialized Component/Resource must declare `operational-state`.
  Active entities also choose `bia-scope=direct|inherited`.
- `direct` entities own a complete BIA; data-bearing direct types listed by
  policy must include RPO.
- `inherited` technical subcomponents deliberately carry no own business BIA;
  `effectiveDependencyCriticality` is derived through required Backstage
  `dependsOn` edges, never overwrites `ownBusinessCriticality`, and records
  the upstream `inheritedFrom` drivers.

Validate the BIA/criticality contract as part of the catalog gate:

```bash
python scripts/audit-service-catalog-v2-parity.py --check
python -m unittest tests.test_business_criticality -v
```

High/critical business entities must ultimately link to tested PCA/PRA/DRP
recovery evidence proving the expected RTO/RPO and minimum continuity objective.

## Service environments

`x-nabla.environments[]` is the canonical source for deployment instances.
A display name, hostname, IP address or suffix must never imply an environment.

- one logical service may expose multiple named environments (for example
  FastAPI Sample has `production` and `staging` instances);
- consumers should use generated `catalog/services.json` or
  `catalog/service-topology.json` environment metadata first;
- legacy presentation entries without topology environment metadata default to
  `production` until explicitly reviewed;
- `dev` and `staging` are never inferred from a service display name.

The fallback is presentation-only metadata. It does not change Docker lifecycle,
Cloudflare exposure, runtime health propagation, or dependency semantics.

Use the audit helper to review entries that are still relying on the production
default:

```bash
python scripts/audit-homelab-environments.py
```

## Boot / reconciliation policy

### Current v1

`x-nabla.lifecycle.phase/priority/blocksLaterWaves` remains consumed by the
existing TrueNAS reboot planner until v2 is implemented and runtime-accepted.

### Target v2

Delete the global phase/priority/wave model.

The resume planner becomes a dependency DAG reconciler:

1. Compose `depends_on` gives same-project dependencies and health/completion
   conditions.
2. Backstage `spec.dependsOn` gives required cross-entity dependencies.
3. Dependents wait for readiness evidence.
4. Independent branches reconcile concurrently.
5. x-nabla `after/before` is reserved for rare systemd-style order-only
   constraints.
6. x-nabla `wants` is reserved for rare weak/optional dependencies.

There is no v2 replacement `target`, `phase`, `priority` or
`blocksLaterWaves` field.

Kubernetes provides the complementary operational model: initialization and
readiness gate traffic rather than imposing one global application startup
sequence.

## Generation

Generate the portable catalog with:

```bash
python scripts/generate-service-topology.py
```

Verify that the committed artifact is synchronized with its sources with:

```bash
python scripts/generate-service-topology.py --check
```

The pre-commit policy runs the generator whenever relevant Compose metadata, the transitional static topology, or the generator itself changes. `catalog/service-topology.json` and `catalog/services.json` are generated artifacts and must not be edited manually.

During the incremental migration, `service-topology.static.json` retains nodes and relations that have not yet moved into service-local `x-nabla` blocks. It is merged with `x-nabla` metadata by the generator. The target state is to remove that transitional file once all useful relations are co-located with their deployment configuration.

## Relation semantics

Backstage well-known relations become the canonical declared graph:

- `dependsOn`;
- `providesApi`;
- `consumesApi`;
- System/Domain membership / `partOf`;
- ownership.

Do not create a second x-nabla edge such as `storesIn` when a Backstage
`dependsOn` to a typed database Resource already expresses the relationship.

Runtime/provider-derived relationships such as hosting, routing, public exposure
and observation belong to the observed graph. They may be enriched in
Cartography/Neo4j with provenance.

Custom relation metadata is retained only when the distinction cannot be
represented by Backstage, cannot be derived from provider/runtime evidence, and
is used by a concrete security/operational query.

## Declared vs observed graph

The declared catalog describes intended architecture. It should eventually be compared with an **observed** service graph derived from OpenTelemetry traces (for example Tempo/Grafana service-graph metrics). These two sources answer different questions:

- declared: *what should talk to what?*
- observed: *what actually talked to what?*

A future UI can highlight `declared-only`, `observed-only` and `declared+observed` edges to detect topology drift without changing deployment order.


## Operational intent

The v2 operational state is a qualified Backstage label, separate from
`spec.lifecycle`:

```yaml
metadata:
  labels:
    albandrieu.com/operational-state: active
```

Allowed values remain `active | planned | disabled`.

Backstage `spec.lifecycle` continues to describe catalog/software lifecycle
(`experimental | production | deprecated`) and must not be used as a boot-state
substitute.

Runtime health never overwrites declared operational state.

### Security taxonomy and evidence boundaries

See [catalog-security-standards.md](../docs/catalog-security-standards.md) for the
Backstage/Compose/Gatus/CycloneDX/OCSF/OSCAL/OTel roles, the correlated
Scanopy/Cartography/Akvorado/ntopng/DSOMM workflow, and its secure-by-design
audit. A discovered IP/flow/host is **not** a new Backstage service identity.

### AutoKuma native output (v2)

AutoKuma does **not** read a JSON array as one static monitor. Its 2.x Files
provider expects one JSON object per file, and uses the filename as ID.
The canonical Gatus probes generate an intermediate array under
`apps/autokuma/static/generated-monitors.json` (not mounted). On TrueNAS,
`scripts/truenas/deploy-autokuma.sh` materializes individual native
`/mnt/cpool/autokuma/static-monitors/nabla-<monitor-id>.json` files before
reconciliation. No second editable inventory is introduced. See
`apps/autokuma/README.md`.
