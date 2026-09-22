# Service catalog v2 normalization and one-shot cutover

Last reviewed: 2026-09-20.

This document refines the architecture in
`docs/service-catalog-security-graph.md`. The goal is to minimize Nabla-specific
schema while keeping the operational semantics needed by the homelab.

## Executive decision

Do **not** grow `x-nabla` into a clone of Backstage.

Use the standards where they already exist:

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
consulted**.

The target is smaller than the first v2 draft:

1. operational state becomes a qualified Backstage label
   (`albandrieu.com/operational-state`) rather than a second service identity;
2. boot metadata exists only for exceptional cross-application ordering that
   cannot be derived from Backstage `dependsOn`, Compose `depends_on` and
   readiness;
3. **desired exposure/security intent remains declared in Git** until the real
   provider configuration is itself Git/IaC-managed; provider APIs are observed
   state, never the sole memory of what should exist;
4. endpoint/backend facts that are derivable from Compose/Kubernetes/providers
   are not copied into the intent model;
5. custom relation metadata is exceptional and only enriches a standard edge;
6. structured risk acceptance remains a legitimate custom policy payload.

A standard relation is authored exactly once. For example,
`spec.dependsOn: [resource:default/neo4j-security]` is the canonical Cartography
→ Neo4j dependency; it must not be repeated as an `x-nabla` `storesIn` edge
merely to rename the same relation.

This is a deliberate breaking v2 cutover. Do not maintain a long-lived v1/v2
compatibility layer.

## Why this is more normalized

Backstage already recommends Git-managed `catalog-info.yaml` descriptors as the
source of catalog entities. Its descriptors use the same entity envelope in YAML
and JSON:

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: example
spec:
  type: service
  lifecycle: production
  owner: group:default/nabla-platform
  system: system:default/nabla-homelab
```

Putting that structure inside a Compose vendor extension would make the data look
like Backstage without actually being directly consumable by Backstage.

Instead, place the real descriptor next to the real deployment:

```text
apps/cartography/
├── catalog-info.yaml
└── compose.yml
```

The repository stays GitOps-native, while the two files have distinct concerns:

- `catalog-info.yaml` = what the entity **is**;
- `compose.yml` = how it **runs**;
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
├── generated/
│   ├── entities.json                  # Backstage entity/API-shaped JSON
│   ├── operations.json                # normalized Nabla-only operational data
│   ├── relations.json                 # resolved relations + provenance/evidence
│   └── homelab.cdx.json               # CycloneDX 1.7 aggregate BOM
└── schemas/
    ├── nabla-operations.schema.json
    └── nabla-relations.schema.json

apps/<app>/
├── catalog-info.yaml
└── compose.yml
```

The generator validates and joins these sources; it must not create a second
manually-maintained service inventory.

## Backstage entity taxonomy

Stop using the current free-form `kind` field as both catalog kind and technical
type.

Use native Backstage kinds:

### Component

Deployable software/processes:

- FastAPI Sample;
- Prometheus;
- Grafana;
- Traefik;
- Cartography;
- exporters;
- workers;
- collectors;
- controllers;
- websites.

Use a small controlled `spec.type` taxonomy:

```text
service
website
worker
job
controller
collector
exporter
proxy
security-tool
ai-service
```

Backstage permits adopter-defined component types, so keep the list small rather
than reproducing every current `kind`.

### Resource

Infrastructure/stateful dependencies:

```text
database
graph-database
cache
object-storage
message-broker
search-engine
kubernetes-cluster
host
virtualization-platform
network
dns
identity-provider
```

Examples:

- PostgreSQL -> Resource / database;
- Neo4j -> Resource / graph-database;
- Redis -> Resource / cache;
- Garage / MinIO -> Resource / object-storage;
- Kafka -> Resource / message-broker;
- TrueNAS -> Resource / virtualization-platform;
- Kubernetes -> Resource / kubernetes-cluster.

### API

Create API entities only for stable interfaces that have an actual contract or a
meaningful machine API:

- OpenAPI;
- AsyncAPI;
- GraphQL;
- gRPC;
- MCP server.

Do not create an API entity merely because a web UI listens on HTTP.

### System / Domain / Group

Initial hierarchy:

```text
Domain:  nabla
System:  nabla-homelab
Owner:   group:default/nabla-platform
```

Keep current categories such as `security`, `observability`, `network`,
`data`, `ai` as tags initially. Do not create dozens of Systems simply to
replace a category string.

## Backstage metadata conventions

Use standard fields wherever possible.

Example:

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

- `metadata.name` is the canonical stable ID.
- `metadata.title` is display text.
- `metadata.description` replaces duplicate UI descriptions.
- `metadata.tags` holds category and NIST CSF classifications.
- `metadata.labels` holds short queryable Nabla values.
- `metadata.annotations` holds source/external-system references.
- `spec.lifecycle` is the software/catalog lifecycle, not boot order.

Suggested catalog lifecycle values:

```text
experimental
production
deprecated
```

The current `active | planned | disabled` field is **not** the same concept and
must therefore stay as Nabla operational intent.

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
  This is applicable to data-bearing services; it may be omitted for a
  stateless/rebuildable service.
- **MBCO / OMCA** — minimum business continuity objective / objectif minimal de
  continuité d'activité. Keep it as a qualitative minimum acceptable service
  level; do not force it into a numeric score.

ISO/TS 22317 also requires the BIA to consider the impact of disruption over
time, legal/regulatory/contractual obligations, resources and dependencies.
NIST SP 800-34 uses MTD/RTO/RPO and recovery priorities, while NIST IR 8286D
extends BIA beyond availability toward enterprise-value impacts including
financial, reputational, operational and regulatory consequences.

References:

- ISO/TS 22317:2021 — https://www.iso.org/standard/79000.html
- ISO 22300:2025 vocabulary — https://www.iso.org/obp/ui/en/#iso:std:iso:22300:ed-4:v1:fr
- NIST SP 800-34 Rev. 1 — https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final
- NIST IR 8286D-upd1 (2025) — https://csrc.nist.gov/pubs/ir/8286/d/upd1/final

### Backstage representation

Use a queryable calculated label plus scalar annotations. Backstage labels are
appropriate for catalog classification/filtering; annotations carry the
supporting non-identifying BIA metadata.

Example:

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

Durations use the bounded ISO-8601 subset used by the repository policy
(`PT15M`, `PT4H`, `P1D`, `P3D`, ...).

### Calculation policy

`catalog/business-criticality-policy.yaml` is the single source for the Nabla
tier thresholds. The thresholds are deliberately identified as **Nabla
policy**, not ISO/NIST thresholds.

Current method: `max-of-drivers`.

1. Convert MTPD, RTO and applicable RPO into a
   `low | medium | high | critical` tier using the policy thresholds.
2. Convert each assessed impact dimension into the same tier vocabulary.
3. Business criticality is the most severe driver.
4. Report the driver list and the recovery margin `MTPD - RTO`.
5. Fail the catalog gate if `RTO >= MTPD`, duration syntax is invalid, an
   impact value is unknown, or the declared business-criticality label differs
   from the calculated value.

Current impact dimensions are:

```text
operational
customer
financial
legal-regulatory
reputation
confidentiality
integrity
privacy
```

These dimensions are not an attempt to invent a universal scoring standard.
They are a compact catalog projection of BIA concerns from ISO/NIST and remain
reviewable policy.

### Assessment maturity

Pilot values in PR #215 use:

```text
albandrieu.com/bia-status: provisional
```

A technically passing gate does **not** mean the BIA has been approved.
`validated` is reserved for an assessment reviewed by the responsible owner.
The bulk migration must not silently turn provisional values into validated
values.

### Coverage gate

The catalog gate now prevents silent BIA omissions during P2.1.c:

- every materialized Backstage `Component` / `Resource` must declare
  `albandrieu.com/operational-state` so BIA scope cannot be bypassed by a
  missing label;
- every `active` Component/Resource must also declare
  `albandrieu.com/bia-scope: direct | inherited`;
- `direct` means the entity owns a BIA and therefore requires a
  business-criticality label, MTPD/DMTP, RTO, MBCO/OMCA, assessment status,
  review date and at least one assessed impact dimension;
- data-bearing `direct` types listed in
  `catalog/business-criticality-policy.yaml` additionally require RPO;
- `inherited` means the technical subcomponent does **not** duplicate an own
  business-criticality/BIA. Its effective criticality is derived from required
  dependents through the Backstage graph;
- `planned` / `disabled` entities may remain incomplete until activation,
  but their missing BIA is explicit lifecycle debt rather than an inferred
  low-criticality assessment.

### Dependency amplification

Do not overwrite an infrastructure Resource's own BIA because a critical
service depends on it. Keep two separate concepts:

- **own business criticality** — calculated from that entity's BIA;
- **effective dependency criticality** — generated as a separate read-model
  signal by traversing required Backstage `spec.dependsOn` edges transitively.

The implementation reports `ownBusinessCriticality`,
`effectiveDependencyCriticality`, whether the entity was elevated, and the
upstream business entities in `inheritedFrom`. An `inherited` entity is
expected to have no own BIA and receives its effective value through this graph.
Duplicate entity refs, malformed dependencies and unresolved dependency refs
fail closed.

This preserves provenance, avoids recursive score inflation and lets FastAPI /
Site consumers explain why an infrastructure dependency is effectively critical
without mutating its own BIA.

## Kubernetes model: do not flatten catalog, network and status

Kubernetes provides the strongest design lesson for this migration: it does not
keep one manually merged `services + exposure overrides` inventory.

It splits concerns into resources and reconciles them:

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

Important consequences:

1. **desired state and observed state stay separate**;
2. desired public exposure must survive a Cloudflare/Docker/TrueNAS outage;
3. an endpoint is not copied into catalog identity metadata merely because it is
   useful to a UI;
4. when a provider is not yet Git/IaC-managed, Nabla must temporarily retain the
   intended route/security policy in Git;
5. provider APIs report whether that intent is actually realized;
6. runtime backend addresses are observations, like EndpointSlices, not catalog
   fields;
7. consumers build a view by joining resources through stable references.

This mirrors Kubernetes `spec` versus `status`: losing the controller does not
erase the desired `spec`.
### Kubernetes-style metadata conventions

Where Kubernetes resources are generated later, use the recommended labels:

```text
app.kubernetes.io/name
app.kubernetes.io/instance
app.kubernetes.io/version
app.kubernetes.io/component
app.kubernetes.io/part-of
app.kubernetes.io/managed-by
```

Map `app.kubernetes.io/name` to Backstage `metadata.name`; do not create a
second Kubernetes-only service ID.

For Docker/Compose runtime correlation, keep only the equivalent qualified label:

```text
com.albandrieu.nabla.entity-ref=component:default/example
```

### Kubernetes-style status conditions

FastAPI should normalize runtime/network observations into Kubernetes-like
conditions instead of storing another declared catalog.

Use the condition shape and semantics:

```json
{
  "type": "Ready",
  "status": "True",
  "reason": "HealthcheckPassed",
  "message": "Compose container healthcheck is healthy",
  "lastTransitionTime": "..."
}
```

Useful condition types for the homelab can reuse established terminology rather
than inventing one status enum:

- `Ready` — service can accept intended traffic;
- `Healthy` / provider-specific health evidence where required;
- `Accepted`, `Programmed`, `ResolvedRefs` for route/Gateway-style
  reconciliation;
- `Available` for workload/runtime availability;
- `Degraded` only as a derived presentation state, not as declared intent.

Keep `Unknown` when evidence is stale/unavailable. This matches the existing
FastAPI principle that missing Cloudflare evidence must not fabricate a failure.

### Gateway API as the exposure model

The conceptual exposure graph is:

```text
Gateway/listener
       │
       ▼
HTTPRoute/TCPRoute
       │ backendRef
       ▼
Service
       │
       ▼
EndpointSlice / runtime backends
```

For the current non-Kubernetes TrueNAS stack, **do not create fake Kubernetes
HTTPRoute objects merely to look standard**. Instead, implement provider adapters
that project the existing source into the same concepts:

- Traefik labels -> Route + backend;
- Cloudflare Tunnel Public Hostname -> Route + origin;
- Cloudflare Access Application/Policy -> route authorization policy;
- pfSense HAProxy frontend/backend -> Gateway/listener + Route + backend;
- Compose published port -> Service-like internal surface;
- TrueNAS/Docker container -> observed backend.

When the workload is actually deployed on Kubernetes, consume the native
Service/EndpointSlice/Gateway API objects directly.

### Desired exposure intent while providers are not fully IaC-managed

The previous draft went too far by proposing that all exposure be inferred from
provider state. That would lose security intent during an outage or API
authorization failure.

Until Cloudflare/pfSense exposure configuration is managed declaratively in Git,
retain a **small route-intent spec** beside the service.

Use Gateway API concepts and references, but do not fabricate Kubernetes objects
for Docker workloads:

```yaml
x-nabla:
  exposure:
    - name: public
      hostnames:
        - sample.albandrieu.com
      protocol: HTTPS
      visibility: public
      gatewayRef: resource:default/cloudflare-tunnel
      backendPort: web
      access:
        required: true
```

The Compose port is named once:

```yaml
ports:
  - name: web
    target: 8080
    published: "8091"
    host_ip: 172.17.0.24
    protocol: tcp
    app_protocol: http
```

The exposure spec therefore does **not** repeat IP address, numeric backend port,
container name or runtime health.

Semantics:

- `hostnames` = desired names that should exist even when the provider is down;
- `protocol` = desired listener/application transport;
- `visibility` = intended security boundary (`public | lan | cluster | host`);
- `gatewayRef` = Backstage entity ref for the desired edge/gateway provider;
- `backendPort` = named Compose/Kubernetes service port, not a duplicate number;
- `access.required` = desired protection intent, independent of whether the
  Cloudflare Access API can currently prove it.

FastAPI then exposes a reconciled view:

```text
spec:
  desired route intent from Git

status:
  Accepted
  ResolvedRefs
  Programmed
  AccessProtected
  Ready
```

If Cloudflare is unreachable:

```text
desired public hostname = still present
access.required = still true
Programmed = Unknown
AccessProtected = Unknown
```

Never convert the provider outage into `external=false`.

### Future migration of route intent

The route-intent extension is explicitly transitional:

- Traefik desired routing should remain native Traefik configuration/labels in
  Git and can be projected into the normalized route view.
- Kubernetes workloads should move to native Gateway API resources.
- Cloudflare Tunnel/Access desired state should move to an OpenTofu/Terraform
  Cloudflare provider when that management path is introduced.
- pfSense HAProxy desired state should move to its reviewed API/IaC source when
  safe automation exists.

Once a provider has a real declarative Git source, delete the duplicate
`x-nabla.exposure` record for that route. The provider-native configuration
becomes `spec`; FastAPI/provider observation remains `status`.

## Separate Backstage lifecycle from boot semantics

Backstage `spec.lifecycle` remains exclusively the catalog/software lifecycle:

```text
experimental | production | deprecated
```

For reboot/startup, combine the useful parts of **systemd** and **Kubernetes**
without copying either API.

Systemd provides the key semantic distinction:

- requirement dependencies (`Requires` / `Wants`);
- ordering dependencies (`After` / `Before`).

Kubernetes adds the more important operational lesson: avoid a global boot phase
model when controllers can reconcile independently and gate availability on
readiness.

### Target boot algorithm

The TrueNAS resume planner should therefore:

1. discover active entities from Backstage's qualified operational-state label;
2. derive same-project dependencies from Compose `depends_on`;
3. derive required cross-entity dependencies from Backstage `spec.dependsOn`;
4. wait for the dependency's declared readiness evidence before unblocking a
   dependent;
5. start/reconcile independent branches concurrently;
6. use systemd-style `after` / `before` only for exceptional order-only
   constraints;
7. use `wants` only for a weak/optional boot dependency;
8. keep retry/reconciliation idempotent rather than requiring one global phase to
   finish perfectly.

Delete the current global:

```yaml
lifecycle:
  phase: primary-data
  priority: 20
  blocksLaterWaves: true
```

There is **no v2 replacement for phase or priority**.

Required Backstage dependencies block only their dependents. A failed Vaultwarden
recovery, for example, does not block an unrelated PostgreSQL branch merely
because both formerly belonged to ordered waves.

### Exceptional boot metadata

Most services have no x-nabla boot block.

When a true order-only constraint exists:

```yaml
x-nabla:
  boot:
    after:
      - resource:default/special-host-service
    before:
      - component:default/consumer
```

For a weak/optional boot requirement:

```yaml
x-nabla:
  boot:
    wants:
      - component:default/optional-observer
```

Rules:

- `after` / `before` express ordering only;
- `wants` expresses a weak dependency;
- required dependencies remain Backstage `spec.dependsOn`;
- intra-project dependencies remain native Compose `depends_on`;
- there is no `target`, `phase`, `priority`,
  `blocksDependents` or duplicate `requires` field.

This yields a DAG/reconciliation planner instead of a custom wave scheduler.

## Minimal x-nabla v2

The preferred state is **no `x-nabla` block at all** for a normal service.

Cartography:

```yaml
# apps/cartography/catalog-info.yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: cartography
  labels:
    albandrieu.com/operational-state: active
spec:
  type: job
  lifecycle: production
  owner: group:default/nabla-platform
  system: system:default/nabla-homelab
  dependsOn:
    - resource:default/neo4j-security
```

```yaml
# apps/cartography/compose.yml
name: cartography

services:
  cartography:
    image: ghcr.io/cartography-cncf/cartography:latest
    profiles:
      - manual
    labels:
      com.albandrieu.nabla.entity-ref: component:default/cartography
```

No x-nabla metadata is required here.

### Legitimate remaining x-nabla

Use the extension only when a source cannot yet be represented by a provider-
native Git/IaC object or derived elsewhere:

```yaml
x-nabla:
  exposure:
    - name: public
      hostnames:
        - example.albandrieu.com
      protocol: HTTPS
      visibility: public
      gatewayRef: resource:default/cloudflare-tunnel
      backendPort: web
      access:
        required: true

  boot:
    after:
      - resource:default/special-host-service

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

### 1. Add top-level project name

Every repository-managed Compose application should declare:

```yaml
name: cartography
```

Compose defines this as the project name. This gives the catalog, runtime and
TrueNAS reconciliation a stable application identity without another
`runtime.appId` copy.

Only retain a Nabla `runtime.appId` override where the actual TrueNAS App ID
cannot be made equal to the project name.

### 2. Remove unnecessary container_name

Prefer:

```yaml
services:
  neo4j-security:
    image: neo4j:5-community
```

over:

```yaml
container_name: neo4j-security
```

Compose already has canonical project/service identity and creates
`com.docker.compose.project` / `com.docker.compose.service` labels.

Keep `container_name` only when a verified external integration requires the
literal Docker container name.

### 3. Add one runtime correlation label

Use Docker's recommended reverse-DNS label convention:

```yaml
labels:
  com.albandrieu.nabla.entity-ref: resource:default/neo4j-security
```

This creates a join key available both in Git and on the live container.

Do not overload container labels with the complete catalog.

### 4. Derive instead of duplicate

The generator should infer:

- Compose project from top-level `name`;
- Compose service from the service key;
- image reference from `image`;
- networks from `networks`;
- published ports, names and application protocols from long-syntax `ports` (`name`, `target`, `published`, `host_ip`, `protocol`, `app_protocol`);
- manual/job intent from `profiles`;
- local dependency edges from `depends_on`;
- container health capability from `healthcheck`;
- restart semantics from `restart`;
- configs and secrets from native Compose declarations.

Only require metadata when it cannot be derived safely.

### 5. Health checks

Prefer native Compose `healthcheck` for container health and use Kubernetes
probe semantics in the observer:

- **startup**: has the application completed initialization?
- **readiness**: should traffic be sent to it?
- **liveness**: should the runtime restart it?

Do not persist those probes in a second catalog when they can be derived.

Cross-plane checks (LAN, public edge, Access-authenticated route, DNS,
WebSocket, functional dependency) belong to FastAPI observer configuration/code
or provider-derived routes and produce status conditions. They are observations,
not service identity metadata.

### 6. Standard configs/secrets

Where practical:

- use Compose `configs` for non-secret configuration files;
- use Compose `secrets` when the target application supports file-based secrets;
- retain Vaultwarden-rendered `env_file` only where applications require
  environment variables.

Do not force file-based secrets onto software that only supports environment
variables merely for schema purity.

### 7. OCI metadata

For images built by Nabla, set OCI image annotations at build time:

```text
org.opencontainers.image.source
org.opencontainers.image.revision
org.opencontainers.image.version
org.opencontainers.image.documentation
org.opencontainers.image.licenses
```

Do not add misleading OCI vendor/source labels to third-party images that Nabla
does not build.

### 8. Version/digest security

Prefer a pinned version and, for critical services, an immutable image digest.

This improves:

- CycloneDX identity;
- Trivy correlation;
- rollback reproducibility;
- runtime-to-SBOM joins.

Treat `:latest` as explicit supply-chain debt.

## OpenTelemetry identity alignment

For telemetry-capable applications, use:

```text
service.name                 = Backstage metadata.name
service.namespace            = nabla-homelab
deployment.environment.name  = production | staging | development | test
service.version              = deployed application/image version
service.criticality          = critical | high | medium | low
```

The same service name must remain stable across production/staging deployments;
the deployment environment is a separate attribute.

Do not invent environment-specific service IDs such as
`sample-production` unless they are genuinely different logical services.

## CycloneDX projection

Map every Backstage service/component to a deterministic CycloneDX reference.

Recommended reference:

```text
nabla:component:default/cartography
nabla:resource:default/neo4j-security
```

CycloneDX services natively support:

- endpoints;
- authenticated boolean;
- trust-boundary boolean;
- trust zone;
- service hierarchy;
- data flows/classification;
- dependency references.

Map the operational endpoint model into those fields where semantics are
lossless. Preserve richer ingress/access/risk-acceptance details as namespaced
CycloneDX properties.

Package/image SBOMs generated by Trivy remain separate artifacts linked through
image digest / pURL and the Backstage entity reference.

## Relation normalization: one edge, one authority

Backstage well-known relations are the canonical declared graph:

```text
ownedBy
partOf
dependsOn
providesApi
consumesApi
```

Use them natively in `catalog-info.yaml`.

### No duplicated semantic aliases

Do **not** author both:

```yaml
spec:
  dependsOn:
    - resource:default/neo4j-security
```

and:

```yaml
x-nabla:
  relations:
    - targetRef: resource:default/neo4j-security
      semantic: storesIn
```

for the same logical edge.

For the Cartography → Neo4j case, `dependsOn` is sufficient: Neo4j is already
typed as a `Resource` / `graph-database`, so consumers can understand the
dependency without a second edge.

### When enrichment is justified

Keep relation metadata only when all three are true:

1. Backstage cannot express the distinction;
2. runtime/configuration cannot derive it reliably;
3. the distinction is used by an operational/security query.

Examples that may qualify are an explicit authentication path, proxy route or
security observation path. Even then, enrich the existing edge rather than
creating a second independently-owned topology relation whenever possible.

### Derivation policy

Prefer:

- Compose `depends_on` for same-project runtime dependency;
- Backstage `spec.dependsOn` for cross-entity functional dependency;
- Backstage `providesApis` / `consumesApis` for API relationships;
- Backstage System/Domain fields for `partOf`;
- runtime/provider observations for hosting, routing and exposure;
- Neo4j relationship enrichment for observed attack-path semantics.

This deliberately removes `storesIn`, `hostedBy`, `routesTo`,
`observedBy`, `authenticatesVia`, `exposedBy` and `automates` from the
mandatory authoring vocabulary. They may still exist as generated/observed graph
semantics when evidence proves them.

## Cartography ontology alignment

Do not try to force Nabla's whole schema to match provider-specific Cartography
nodes.

Use semantic graph labels during import:

```text
Backstage Component -> :NablaEntity:Application
Backstage Resource/database -> :NablaEntity:Database:DataStore
Backstage Resource/host -> :NablaEntity:ComputeInstance
API -> :NablaEntity:Service
```

The Cartography project is itself moving toward lightweight ontology and
relationship normalization. Keep the mapping layer explicit so the Nabla model
can follow those canonical semantic labels without making Cartography's internal
schema the Git authoring format.

## Delete homelab-services.json and homelab-exposure-overrides.json

The Kubernetes comparison changes the previous recommendation: **do not replace
these files with another canonical flat endpoint document**.

However, do not discard the desired exposure/security intent they currently
contain. First migrate that intent into Backstage/Compose/provider-native Git
sources or the temporary minimal `x-nabla.exposure` spec. Only then delete the
legacy files in the coordinated cutover.

Both files exist because identity, endpoint discovery, desired exposure,
observed routing and presentation were collapsed into one UI-oriented schema and
then patched with precedence overrides.

Delete the flat model, not the intent.

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

### Provider authority

For the current homelab:

- **internal Docker endpoint desired state:** Compose;
- **internal HTTP ingress desired state:** Traefik labels/config;
- **public Cloudflare route desired state:** temporary Git route intent until
  Cloudflare configuration is IaC-managed;
- **public Cloudflare route observed state:** Tunnel Public Hostname API;
- **public authorization desired state:** route intent `access.required` until
  Cloudflare Access policy is IaC-managed;
- **public authorization observed state:** Access Application + attached policies
  + Service Token/live-edge evidence;
- **direct WAN desired state:** temporary route intent until pfSense HAProxy
  configuration has a reviewed declarative owner;
- **direct WAN observed state:** pfSense HAProxy frontend/backend;
- **runtime backend:** TrueNAS/Docker observation;
- **Kubernetes workload:** native Service + EndpointSlice + Gateway API, whose
  spec/status separation already solves this natively.

FastAPI already observes several of these providers. The migration should make
those adapters the source of the network view instead of copying their result
into static JSON.

### Desired exposure versus observed exposure

Kubernetes separates `spec` from `status`; Nabla should too.

Whenever possible, move desired exposure into the actual controller's
declarative source:

- Traefik labels/config in Git;
- Kubernetes Gateway API manifests in Git;
- Cloudflare configuration-as-code if/when the dashboard-managed configuration
  is migrated to OpenTofu/Terraform;
- pfSense/HAProxy configuration source when safely automatable.

Until a provider is Git-managed, the minimal Git route-intent spec is the
**desired state**, and FastAPI/provider APIs supply the **observed status**.

A direct exposure that needs an explicit policy exception additionally keeps a
structured `riskAcceptance`.

Do not add a generic `external: true/false` Backstage field merely to recreate
the old override file; keep exposure intent as a route/policy object with a
hostname/gateway/access context.

## FastAPI Sample one-shot changes

FastAPI becomes a **read-model / reconciler**, analogous to a Kubernetes
controller plus API view. It does not own a second declared inventory.

Delete:

```text
homelab-services.json
homelab-exposure-overrides.json
DeclaredService
DeploymentEnvironment
RuntimeBinding
ServiceLifecycle
HomelabTopologyNode
```

Consume directly:

```text
Backstage entities/relations
temporary Git route/security intent for providers not yet IaC-managed
Compose-derived desired runtime facts
TrueNAS/Docker observations
Kubernetes Service/EndpointSlice/Gateway objects when applicable
Traefik route configuration
Cloudflare Tunnel + Access observations
pfSense HAProxy observations
security findings/SBOM enrichments
```

### API shape

Do not create one giant replacement DTO.

Prefer resource-oriented endpoints/views:

```text
/api/catalog/entities
/api/catalog/relations
/api/runtime/observations
/api/network/routes
/api/network/backends
/api/security/findings-summary
```

The existing health-board aggregate can remain a presentation-optimized endpoint,
but it is generated from those views and is not the source of truth.

### Status

Normalize evidence with Kubernetes-style conditions:

```text
type
status = True | False | Unknown
reason
message
lastTransitionTime
observedGeneration/revision where applicable
```

Gateway-like route observations should expose `Accepted`, `Programmed` and
`ResolvedRefs` semantics where meaningful.

### Join key

Use only the full Backstage entity reference:

```text
component:default/prometheus
resource:default/postgresql
```

Never join runtime evidence on display names.

### Cold-start/offline behavior

A build may embed an **optional generated last-known-good cache**, but that file
is an implementation cache, not a third canonical catalog and is never hand
edited.

If present, name it generically (for example
`nabla/api/data/catalog-snapshot.json`) and generate it solely from the standard
sources. Runtime/provider observations remain separately fresh/stale/unknown.

## Site Alban one-shot changes

Replace the current service DTO with the same entity-ref model.

React Flow node ID:

```text
component:default/prometheus
```

not:

```text
Prometheus
prometheus
```

Consume:

- Backstage entity metadata for title/description/type/owner/system/tags;
- desired exposure/security intent from provider-native Git/IaC or temporary route-intent declarations;
- Backstage relations for declared graph edges/evidence;
- FastAPI runtime observations separately;
- security enrichment separately.

Remove presentation-critical operational fields from the catalog UI fallback.

The Site may keep its own icon/layout mapping, because icon choice and graph
position are presentation concerns rather than infrastructure truth.

## Static infrastructure normalization

Replace `catalog/service-topology.static.json` with standards-first sources.

Use `catalog/catalog-info.yaml` for Domain/System/Group and static Resources
such as TrueNAS, pfSense, Kubernetes and Talos.

Do **not** recreate a static endpoint inventory. Their endpoints/routes are
derived from provider configuration and observations just like Kubernetes
Service/Gateway/status resources.

A small qualified annotation or x-nabla block is permitted only for an
exceptional risk acceptance or order-only constraint that cannot be represented
elsewhere.

This removes the current dependency where static topology nodes point their
`sourcePath` at `catalog/homelab-services.json`.

## Generator v2

Replace `generate-service-topology.py` responsibilities with a standards-first
pipeline:

1. discover all `apps/**/catalog-info.yaml`;
2. validate Backstage entities and entity refs;
3. read tracked Compose files;
4. bind each Compose service through
   `com.albandrieu.nabla.entity-ref`;
5. read minimal `x-nabla.operations` and custom relations;
6. derive Compose-native runtime facts;
7. merge static catalog/operations;
8. verify all entity refs resolve;
9. generate Backstage entity/relationship projections and CycloneDX;
10. optionally generate a derived cold-start cache for FastAPI/Site builds;
11. calculate one revision across all declared catalog inputs;
12. fail `--check` if generated output is stale.

Do not generate a replacement static exposure inventory. Network/runtime views are
built from controller/provider sources.

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

## Example: Neo4j

### apps/neo4j/catalog-info.yaml

```yaml
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: neo4j-security
  title: Neo4j Security Graph
  description: Analytical graph store for attack-path and blast-radius analysis.
  tags:
    - security
    - graph
    - nist-identify
    - nist-detect
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

### apps/neo4j/compose.yml

```yaml
name: neo4j

services:
  neo4j-security:
    image: neo4j:5-community
    labels:
      com.albandrieu.nabla.entity-ref: resource:default/neo4j-security

    ports:
      - name: web
        target: 7474
        published: "31086"
        host_ip: 172.17.0.24
        protocol: tcp
        app_protocol: http
      - name: bolt
        target: 7687
        published: "31087"
        host_ip: 172.17.0.24
        protocol: tcp
        app_protocol: bolt

    healthcheck:
      test:
        - CMD-SHELL
        - wget --no-verbose --tries=1 --spider http://127.0.0.1:7474/ || exit 1

```

Notice what disappeared from x-nabla:

- id/name/description;
- kind/category;
- criticality;
- security functions;
- runtime containerService;
- endpoint inventory now derived from Compose/provider routing;
- monitoring URL already represented by Compose healthcheck or observer;
- network membership;
- phase/priority boot metadata.

## Example: Cartography

### apps/cartography/catalog-info.yaml

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
    albandrieu.com/status: active
    albandrieu.com/operational-criticality: low
spec:
  type: job
  lifecycle: production
  owner: group:default/nabla-platform
  system: system:default/nabla-homelab
  dependsOn:
    - resource:default/neo4j-security
```

### apps/cartography/compose.yml

```yaml
name: cartography

services:
  cartography:
    image: ghcr.io/cartography-cncf/cartography:latest
    profiles:
      - manual
    labels:
      com.albandrieu.nabla.entity-ref: component:default/cartography

```

The standard Backstage `dependsOn` is the **only declared Cartography → Neo4j edge**. No x-nabla relation duplicates it.

## One-shot implementation scope

This should be implemented as one coordinated schema cutover, not as a long
compatibility migration.

The execution is deliberately **prepared in stages but switched over once**.
`docs/roadmap.md` is the canonical execution tracker and defines:

1. **P2.1.a — preparation:** freeze/inventory v1, generate the v1→v2 parity
   report, define schemas and anti-duplication gates; no runtime behavior change.
2. **P2.1.b — representative pilot:** migrate Neo4j, Cartography, PostgreSQL,
   FastAPI Sample and Traefik; prove desired intent survives provider outages.
3. **P2.1.c — bulk nabla-compose migration:** materialize all Backstage
   descriptors, normalize Compose, migrate exposure intent/risk acceptances and
   prove 100% semantic parity.
4. **P2.1.d — consumer preparation:** make FastAPI and Site Alban understand only
   the v2 model while legacy runtime contracts still exist for rollback.
5. **P2.1.e — coordinated cutover:** deploy the three prepared repositories and
   run desired-vs-observed/network/topology smokes.
6. **P2.1.f — destructive cleanup:** delete legacy JSON and wave metadata only
   after parity, consumer and reboot gates pass.
7. **P2.1.g — provider-native IaC cleanup:** later move temporary
   `x-nabla.exposure` records into Cloudflare/pfSense IaC or Kubernetes Gateway
   API and delete each temporary record when its native desired-state source
   exists.

Thus "one-shot" describes the externally visible schema switch, **not** an
unreviewed big-bang edit.

### nabla-compose

- add Backstage descriptors;
- bulk-convert all current x-nabla blocks;
- add Compose project names;
- add entity-ref runtime labels;
- remove redundant `container_name` values where safe;
- derive networks/ports/profiles/health/dependencies from Compose;
- replace static topology source;
- replace generator and schemas;
- generate Backstage projections and CycloneDX;
- derive provider/runtime network views instead of generating another static
  service/exposure inventory;
- migrate every legacy desired hostname/visibility/access requirement into
  provider-native Git/IaC or temporary `x-nabla.exposure`;
- remove old `services.json`, `service-topology.json`,
  `homelab-services.json` and `homelab-exposure-overrides.json` only after
  that desired-intent parity gate and the coordinated consumer PRs are ready.

### fastapi-sample

- replace old catalog/topology Pydantic models;
- delete both packaged legacy service/exposure JSON files;
- consume Backstage entities plus provider/runtime resources directly;
- normalize observations to Kubernetes-style conditions;
- remove name-based and legacy-field joins;
- expose entity-ref-based resource-oriented read APIs;
- keep any cold-start snapshot explicitly derived/cache-only.

### nabla-site-alban

- replace old catalog DTO;
- use entity refs as graph IDs;
- consume Backstage relations plus FastAPI runtime/network resource views;
- keep presentation-only icons/layout local;
- remove the old bundled service/exposure shape.

## Merge/cutover order

GitHub cannot make three repositories transactional, so prepare all PRs before
cutover.

Recommended controlled order:

1. make all three PRs ready and locally validated;
2. merge/deploy `nabla-compose` generator/artifacts;
3. immediately merge/deploy `fastapi-sample` against the new artifacts;
4. immediately merge/deploy `nabla-site-alban`;
5. run cross-repository catalogRevision/health/topology smoke;
6. remove any temporary deployment-only rollback artifact if one was required.

There should be no permanent dual schema and no long-running compatibility code.

## References

- Backstage descriptor format:
  https://backstage.io/docs/features/software-catalog/descriptor-format/
- Backstage catalog graph / GitOps:
  https://backstage.io/docs/features/software-catalog/creating-the-catalog-graph/
- Backstage well-known relations:
  https://backstage.io/docs/features/software-catalog/well-known-relations/
- Backstage well-known annotations:
  https://backstage.io/docs/features/software-catalog/well-known-annotations/
- Docker Compose extensions:
  https://docs.docker.com/reference/compose-file/extension/
- Docker Compose service labels:
  https://docs.docker.com/reference/compose-file/services/
- Docker Compose project name:
  https://docs.docker.com/reference/compose-file/version-and-name/
- Kubernetes object model:
  https://kubernetes.io/docs/concepts/overview/working-with-objects/
- Kubernetes recommended labels:
  https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/
- Kubernetes Service / EndpointSlice:
  https://kubernetes.io/docs/concepts/services-networking/
- Kubernetes probes:
  https://kubernetes.io/docs/concepts/workloads/pods/probes/
- Gateway API HTTP routing:
  https://gateway-api.sigs.k8s.io/guides/user-guides/http-routing/
- Gateway API specification/status conditions:
  https://gateway-api.sigs.k8s.io/reference/api-spec/main/spec/
- OpenTelemetry service semantic conventions:
  https://opentelemetry.io/docs/specs/semconv/resource/service/
- OpenTelemetry deployment environment:
  https://opentelemetry.io/docs/specs/semconv/registry/entities/deployment/
- OCI image annotations:
  https://github.com/opencontainers/image-spec/blob/main/annotations.md
- CycloneDX 1.7 service schema:
  https://cyclonedx.org/docs/1.7/json/
- Cartography:
  https://github.com/cartography-cncf/cartography
