# Service catalog v2 normalization and one-shot cutover

Last reviewed: 2026-11-06.

This document refines the architecture in
`docs/service-catalog-security-graph.md`. The goal is to minimize Nabla-specific
schema while keeping the operational semantics needed by the homelab.

## Status (2026-11-06)

- Backstage descriptors (`apps/<app>/catalog-info.yaml`,
  `catalog/catalog-info.yaml`) and the generated read models
  `catalog/generated/{entities,homelab.cdx,identity-map}.json` are committed;
  `python scripts/generate-catalog-v2-artifacts.py --check` fails on stale
  output.
- Homarr, Gatus and AutoKuma consume Backstage v2 directly (PR #265, 21/10).
- The v1 files (`services.json`, `service-topology.json`,
  `homelab-services.json`, `homelab-exposure-overrides.json`) remain for other
  scripts and repositories: destructive cleanup (P2.1.f) is **not done** and
  stays gated on the parity audit (see *Materialization debt workflow*).
- Pre-commit hooks `catalog-v2-preparation-contract`,
  `catalog-v2-native-identity-contract` and `catalog-v2-pilot-contract` run the
  parity audit and the catalog tests when these sources change.
- 2026-11-13 (P2.1.c): every legacy row's exposure intent lives in
  `x-nabla.exposure` (see *Route intent as authored and projected*) and the
  parity audit fails on any legacy/v2 difference (`routeIntentParityMismatches`,
  two documented owner decisions excepted). Legacy-only services became
  Backstage entities in `catalog/catalog-info.yaml` with a **provisional** BIA
  awaiting owner review.

### Route intent as authored and projected

- A Compose service declares routes in `services.<svc>.x-nabla.exposure`;
  `backendPort` names a long-syntax port. `entityRef` assigns a route to a
  logical endpoint served by another container (Garage Admin, Sentry edge).
- An entity without a Compose port (TrueNAS catalog App, workstation instance,
  pfSense, host networking) declares `backend: scheme://host:port` instead, in
  a root `x-nabla` block of its descriptor or on its Compose service.
- `riskAcceptance` sits on the route it concerns: `status: accepted` for a
  tolerated exposure, `rejected` when any exposure beyond `visibility` is drift.
- `probePriority` became `x-nabla.deploymentUnit.probePolicy.rank` (with
  `primaryEndpoint`/`secondaryEndpoints`, or the existing `probeOrder`), and
  `probePolicy.rank` on a static descriptor.
- `generate-catalog-v2-artifacts.py` projects all of this onto each entity of
  `entities.json` under `x-nabla`: `exposure[]` with a resolved
  `backend {host, port, appProtocol}` (`host_ip`, or the
  `albandrieu.com/lan-address` annotation of the deployment host, TrueNAS by
  default) and `probePolicy {deploymentUnit, rank, position}`. Consumers sort
  probes by `(rank, position)` and join on the full entity ref only.

## Executive decision

Do **not** grow `x-nabla` into a clone of Backstage. Use the standards where they
already exist:

- **Backstage `catalog-info.yaml`** for catalog identity, ownership, component /
  resource / API classification, lifecycle, system membership, standard
  dependencies and source links.
- **Docker Compose** native fields for runtime topology that Compose already knows:
  project name, service name, image, ports, networks, healthcheck, depends_on,
  profiles, configs, secrets and labels.
- **Docker labels** only for runtime correlation, using reverse-DNS names.
- **OpenTelemetry semantic conventions** as the runtime/telemetry identity model:
  `service.name`, `service.namespace`, `service.version`,
  `service.criticality` and `deployment.environment.name`.
- **CycloneDX 1.7** for service/SBOM identity, endpoints, authentication,
  trust-zone/trust-boundary and dependency graph projection.
- **NIST CSF 2.0** for security-function classification.
- **Cartography / Neo4j** for observed graph correlation and attack-path analysis.

Retain `x-nabla` only for information with no sufficiently good standard
representation **after Backstage, Compose and provider control planes have been
consulted**:

1. operational state is a qualified Backstage label
   (`albandrieu.com/operational-state`), not a second service identity;
2. boot metadata exists only for exceptional cross-application ordering that
   cannot be derived from Backstage `dependsOn`, Compose `depends_on` and
   readiness;
3. **desired exposure/security intent remains declared in Git** until the real
   provider configuration is itself Git/IaC-managed; provider APIs are observed
   state, never the sole memory of what should exist;
4. endpoint/backend facts derivable from Compose/Kubernetes/providers are not
   copied into the intent model;
5. custom relation metadata is exceptional and only enriches a standard edge;
6. structured risk acceptance remains a legitimate custom policy payload.

A standard relation is authored exactly once:
`spec.dependsOn: [resource:default/neo4j-security]` is the canonical Cartography
→ Neo4j dependency and must not be repeated as an `x-nabla` `storesIn` edge.

This is a deliberate breaking v2 cutover. Do not maintain a long-lived v1/v2
compatibility layer.

Why separate files: putting Backstage structure inside a Compose vendor
extension would look like Backstage without being consumable by Backstage. The
real descriptor sits next to the real deployment:

- `apps/<app>/catalog-info.yaml` = what the entity **is**;
- `apps/<app>/compose.yml` = how it **runs**;
- minimal `x-nabla` = Nabla-specific operational policy.

## Migration mapping: legacy x-nabla -> Backstage / Compose / minimal x-nabla

Keep this mapping as migration documentation even after the cutover. It explains
where every legacy field moved and prevents reintroducing a parallel catalog.

| Legacy x-nabla | Target authority | Target |
| --- | --- | --- |
| `id` | Backstage | `metadata.name` |
| `name` | Backstage | `metadata.title` |
| `description` | Backstage | `metadata.description` |
| `kind` | Backstage | entity `kind` + controlled `spec.type` |
| `category` | Backstage | `metadata.tags` |
| `presentationRole` | Site/UI | presentation configuration only |
| `criticality` | Backstage/OTel | legacy operational criticality -> `albandrieu.com/operational-criticality`, projected to OTel `service.criticality`; business criticality is a separate BIA-derived label |
| `securityFunctions` | Backstage/NIST | `nist-*` tags |
| `status` | Backstage label | `metadata.labels['albandrieu.com/operational-state']` |
| `lifecycle.phase` | delete | derive boot order from dependency graph/readiness; no phase replacement |
| `lifecycle.priority` | delete | deterministic topological ordering is a planner implementation detail, not service metadata |
| `lifecycle.blocksLaterWaves` | delete | required dependencies block their dependents; unrelated services continue reconciling |
| `runtime.containerService` | Compose | service key |
| `runtime.networks` | Compose | `networks` |
| `runtime.appId` | Compose/exception | top-level project `name`; retain override only on real mismatch |
| `sourcePath` | Backstage/Git | source-location annotation + discovery path |
| `url/internalUrl` | split desired/observed | internal backend facts derive from Compose/Kubernetes; desired public hostname/exposure is temporarily retained as Git route intent until provider-native IaC owns it; provider APIs supply observed state |
| `monitoring` | Compose/Kubernetes/observer | native Compose `healthcheck`; Kubernetes startup/readiness/liveness semantics; FastAPI cross-plane observations |
| `partOf` | Backstage | System/Domain membership |
| `dependsOn` | Backstage / Compose | `spec.dependsOn`; native `depends_on` intra-project |
| `providesApi/consumesApi` | Backstage | API entity refs |
| `storesIn` | normally delete | use Backstage `dependsOn` + target Resource type; enrich only if a real query requires more |
| `hostedBy` | derive | Compose/TrueNAS/Kubernetes runtime observation |
| `routesTo/exposedBy` | split desired/observed | desired route/exposure intent stays in Git; actual route/backend is derived from Traefik/Cloudflare/pfSense/Kubernetes observations |
| `observedBy` | derive | observability configuration/runtime |
| `authenticatesVia` | Backstage dependency or rare enrichment | identity Resource/API dependency; enrich only when needed |
| `automates` | derive or rare enrichment | automation/API relationship when standard relations are insufficient |

## Target repository layout

```text
catalog/
├── catalog-info.yaml                  # Domain/System/Group + static infra
├── service-icons.json                 # presentation only; not security truth
├── business-criticality-policy.yaml   # Nabla tier thresholds over BIA inputs
└── generated/                         # Backstage-shaped JSON, identity map,
                                       # CycloneDX 1.7 aggregate BOM
apps/<app>/
├── catalog-info.yaml
└── compose.yml
```

The generator validates and joins these sources; it must not create a second
manually-maintained service inventory.

## Backstage entity taxonomy

Use native Backstage kinds instead of the old free-form `kind`:

- **Component** — deployable software/processes (FastAPI Sample, Prometheus,
  Grafana, Traefik, Cartography, exporters, workers, collectors, controllers,
  websites). Controlled `spec.type`: `service`, `website`, `worker`, `job`,
  `controller`, `collector`, `exporter`, `proxy`, `security-tool`,
  `ai-service`. Keep the list small.
- **Resource** — infrastructure/stateful dependencies: `database`,
  `graph-database`, `cache`, `object-storage`, `message-broker`,
  `search-engine`, `kubernetes-cluster`, `host`, `virtualization-platform`,
  `network`, `dns`, `identity-provider` (e.g. PostgreSQL → database, Neo4j →
  graph-database, Redis → cache, Garage/MinIO → object-storage, Kafka →
  message-broker, TrueNAS → virtualization-platform).
- **API** — only for stable interfaces with a real contract (OpenAPI,
  AsyncAPI, GraphQL, gRPC, MCP server); not merely because a web UI listens on
  HTTP.
- **System / Domain / Group** — `Domain: nabla`, `System: nabla-homelab`,
  `Owner: group:default/nabla-platform`. Keep categories (`security`,
  `observability`, `network`, `data`, `ai`) as tags; do not create dozens of
  Systems to replace a category string.

## Backstage metadata conventions

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: cartography
  title: Cartography
  description: Security asset and relationship ingestion into Neo4j.
  tags:
    - security
    - nist-identify
    - nist-detect
  labels:
    albandrieu.com/operational-state: active
    albandrieu.com/operational-criticality: low
    albandrieu.com/bia-scope: direct
  annotations:
    backstage.io/source-location: url:https://github.com/AlbanAndrieu/nabla-compose/tree/master/apps/cartography/
    github.com/project-slug: AlbanAndrieu/nabla-compose
spec:
  type: job
  lifecycle: production
  owner: group:default/nabla-platform
  system: system:default/nabla-homelab
  dependsOn:
    - resource:default/neo4j-security
```

Rules:

- `metadata.name` is the canonical stable ID (lowercase kebab-case).
- `metadata.title` is display text; `metadata.description` replaces duplicate
  UI descriptions.
- `metadata.tags` holds category and NIST CSF classifications.
- `metadata.labels` holds short queryable Nabla values.
- `metadata.annotations` holds source/external-system references.
- `spec.lifecycle` (`experimental | production | deprecated`) is the
  software/catalog lifecycle, not boot order. The operational
  `active | planned | disabled` state is a different concept and stays in the
  `albandrieu.com/operational-state` label.

## Business criticality and BIA

Keep **business criticality** separate from **operational criticality**.

- `albandrieu.com/operational-criticality` describes the technical/operational
  importance of the service and is projected to OpenTelemetry
  `service.criticality` (`critical | high | medium | low`).
- `albandrieu.com/business-criticality` describes the business impact of loss
  or disruption and is **calculated from BIA inputs**.
- Do not infer one from the other. A technically central platform can have low
  current business criticality when it hosts no business workload, while a
  simple application can be business-critical.

### Standards vocabulary

Use ISO terminology as the canonical vocabulary:

- **MTPD / DMTP** — maximum tolerable period of disruption / durée maximale
  tolérable de perturbation. The French ISO vocabulary also lists **DMIA**.
  Existing Nabla/organizational wording **DIMA** maps to this same concept and
  must not become a second field.
- **RTO** — recovery time objective / objectif de délai de rétablissement.
  RTO must be lower than MTPD/DMTP.
- **RPO** — recovery point objective / point de rétablissement des données.
  Applicable to data-bearing services; may be omitted for a stateless or
  rebuildable service.
- **MBCO / OMCA** — minimum business continuity objective / objectif minimal de
  continuité d'activité. A qualitative minimum acceptable service level; do not
  force it into a numeric score.

ISO/TS 22317 requires the BIA to consider impact over time,
legal/regulatory/contractual obligations, resources and dependencies. NIST SP
800-34 uses MTD/RTO/RPO and recovery priorities; NIST IR 8286D extends BIA to
financial, reputational, operational and regulatory consequences.

- ISO/TS 22317:2021 — https://www.iso.org/standard/79000.html
- ISO 22300:2025 vocabulary — https://www.iso.org/obp/ui/en/#iso:std:iso:22300:ed-4:v1:fr
- NIST SP 800-34 Rev. 1 — https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final
- NIST IR 8286D-upd1 (2025) — https://csrc.nist.gov/pubs/ir/8286/d/upd1/final

### Backstage representation

A queryable calculated label plus scalar annotations:

```yaml
metadata:
  labels:
    albandrieu.com/operational-criticality: medium
    albandrieu.com/business-criticality: high
  annotations:
    albandrieu.com/bia-mtpd: P1D
    albandrieu.com/bia-rto: PT4H
    albandrieu.com/bia-rpo: PT1H
    albandrieu.com/bia-mbco: minimum-service-description
    albandrieu.com/bia-status: provisional
    albandrieu.com/bia-reviewed-at: "2026-09-21"
    albandrieu.com/bia-impact-operational: high
    albandrieu.com/bia-impact-customer: medium
    albandrieu.com/bia-impact-financial: low
    albandrieu.com/bia-impact-legal-regulatory: medium
    albandrieu.com/bia-impact-reputation: medium
    albandrieu.com/bia-impact-confidentiality: medium
    albandrieu.com/bia-impact-integrity: high
    albandrieu.com/bia-impact-privacy: medium
```

Durations use the bounded ISO-8601 subset of the repository policy
(`PT15M`, `PT4H`, `P1D`, `P3D`, ...).

### Calculation policy

`catalog/business-criticality-policy.yaml` is the single source for the tier
thresholds, deliberately identified as **Nabla policy**, not ISO/NIST
thresholds. Current method: `max-of-drivers`.

1. Convert MTPD, RTO and applicable RPO into a
   `low | medium | high | critical` tier using the policy thresholds.
2. Convert each assessed impact dimension (`operational`, `customer`,
   `financial`, `legal-regulatory`, `reputation`, `confidentiality`,
   `integrity`, `privacy`) into the same vocabulary.
3. Business criticality is the most severe driver.
4. Report the driver list and the recovery margin `MTPD - RTO`.
5. Fail the catalog gate if `RTO >= MTPD`, duration syntax is invalid, an
   impact value is unknown, or the declared business-criticality label differs
   from the calculated value.

The dimensions are a compact, reviewable projection of ISO/NIST BIA concerns,
not a universal scoring standard.

### Assessment maturity

Pilot values (PR #215) use `albandrieu.com/bia-status: provisional`. A passing
gate does **not** mean the BIA is approved: `validated` is reserved for an
assessment reviewed by the responsible owner, and bulk migration must never
silently turn provisional values into validated ones.

### Coverage gate

- every materialized Backstage `Component` / `Resource` declares
  `albandrieu.com/operational-state`, so BIA scope cannot be bypassed by a
  missing label;
- every `active` Component/Resource declares
  `albandrieu.com/bia-scope: direct | inherited`;
- `direct` owns a BIA and requires a business-criticality label, MTPD/DMTP,
  RTO, MBCO/OMCA, assessment status, review date and at least one assessed
  impact dimension; data-bearing `direct` types listed in
  `catalog/business-criticality-policy.yaml` also require RPO;
- `inherited` does **not** duplicate a BIA: its effective criticality comes
  from required dependents through the Backstage graph;
- `planned` / `disabled` entities may stay incomplete until activation; their
  missing BIA is explicit lifecycle debt, not an inferred low criticality.

### Dependency amplification

Never overwrite an infrastructure Resource's own BIA because a critical service
depends on it. The read model reports `ownBusinessCriticality`,
`effectiveDependencyCriticality` (transitive over required Backstage
`spec.dependsOn` edges), whether the entity was elevated, and the upstream
business entities in `inheritedFrom`. Duplicate entity refs, malformed
dependencies and unresolved refs fail closed. This preserves provenance and
prevents recursive score inflation.

## Kubernetes model: do not flatten catalog, network and status

Kubernetes does not keep one manually merged `services + exposure overrides`
inventory; it splits concerns and reconciles them:

| Concern | Kubernetes source | Nabla equivalent |
| --- | --- | --- |
| application identity | recommended `app.kubernetes.io/*` labels + workload metadata | Backstage entity ref + Compose project/service |
| desired workload | Deployment/StatefulSet/Pod `spec` | Compose |
| stable internal service | Service | derived Compose/Kubernetes service surface |
| concrete healthy backends | EndpointSlice | Docker/TrueNAS or Kubernetes runtime observations |
| external routing | Gateway + HTTPRoute/GRPCRoute/TCPRoute | Traefik labels, Cloudflare Tunnel routes, pfSense HAProxy, Kubernetes Gateway API |
| reachability policy | NetworkPolicy / implementation policies | Kubernetes NetworkPolicy plus edge-provider policy |
| process health | startup/readiness/liveness probes | Compose healthcheck + observer probes, normalized to Kubernetes semantics |
| current state | resource `status.conditions` | FastAPI observation conditions |

Consequences: desired and observed state stay separate; desired public
exposure must survive a Cloudflare/Docker/TrueNAS outage; endpoints are not
copied into catalog identity because a UI finds them useful; while a provider is
not Git/IaC-managed, Nabla keeps the intended route/security policy in Git and
provider APIs report whether it is realized; runtime backend addresses are
observations (like EndpointSlices); consumers join resources through stable
references. Losing the controller does not erase the desired `spec`.

### Kubernetes-style metadata and status

Generated Kubernetes resources use the recommended `app.kubernetes.io/name`,
`instance`, `version`, `component`, `part-of` and `managed-by` labels, with
`app.kubernetes.io/name` = Backstage `metadata.name` (no second
Kubernetes-only ID). Docker/Compose runtime correlation uses only
`com.albandrieu.nabla.entity-ref=component:default/example`.

FastAPI normalizes runtime/network observations into conditions
(`type`, `status`, `reason`, `message`, `lastTransitionTime`; e.g.
`Ready=True reason=HealthcheckPassed`) rather than storing another declared
catalog. Condition types: `Ready`; `Healthy` / provider-specific health where required;
`Accepted`, `Programmed`, `ResolvedRefs` for route reconciliation; `Available`
for workload availability; `Degraded` only as a derived presentation state.
`status` is `True | False | Unknown`, plus `observedGeneration`/revision where
applicable. Keep `Unknown` when evidence is stale or unavailable: missing
Cloudflare evidence must not fabricate a failure.

### Gateway API as the exposure model

```text
Gateway/listener -> HTTPRoute/TCPRoute -> (backendRef) Service -> EndpointSlice / runtime backends
```

For the non-Kubernetes TrueNAS stack, **do not create fake Kubernetes HTTPRoute
objects merely to look standard**. Provider adapters project existing sources
into the same concepts:

- Traefik labels -> Route + backend;
- Cloudflare Tunnel Public Hostname -> Route + origin;
- Cloudflare Access Application/Policy -> route authorization policy;
- pfSense HAProxy frontend/backend -> Gateway/listener + Route + backend;
- Compose published port -> Service-like internal surface;
- TrueNAS/Docker container -> observed backend.

Kubernetes workloads consume native Service/EndpointSlice/Gateway API objects.

### Desired exposure intent while providers are not fully IaC-managed

Inferring all exposure from provider state would lose security intent during an
outage or API authorization failure. Until Cloudflare/pfSense exposure is
managed declaratively in Git, keep a **small route-intent spec** beside the
service (Gateway API concepts, no fabricated Kubernetes objects):

```yaml
x-nabla:
  exposure:
    - name: public
      hostnames:
        - fastapi-sample.albandrieu.com
      protocol: HTTPS
      visibility: public
      gatewayRef: resource:default/cloudflare-tunnel
      backendPort: web
      access:
        required: true
```

The Compose port is named once (long syntax), so the exposure spec does **not**
repeat IP, numeric port, container name or runtime health:

```yaml
ports:
  - name: web
    target: 8080
    published: "8091"
    host_ip: 172.17.0.24
    protocol: tcp
    app_protocol: http
```

- `hostnames` = desired names that must exist even when the provider is down;
- `protocol` = desired listener/application transport;
- `visibility` = intended boundary (`public | lan | cluster | host`);
- `gatewayRef` = Backstage entity ref of the desired edge/gateway provider;
- `backendPort` = named Compose/Kubernetes port, not a duplicate number;
- `access.required` = desired protection intent, independent of whether the
  Cloudflare Access API can currently prove it.

FastAPI exposes `spec` (desired route intent from Git) and `status`
(`Accepted`, `ResolvedRefs`, `Programmed`, `AccessProtected`, `Ready`). If
Cloudflare is unreachable, the desired hostname and `access.required` remain,
and `Programmed` / `AccessProtected` become `Unknown`. **Never convert a
provider outage into `external=false`.**

### Future migration of route intent

The route-intent extension is transitional. Traefik routing stays native
Traefik labels/config in Git; Kubernetes workloads move to Gateway API;
Cloudflare Tunnel/Access moves to an OpenTofu/Terraform provider when
introduced; pfSense HAProxy moves to a reviewed API/IaC source when safe. Once a
provider has a real declarative Git source, delete the duplicate
`x-nabla.exposure` record: provider-native configuration becomes `spec`,
FastAPI/provider observation remains `status`.

## Separate Backstage lifecycle from boot semantics

Backstage `spec.lifecycle` stays the catalog/software lifecycle. For
reboot/startup, combine systemd's distinction between requirement
(`Requires`/`Wants`) and ordering (`After`/`Before`) with the Kubernetes lesson:
no global boot phase when controllers can reconcile independently and gate on
readiness.

### Target boot algorithm

The TrueNAS resume planner:

1. discovers active entities from the qualified operational-state label;
2. derives same-project dependencies from Compose `depends_on`;
3. derives required cross-entity dependencies from Backstage `spec.dependsOn`;
4. waits for the dependency's declared readiness evidence before unblocking a
   dependent;
5. starts/reconciles independent branches concurrently;
6. uses systemd-style `after` / `before` only for exceptional order-only
   constraints and `wants` only for a weak/optional dependency;
7. keeps retry/reconciliation idempotent instead of requiring one global phase
   to finish perfectly.

The legacy `lifecycle: {phase, priority, blocksLaterWaves}` block is deleted and
**has no v2 replacement**. Required dependencies block only their dependents: a
failed Vaultwarden recovery does not block an unrelated PostgreSQL branch.

### Exceptional boot metadata

Most services have no boot block. When a true order-only or weak constraint
exists:

```yaml
x-nabla:
  boot:
    after:
      - resource:default/special-host-service
    before:
      - component:default/consumer
    wants:
      - component:default/optional-observer
```

`after` / `before` express ordering only; `wants` a weak dependency; required
dependencies stay in Backstage `spec.dependsOn` and intra-project ones in
Compose `depends_on`. There is no `target`, `phase`, `priority`,
`blocksDependents` or duplicate `requires` field. The result is a DAG
reconciliation planner, not a custom wave scheduler.

## Minimal x-nabla v2

The preferred state is **no `x-nabla` block at all** for a normal service (see
the Cartography example). Use the extension only when a source cannot yet be
represented by a provider-native Git/IaC object or derived elsewhere:
`exposure` (route intent) and `boot` (exceptional ordering), both described
above, plus:

```yaml
x-nabla:
  riskAcceptances:
    - id: truenas-public-admin
      status: accepted
      reason: ...
      control: tls-and-api-auth
      reviewAfter: null

  relationMetadata:
    - relation: component:default/example->resource:default/special-resource
      semantic: custom-semantic-not-representable-by-backstage
      evidence:
        - apps/example/compose.yml:SOME_CONFIG
```

`relationMetadata` is exceptional. If removing it does not lose a concrete
security/operational query, remove it.

## Normalize Compose itself

1. **Top-level project name** — every repository-managed application declares
   `name: <app>`. This gives catalog, runtime and TrueNAS reconciliation a
   stable identity; keep a `runtime.appId` override only where the TrueNAS App
   ID cannot equal the project name.
2. **No unnecessary `container_name`** — Compose already provides
   `com.docker.compose.project` / `com.docker.compose.service`. Keep
   `container_name` only when a verified external integration needs the literal
   name.
3. **One runtime correlation label** —
   `com.albandrieu.nabla.entity-ref: resource:default/neo4j-security`. The
   reverse-DNS `com.albandrieu.nabla.*` namespace avoids collisions with
   `com.docker.compose.*`, `org.opencontainers.*` or `traefik.*`; the value is
   the full entity ref, unambiguous across kinds and namespaces. Compose puts it
   on the live container, so Docker/TrueNAS observers join runtime state to the
   entity without guessing from names. Do not use a Backstage annotation for
   this join (Docker never materializes annotations on a container), and do not
   overload Docker labels with catalog metadata: identity, ownership, lifecycle,
   BIA and business metadata stay in Backstage.
4. **Derive instead of duplicate** — project from `name`, service from the key,
   image, networks, ports (long syntax: `name`, `target`, `published`,
   `host_ip`, `protocol`, `app_protocol`), manual/job intent from `profiles`,
   local edges from `depends_on`, health from `healthcheck`, restart semantics,
   configs and secrets. Require metadata only when it cannot be derived safely.
5. **Health checks** — native Compose `healthcheck`, interpreted with Kubernetes
   probe semantics (startup / readiness / liveness). Cross-plane checks (LAN,
   public edge, Access-authenticated route, DNS, WebSocket, functional
   dependency) are FastAPI observations producing conditions, not identity
   metadata.
6. **Configs/secrets** — Compose `configs` for non-secret files, Compose
   `secrets` where the application supports file-based secrets, Vaultwarden-
   rendered `env_file` only where environment variables are required. Do not
   force file-based secrets for schema purity.
7. **OCI metadata** — for images Nabla builds, set
   `org.opencontainers.image.{source,revision,version,documentation,licenses}`
   at build time; never add misleading OCI labels to third-party images.
8. **Version/digest security** — pinned version and, for critical services, an
   immutable digest (CycloneDX identity, Trivy correlation, rollback,
   runtime-to-SBOM joins). Treat `:latest` as explicit supply-chain debt.

## OpenTelemetry identity alignment

```text
service.name                 = Backstage metadata.name
service.namespace            = nabla-homelab
deployment.environment.name  = production | staging | development | test
service.version              = deployed application/image version
service.criticality          = critical | high | medium | low
```

The service name stays stable across environments; do not invent IDs such as
`sample-production` unless they are genuinely different logical services.

## CycloneDX projection

Every Backstage component/resource maps to a deterministic reference
(`nabla:component:default/cartography`, `nabla:resource:default/neo4j-security`).
Map endpoints, authentication, trust boundary/zone, service hierarchy, data
flows and dependency references where semantics are lossless; keep richer
ingress/access/risk-acceptance details as namespaced CycloneDX properties.
Trivy package/image SBOMs remain separate artifacts linked through image digest
/ pURL and the entity ref.

## Relation normalization: one edge, one authority

Backstage well-known relations (`ownedBy`, `partOf`, `dependsOn`,
`providesApi`, `consumesApi`) are the canonical declared graph, authored
natively in `catalog-info.yaml`. Never author both `spec.dependsOn` and an
`x-nabla.relations` entry (e.g. `semantic: storesIn`) for the same logical
edge: Neo4j is already typed `Resource` / `graph-database`.

Keep relation metadata only when **all three** hold: Backstage cannot express
the distinction; runtime/configuration cannot derive it reliably; an
operational/security query uses it (e.g. an explicit authentication path, proxy
route or security observation path). Even then, enrich the existing edge.

Derivation policy: Compose `depends_on` for same-project runtime dependency;
Backstage `spec.dependsOn` for cross-entity functional dependency;
`providesApis` / `consumesApis` for APIs; System/Domain for `partOf`;
runtime/provider observations for hosting, routing and exposure; Neo4j
enrichment for observed attack-path semantics. `storesIn`, `hostedBy`,
`routesTo`, `observedBy`, `authenticatesVia`, `exposedBy` and `automates` are
removed from the mandatory authoring vocabulary; they may exist as
generated/observed semantics when evidence proves them.

## Cartography ontology alignment

Do not force the Nabla schema to match provider-specific Cartography nodes. Use
semantic labels at import:

```text
Backstage Component -> :NablaEntity:Application
Backstage Resource/database -> :NablaEntity:Database:DataStore
Backstage Resource/host -> :NablaEntity:ComputeInstance
API -> :NablaEntity:Service
```

Keep the mapping layer explicit so Nabla can follow Cartography's canonical
semantic labels without making its internal schema the Git authoring format.

## Delete homelab-services.json and homelab-exposure-overrides.json

Both files collapsed identity, endpoint discovery, desired exposure, observed
routing and presentation into one UI-oriented schema patched with precedence
overrides. **Do not replace them with another flat endpoint document**, and do
not discard the desired exposure/security intent they contain: first migrate it
into Backstage/Compose/provider-native Git sources or the temporary
`x-nabla.exposure` spec, then delete the legacy files in the coordinated
cutover. Delete the flat model, not the intent.

### homelab-services.json field disposition

| Old field | Source after cutover |
| --- | --- |
| `name` | Backstage `metadata.title` |
| stable identity | Backstage entity ref |
| `description` | Backstage `metadata.description` |
| `internalHost/internalPort` | Compose long-syntax ports or native Kubernetes Service |
| application protocol / TLS hint | Compose `ports[].app_protocol`, Traefik/Gateway route, or API entity |
| `internalPath` | actual route/probe source, not catalog identity |
| `tunnelUrl` | desired hostname -> route intent/provider IaC; actual route -> provider status |
| `external` | desired visibility -> route intent; actual exposure -> observed route/listener |
| `tunnelSecure` | desired protocol -> route intent; actual TLS -> listener/provider observation |
| `endpointEnabled` | desired route presence if meaningful -> spec; actual route/backend availability -> status |
| `healthNote` | condition `reason/message` or documentation |
| `internalTitle/tunnelTitle` | delete; presentation only |
| `icons/iconSrc` | Site presentation mapping |

### homelab-exposure-overrides.json field disposition

| Old field | Source after cutover |
| --- | --- |
| `external` | desired visibility in route intent; observed exposure in status |
| `tunnelUrl` | desired hostname in route intent; observed Cloudflare/Traefik/Gateway/HAProxy route in status |
| `tunnelSecure` | desired protocol in route intent; observed listener/route TLS in status |
| `cloudflareAccessRequired` | desired `access.required`; observed Access Application/Policy separately |
| `endpointEnabled` | desired presence only when intentional; observed route/runtime condition separately |
| `healthNote` | observation condition/documentation |
| `securityException` | structured risk acceptance only |
| `probePriority` | single global probe rank; folds into the deployment-unit `probePolicy` (PR #257), never a second ranking |

### Provider authority

| Plane | Desired state | Observed state |
| --- | --- | --- |
| internal Docker endpoint | Compose | TrueNAS/Docker observation |
| internal HTTP ingress | Traefik labels/config | Traefik routes |
| public Cloudflare route | Git route intent until Cloudflare is IaC-managed | Tunnel Public Hostname API |
| public authorization | route intent `access.required` until Access policy is IaC-managed | Access Application + attached policies + Service Token/live-edge evidence |
| direct WAN | route intent until pfSense HAProxy has a reviewed declarative owner | pfSense HAProxy frontend/backend |
| Kubernetes workload | Service + Gateway API manifests | EndpointSlice + Gateway status |

FastAPI provider adapters are the source of the network view; their results are
not copied into static JSON. A direct exposure needing a policy exception also
keeps a structured `riskAcceptance`. Do not add a generic
`external: true/false` Backstage field to recreate the old override file.

## Consumer contracts: FastAPI Sample and Site Alban

FastAPI is a **read-model / reconciler** (controller plus API view), not a
second declared inventory. It drops `homelab-services.json`,
`homelab-exposure-overrides.json`, `DeclaredService`, `DeploymentEnvironment`,
`RuntimeBinding`, `ServiceLifecycle` and `HomelabTopologyNode`, and consumes
Backstage entities/relations, temporary Git route/security intent,
Compose-derived runtime facts, TrueNAS/Docker and Kubernetes observations,
Traefik, Cloudflare Tunnel + Access and pfSense HAProxy observations, and
security findings/SBOM enrichments.

- **API shape:** resource-oriented views (`/api/catalog/entities`,
  `/api/catalog/relations`, `/api/runtime/observations`,
  `/api/network/routes`, `/api/network/backends`,
  `/api/security/findings-summary`); the health-board aggregate is generated
  from them and is not a source of truth.
- **Join key:** only the full entity ref (`component:default/prometheus`);
  never join runtime evidence on display names.
- **Cold start:** an optional generated last-known-good cache (e.g.
  `nabla/api/data/catalog-snapshot.json`) is an implementation cache, never
  hand-edited and never a third catalog; observations stay
  fresh/stale/unknown separately.

Site Alban uses the entity ref as React Flow node ID (not `Prometheus` /
`prometheus`), consumes Backstage metadata and relations, desired exposure
intent, FastAPI runtime observations and security enrichment separately, and
keeps only presentation-only icons/layout locally.

## Static infrastructure normalization

`catalog/service-topology.static.json` is replaced by `catalog/catalog-info.yaml`
(Domain/System/Group and static Resources such as TrueNAS, pfSense, Kubernetes,
Talos). Do **not** recreate a static endpoint inventory: endpoints and routes are
derived from provider configuration and observations. A small qualified
annotation or `x-nabla` block is allowed only for an exceptional risk acceptance
or order-only constraint.

## Generator v2

Standards-first pipeline replacing `generate-service-topology.py`:

1. discover all `apps/**/catalog-info.yaml`;
2. validate Backstage entities and entity refs;
3. read tracked Compose files;
4. bind each Compose service through `com.albandrieu.nabla.entity-ref`;
5. read minimal `x-nabla.operations` and custom relations;
6. derive Compose-native runtime facts;
7. merge static catalog/operations;
8. verify all entity refs resolve;
9. generate Backstage entity/relationship projections and CycloneDX;
10. optionally generate a derived cold-start cache for FastAPI/Site builds;
11. calculate one revision across all declared catalog inputs;
12. fail `--check` if generated output is stale.

Do not generate a replacement static exposure inventory.

### Mandatory quality gates

Fail if:

- a managed Compose service has no entity-ref or explicit ignore;
- a catalog entity expected to run has no runtime binding;
- two services claim the same runtime identity unexpectedly;
- entity refs are unresolved;
- `metadata.name` is not stable lowercase kebab-case;
- duplicate display names are used as joins;
- every legacy public/external hostname or security-protection intent is accounted for in a new desired-state source before the legacy files can be deleted;
- an observed public route has unresolved backend references or an explicitly required authorization policy that is not proven;
- an accepted risk has no reason/control;
- a critical image uses `:latest`;
- a standard Backstage relation is duplicated as custom x-nabla metadata;
- generated artifacts do not share the same revision.

## Examples: Neo4j and Cartography

```yaml
# apps/neo4j/catalog-info.yaml
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: neo4j-security
  title: Neo4j Security Graph
  description: Analytical graph store for attack-path and blast-radius analysis.
  tags: [security, graph, nist-identify, nist-detect]
  labels:
    albandrieu.com/operational-state: active
    albandrieu.com/operational-criticality: medium
  annotations:
    backstage.io/source-location: url:https://github.com/AlbanAndrieu/nabla-compose/tree/master/apps/neo4j/
    github.com/project-slug: AlbanAndrieu/nabla-compose
spec:
  type: graph-database
  owner: group:default/nabla-platform
  system: system:default/nabla-homelab
```

```yaml
# apps/neo4j/compose.yml: named long-syntax ports (web 7474, bolt 7687,
# app_protocol http/bolt) and a native healthcheck, plus:
name: neo4j
services:
  neo4j-security:
    image: neo4j:5-community
    labels:
      com.albandrieu.nabla.entity-ref: resource:default/neo4j-security

# apps/cartography/compose.yml (descriptor: see Backstage metadata conventions)
name: cartography
services:
  cartography:
    image: ghcr.io/cartography-cncf/cartography:latest
    profiles: [manual]
    labels:
      com.albandrieu.nabla.entity-ref: component:default/cartography
```

Gone from `x-nabla`: id/name/description, kind/category, criticality, security
functions, `runtime.containerService`, endpoint inventory, monitoring URL,
network membership and phase/priority boot metadata. The Backstage `dependsOn`
is the **only declared Cartography → Neo4j edge**.

## One-shot implementation scope

Prepared in stages, switched over once: "one-shot" describes the externally
visible schema switch, **not** an unreviewed big-bang edit. `docs/roadmap.md` is
the execution tracker; the P2.1 phases are:

1. **P2.1.a — preparation:** freeze/inventory v1, v1→v2 parity report, schemas
   and anti-duplication gates; no runtime behavior change.
2. **P2.1.b — representative pilot:** Neo4j, Cartography, PostgreSQL, FastAPI
   Sample and Traefik; prove desired intent survives provider outages.
3. **P2.1.c — bulk nabla-compose migration:** materialize all descriptors,
   normalize Compose, migrate exposure intent/risk acceptances, prove 100%
   semantic parity.
4. **P2.1.d — consumer preparation:** FastAPI and Site Alban understand only v2
   while legacy runtime contracts still exist for rollback.
5. **P2.1.e — coordinated cutover:** deploy the prepared repositories and run
   desired-vs-observed/network/topology smokes.
6. **P2.1.f — destructive cleanup:** delete legacy JSON
   (`services.json`, `service-topology.json`, `homelab-services.json`,
   `homelab-exposure-overrides.json`) and wave metadata only after the
   desired-intent parity gate, consumer and reboot gates pass.
7. **P2.1.g — provider-native IaC cleanup:** move temporary `x-nabla.exposure`
   records into Cloudflare/pfSense IaC or Gateway API, deleting each when its
   native source exists.

### Cross-repository merge order

GitHub cannot make three repositories transactional, so prepare all PRs first:

1. make the `nabla-compose`, `fastapi-sample` and `nabla-site-alban` PRs ready
   and locally validated;
2. merge/deploy `nabla-compose` generator/artifacts;
3. immediately merge/deploy `fastapi-sample` against the new artifacts;
4. immediately merge/deploy `nabla-site-alban`;
5. run the cross-repository catalogRevision/health/topology smoke;
6. remove any temporary deployment-only rollback artifact.

No permanent dual schema and no long-running compatibility code.

## Implemented standard projections

- `scripts/nabla_ops/catalog_exports.py` loads the Backstage descriptors,
  assigns full `entityRef` identities and computes one deterministic SHA-256
  `catalogRevision`;
- `scripts/generate-catalog-v2-artifacts.py` produces `entities.json`,
  `homelab.cdx.json` and `identity-map.json` under `catalog/generated/`;
- the CycloneDX document uses **specVersion 1.7**, carries the same revision
  and projects resolved Backstage dependencies into its dependency graph;
- `tests/test_catalog_v2_exports.py` covers deterministic revision and
  dependency preservation (first delivered in PR #224).

## Materialization debt workflow

Do not select a migration wave from directory names or a manually maintained
count. Use the repository audit as the source of truth:

```bash
python scripts/audit-service-catalog-v2-parity.py --check --debt-json
```

The output contains the total debt plus `byState`, `byCriticality` and the
exact generated service records still lacking a unique Backstage entity.
OpenCode `/catalog-wave` consumes this contract.

When the highest-priority remaining entries are `unclassified`, switch to
**classification-first** work. Do not invent business criticality, DMTP/MTPD,
RTO, RPO, MBCO or impact dimensions merely to create a descriptor. Inspect one
coherent runtime group, establish statefulness/dependencies and owner evidence,
then materialize only the entities whose classification can be justified.

## References

- Backstage: [descriptor format](https://backstage.io/docs/features/software-catalog/descriptor-format/),
  [catalog graph / GitOps](https://backstage.io/docs/features/software-catalog/creating-the-catalog-graph/),
  [well-known relations](https://backstage.io/docs/features/software-catalog/well-known-relations/),
  [well-known annotations](https://backstage.io/docs/features/software-catalog/well-known-annotations/)
- Docker Compose: [extensions](https://docs.docker.com/reference/compose-file/extension/),
  [services/labels](https://docs.docker.com/reference/compose-file/services/),
  [project name](https://docs.docker.com/reference/compose-file/version-and-name/)
- Kubernetes: [object model](https://kubernetes.io/docs/concepts/overview/working-with-objects/),
  [recommended labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/),
  [Service / EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/),
  [probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- Gateway API: [HTTP routing](https://gateway-api.sigs.k8s.io/guides/user-guides/http-routing/),
  [spec/status conditions](https://gateway-api.sigs.k8s.io/reference/api-spec/main/spec/)
- OpenTelemetry: [service](https://opentelemetry.io/docs/specs/semconv/resource/service/),
  [deployment environment](https://opentelemetry.io/docs/specs/semconv/registry/entities/deployment/)
- [OCI image annotations](https://github.com/opencontainers/image-spec/blob/main/annotations.md),
  [CycloneDX 1.7 schema](https://cyclonedx.org/docs/1.7/json/),
  [Cartography](https://github.com/cartography-cncf/cartography)
