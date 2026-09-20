# Nabla service topology

`service-topology.json` is the **legacy v1** generated design-time graph. It remains operational until the coordinated v2 cutover.

The v2 target is Backstage-native: `catalog-info.yaml` owns entity identity and standard relations, Docker Compose owns runtime facts, provider resources own routing/exposure, and FastAPI derives observed state. See `docs/service-catalog-v2-normalization.md`.

Compose `depends_on` remains authoritative for same-project startup dependencies. Backstage `spec.dependsOn` becomes authoritative for cross-entity functional dependencies. Do not repeat either relation in x-nabla.

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
- minimal x-nabla: exceptional `after/before/wants`, rare edge enrichment and
  structured risk acceptance only.

The preferred v2 service has **no x-nabla block**.

The migration mapping from legacy x-nabla fields to Backstage/Compose/provider
sources is intentionally retained in
`docs/service-catalog-v2-normalization.md` as documentation after cutover.

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
