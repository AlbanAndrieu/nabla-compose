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
representation, principally:

1. declared operational intent (`active | planned | disabled`);
2. TrueNAS/reboot startup ordering;
3. endpoint exposure policy that is more detailed than Compose or Backstage;
4. custom relation semantics/provenance such as `storesIn`, `routesTo`,
   `observedBy`, `authenticatesVia`, `exposedBy` and `automates`;
5. structured risk/security exceptions.

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

## Target repository layout

```text
catalog/
├── catalog-info.yaml                  # Domain/System/Group + static infra
├── service-icons.json                 # presentation only; not security truth
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
    albandrieu.com/status: active
    albandrieu.com/criticality: low
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

## Normalize the current x-nabla lifecycle collision

Current:

```yaml
x-nabla:
  lifecycle:
    phase: primary-data
    priority: 20
    blocksLaterWaves: true
```

Target:

```yaml
x-nabla:
  operations:
    intent: active
    startup:
      phase: primary-data
      priority: 20
      blocksLaterWaves: true
```

This reserves the term `lifecycle` for Backstage's catalog lifecycle and makes
the operational meaning explicit.

## Minimal x-nabla v2

A normal Compose service should need little metadata.

```yaml
name: cartography

services:
  cartography:
    image: ghcr.io/cartography-cncf/cartography:latest

    labels:
      com.albandrieu.nabla.entity-ref: component:default/cartography

    profiles:
      - manual

    x-nabla:
      operations:
        intent: active
        startup:
          phase: platform-services
          priority: 80
          blocksLaterWaves: false

      relations:
        - targetRef: resource:default/neo4j-security
          semantic: storesIn
          strength: required
          evidence:
            - apps/cartography/compose.yml:NEO4J_URL
```

The service name, Compose project, image, networks and manual profile are already
available from Compose and must not be copied into `x-nabla`.

### x-nabla operations schema

Target fields:

```yaml
x-nabla:
  operations:
    intent: active | planned | disabled

    startup:
      phase: bootstrap-runtime | foundation | network-edge |
             primary-data | secondary-data |
             platform-services | applications
      priority: 0..1000
      blocksLaterWaves: true | false

    runtime:
      appId: optional-exception-only

    endpoints:
      - name: lan
        url: http://172.17.0.24:31086
        role: ui | api | health | metrics | admin
        scope: host | lan | cluster | public
        trustZone: homelab-lan
        trustBoundary: false
        authenticated: true | false
        enabled: true

        ingress:
          provider: cloudflare | pfsense-haproxy | traefik | direct
          mode: tunnel | proxy | direct
          access: required | optional | none

        probe:
          protocol: http | https | tcp | dns | websocket
          path: /ready
          expectedStatus:
            - 200

    riskAcceptances:
      - id: truenas-public-admin
        status: accepted
        reason: ...
        scope: public-endpoint
        control: tls-and-api-auth
        reviewAfter: null

  relations:
    - targetRef: resource:default/postgresql
      semantic: storesIn
      strength: required
      evidence:
        - apps/example/compose.yml:DATABASE_URL
```

All relation targets use full Backstage entity references rather than bare
Nabla IDs.

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
- published ports from `ports`;
- manual/job intent from `profiles`;
- local dependency edges from `depends_on`;
- container health capability from `healthcheck`;
- restart semantics from `restart`;
- configs and secrets from native Compose declarations.

Only require metadata when it cannot be derived safely.

### 5. Health checks

Prefer native Compose `healthcheck` for process/container readiness.

Use `x-nabla.operations.endpoints[].probe` only for health that must be observed
from a different network plane, for example:

- LAN endpoint;
- public Cloudflare path;
- authenticated API;
- DNS;
- WebSocket;
- cross-service functional health.

Do not duplicate the same health URL in both fields unless the probes are
intentionally from different trust zones.

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

## Custom relation normalization

Backstage has well-known relations such as:

```text
ownedBy
partOf
dependsOn
providesApi
consumesApi
```

Use those natively in `catalog-info.yaml`.

Retain only richer Nabla semantic refinements where they add security/operational
meaning:

```text
storesIn
hostedBy
routesTo
observedBy
authenticatesVia
exposedBy
automates
```

Normalize their targets to Backstage entity references.

Generator rule:

- `storesIn` implies a Backstage `dependsOn` Resource;
- `authenticatesVia` normally implies `dependsOn`;
- `hostedBy` should usually be derived from runtime placement;
- `providesApi`, `consumesApi` and `partOf` should no longer be duplicated in
  x-nabla because Backstage already owns them.

Keep evidence/provenance on custom relations for Neo4j/Cartography.

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

## One-shot replacement of homelab-services.json

Do not preserve the current flat schema.

Current fields:

```text
name
description
internalHost
internalPort
internalSecure
internalPath
tunnelUrl
tunnelSecure
external
endpointEnabled
healthNote
internalTitle
tunnelTitle
icons
iconSrc
```

Move them as follows:

| Old field | Target |
| --- | --- |
| `name` | Backstage `metadata.title`; stable ID is `metadata.name` |
| `description` | Backstage `metadata.description` |
| `internalHost/Port/Secure/Path` | normalized operational endpoint URL |
| `tunnelUrl` | endpoint URL |
| `external` | endpoint `scope: public|lan|cluster|host` |
| `tunnelSecure` | represented by URL scheme / ingress transport |
| `endpointEnabled` | endpoint `enabled` |
| `healthNote` | structured probe/policy metadata or documentation; no behavior hidden in prose |
| `internalTitle/tunnelTitle` | presentation only; normally delete |
| `icons/iconSrc` | `catalog/service-icons.json` / Site presentation layer |

For repository-managed services, the endpoint declaration belongs beside the
Compose service in minimal `x-nabla.operations.endpoints`.

For static/non-Compose infrastructure such as TrueNAS, pfSense, Talos and
Kubernetes, put the same normalized operational structure in
`catalog/catalog-info.yaml` plus a small
`catalog/static-operations.yaml`.

After generation and validation, delete the old manually-maintained
`catalog/homelab-services.json`.

## One-shot replacement of homelab-exposure-overrides.json

Delete the override model rather than translating it into another overlay.

Move:

| Old field | Target |
| --- | --- |
| `external` | endpoint scope |
| `tunnelUrl` | endpoint URL |
| `tunnelSecure` | URL/ingress transport |
| `cloudflareAccessRequired` | endpoint `ingress.access` |
| `endpointEnabled` | endpoint `enabled` |
| `securityException` | structured `riskAcceptances[]` |
| `healthNote` | structured probe/operational metadata |

Example:

```yaml
x-nabla:
  operations:
    endpoints:
      - name: admin-public
        url: https://truenas.albandrieu.com:7000
        role: admin
        scope: public
        trustZone: internet
        trustBoundary: true
        authenticated: true
        enabled: true
        ingress:
          provider: pfsense-haproxy
          mode: proxy
          access: none

    riskAcceptances:
      - id: truenas-public-admin-7000
        status: accepted
        scope: admin-public
        reason: Required by the current FastAPI cloud observation path.
        control: TLS plus dedicated authenticated API identity.
        reviewAfter: null
```

A security exception becomes structured evidence, not a second source of
configuration truth.

## FastAPI Sample one-shot changes

Do not keep the old Pydantic v1 contract beside the new one.

Replace:

```text
DeclaredService
DeploymentEnvironment
RuntimeBinding
ServiceLifecycle
MonitoringTarget
HomelabTopologyNode
homelab-services.json
homelab-exposure-overrides.json
```

with:

```text
BackstageEntity
EntityRef
NablaOperations
NablaEndpoint
NablaRelation
CatalogSnapshot
```

### Sources

Fetch:

```text
catalog/generated/entities.json
catalog/generated/operations.json
catalog/generated/relations.json
```

All three carry the same `catalogRevision`.

Reject the snapshot if revisions differ.

### Join key

Use only the full Backstage entity reference:

```text
component:default/prometheus
resource:default/postgresql
```

Never join runtime evidence on display names.

### Offline fallback

Replace both current packaged JSON files with a **single generated snapshot**:

```text
nabla/api/data/homelab-catalog.json
```

It must be produced from the canonical nabla-compose artifacts, never edited by
hand.

No legacy field aliases.

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
- normalized operations for endpoint/exposure;
- normalized relations for graph edges/evidence;
- FastAPI runtime observations separately;
- security enrichment separately.

Remove presentation-critical operational fields from the catalog UI fallback.

The Site may keep its own icon/layout mapping, because icon choice and graph
position are presentation concerns rather than infrastructure truth.

## Static infrastructure normalization

Replace `catalog/service-topology.static.json` with standards-first sources.

Suggested:

```text
catalog/catalog-info.yaml
catalog/static-operations.yaml
```

`catalog-info.yaml` contains:

- Domain `nabla`;
- System `nabla-homelab`;
- Group `nabla-platform`;
- Resources for TrueNAS, pfSense, Kubernetes, Talos, etc.

`static-operations.yaml` contains only endpoint/startup/custom-relation metadata
not representable by Backstage.

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
9. generate normalized JSON/API artifacts;
10. generate CycloneDX;
11. calculate one revision across all canonical inputs;
12. fail `--check` if generated output is stale.

### Mandatory quality gates

Fail if:

- a managed Compose service has no entity-ref or explicit ignore;
- a catalog entity expected to run has no runtime binding;
- two services claim the same runtime identity unexpectedly;
- entity refs are unresolved;
- `metadata.name` is not stable lowercase kebab-case;
- duplicate display names are used as joins;
- an endpoint marked private has a public ingress definition;
- a public endpoint has no explicit authentication/access policy;
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
    albandrieu.com/status: active
    albandrieu.com/criticality: medium
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
      - "172.17.0.24:31086:7474"
      - "172.17.0.24:31087:7687"

    healthcheck:
      test:
        - CMD-SHELL
        - wget --no-verbose --tries=1 --spider http://127.0.0.1:7474/ || exit 1

    x-nabla:
      operations:
        intent: active
        startup:
          phase: secondary-data
          priority: 50
          blocksLaterWaves: true
        endpoints:
          - name: lan-ui
            url: http://172.17.0.24:31086
            role: ui
            scope: lan
            trustZone: homelab-lan
            trustBoundary: false
            authenticated: true
            enabled: true
```

Notice what disappeared from x-nabla:

- id/name/description;
- kind/category;
- criticality;
- security functions;
- runtime containerService;
- monitoring URL already represented by Compose healthcheck or endpoint;
- network membership.

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
    albandrieu.com/criticality: low
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

    x-nabla:
      operations:
        intent: active
        startup:
          phase: platform-services
          priority: 80
          blocksLaterWaves: false

      relations:
        - targetRef: resource:default/neo4j-security
          semantic: storesIn
          strength: required
          evidence:
            - apps/cartography/compose.yml:NEO4J_URL
```

The standard Backstage `dependsOn` expresses the generic dependency. The
Nabla relation adds the richer security meaning `storesIn`.

## One-shot implementation scope

This should be implemented as one coordinated schema cutover, not as a long
compatibility migration.

### nabla-compose

- add Backstage descriptors;
- bulk-convert all current x-nabla blocks;
- add Compose project names;
- add entity-ref runtime labels;
- remove redundant `container_name` values where safe;
- derive networks/ports/profiles/health/dependencies from Compose;
- replace static topology source;
- replace generator and schemas;
- generate Backstage JSON, operations, relations and CycloneDX;
- remove old `services.json`, `service-topology.json` and
  `homelab-services.json` only when the coordinated consumer PRs are ready.

### fastapi-sample

- replace old catalog/topology Pydantic models;
- replace two packaged legacy service/exposure JSON files with one generated
  catalog snapshot;
- remove name-based and legacy-field joins;
- keep runtime/provider evidence models separate from declared catalog models;
- expose entity-ref-based read-only APIs.

### nabla-site-alban

- replace old catalog DTO;
- use entity refs as graph IDs;
- consume normalized endpoints/relations;
- keep presentation-only icons/layout local;
- remove the old bundled service shape.

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
