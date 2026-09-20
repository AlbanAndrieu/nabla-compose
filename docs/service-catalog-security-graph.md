# Service catalog, security graph and SBOM architecture

Last reviewed: 2026-09-20.

## Decision

The deeper normalization review supersedes the earlier idea of keeping the full
catalog model inside `x-nabla`.

Use **native Backstage `catalog-info.yaml` descriptors as the catalog authoring
format**, stored beside each Compose application. Keep Compose as the runtime
source and reduce `x-nabla` to Nabla-only operational semantics that have no
good standard representation.

The detailed breaking-v2 design and one-shot consumer cutover are defined in
[Service catalog v2 normalization and one-shot cutover](./service-catalog-v2-normalization.md).

Target authority:

1. **Backstage descriptors** — entity identity, kind/type, owner, system,
   catalog lifecycle and standard relations.
2. **Docker Compose** — runtime service/project/image/ports/networks/healthcheck/
   profiles/dependencies.
3. **Minimal `x-nabla`** — exceptional order-only boot constraints, rare relation enrichment, structured risk acceptances, and temporary desired exposure/security intent for providers that are not yet Git/IaC-managed. Provider state never replaces declared intent.
4. **CycloneDX** — generated service/SBOM/supply-chain representation.
5. **Cartography + Neo4j** — observed graph correlation and attack-path analysis.
6. **DefectDojo / Dependency-Track** — findings and SBOM/component risk,
   respectively.

This is a **one-shot v2 schema cutover**, not a long-lived v1/v2 migration.
The old flat service/exposure schemas are removed once the coordinated
`nabla-compose`, `fastapi-sample` and `nabla-site-alban` PRs are ready.

## Current Nabla model

The current generated catalog is already close to a graph-oriented asset model.

`catalog/services.json` carries stable service identity and attributes such as:

- `id`, `name`, `kind`, `category`;
- `sourcePath` and `composeService`;
- `status: active | planned | disabled`;
- `criticality`, `securityFunctions`, lifecycle and monitoring metadata;
- runtime bindings such as TrueNAS App/container identity and networks.

`catalog/service-topology.json` carries nodes plus typed relations. Current
relations include concepts such as:

- `dependsOn`;
- `storesIn`;
- `hostedBy`;
- `partOf`;
- `consumesApi`;
- `routesTo`;
- `exposedBy`;
- `observedBy`.

Relations also preserve `strength`, descriptions and evidence. This is valuable
security provenance and must not be flattened away during standardization.

The weakness is not the graph itself. The weakness is that its public contract is
Nabla-specific, while FastAPI and Site Alban still maintain compatibility data
shaped for their own presentation/probe needs.

## Comparison with Cartography

Cartography is optimized for **ingesting observed infrastructure/security data
from providers into Neo4j**. Its current architecture uses declarative node and
relationship schemas, provider-specific intel modules, stable node identifiers,
an `update_tag` / `lastupdated` freshness model and cleanup of stale graph
objects after a sync.

That differs from Nabla in an important way:

| Concern | Nabla today | Cartography |
| --- | --- | --- |
| Primary input | Git/Compose + `x-nabla` | Provider/API observations |
| Intent | Declared desired topology | Observed infrastructure graph |
| Storage | Generated JSON | Neo4j |
| Relations | Typed + strength + evidence | Typed Neo4j relationships |
| Freshness | Git/catalog revision | Sync `update_tag` / `lastupdated` |
| Security queries | Limited/custom | Cartography Rules / Cypher |
| Boot/reconciliation | custom phase/priority waves today | observed graph is non-authoritative; v2 derives boot DAG from Backstage/Compose dependencies + readiness |

Therefore Cartography should **enrich and query** the Nabla catalog, not replace
it. A Cartography-discovered edge must never silently change reboot/deployment
ordering. Standard declared relations live in Backstage/Compose; Cartography
relations are observed/analytical evidence.

### Cartography integration model

Phase 1 should be deliberately small: load Nabla entities/relations into Neo4j
with stable identities and Cartography-compatible freshness/provenance behavior.

Recommended node identity:

```text
NablaService.id = <existing catalog service id>
NablaService.backstageRef = <kind>:default/<id>
NablaService.bomRef = urn:nabla:service:<id>
```

Recommended relationship mapping:

```text
dependsOn  -> DEPENDS_ON
storesIn   -> STORES_IN
hostedBy   -> HOSTED_BY
partOf     -> PART_OF
consumesApi -> CONSUMES_API
routesTo   -> ROUTES_TO
exposedBy  -> EXPOSED_BY
observedBy -> OBSERVED_BY
```

Every imported node/relation should carry at least `source`,
`catalogRevision`, `lastupdated` and, where applicable, evidence/provenance.

Phase 2 may package this loader as a Cartography-style custom `nabla` intel
module using the project's NodeSchema/relationship patterns. Keep the first
migration independent of an upstream Cartography fork so the homelab can adopt
the model immediately.

## Backstage as the native catalog schema

Backstage catalog entities provide the standard entity envelope used by the
target design: `apiVersion`, `kind`, `metadata`, `spec` and entity
references.

Use **real `catalog-info.yaml` files as the authoring source**, not a Backstage-
shaped structure nested inside `x-nabla`.

Example layout:

```text
apps/cartography/
├── catalog-info.yaml
└── compose.yml
```

The migration from the current catalog can still be automatic: generate the first
set of descriptors from existing `services.json` / `service-topology.json`,
review them, then make those descriptors canonical in the same breaking cutover.

Key normalization:

| Current Nabla | Target |
| --- | --- |
| `id` | Backstage `metadata.name` |
| display `name` | `metadata.title` |
| `description` | `metadata.description` |
| free-form `kind` | Backstage `kind` + controlled `spec.type` |
| `category` | tags initially |
| `criticality` | queryable catalog label + OpenTelemetry `service.criticality` projection |
| `securityFunctions` | `nist-*` tags + NIST CSF projection |
| `partOf` | Backstage System/Domain membership |
| `dependsOn` | Backstage `spec.dependsOn` |
| `providesApi/consumesApi` | Backstage API refs |
| source repository/path | Backstage source/GitHub annotations |
| `active/planned/disabled` | qualified Backstage operational-state label; not `spec.lifecycle` |
| boot `lifecycle.phase/priority` | delete; derive required ordering from Backstage/Compose and readiness |
| exceptional boot ordering | minimal x-nabla `after/before/wants` only |
| runtime identity | derived from Compose + one entity-ref runtime label |
| public/LAN endpoints | split desired/observed: derive runtime facts; preserve desired hostname/visibility/access intent in Git until provider-native IaC owns it; project reconciled view to CycloneDX |

Do not force richer edges such as `routesTo`, `exposedBy`, `observedBy`,
`storesIn` or their evidence into generic Backstage dependencies. Backstage owns
the generic catalog relation; Nabla keeps only the security/operational semantic
refinement.

Generated artifacts after the cutover:

```text
catalog/
├── catalog-info.yaml
├── generated/
│   ├── entities.json
│   ├── operations.json
│   ├── relations.json
│   └── homelab.cdx.json
└── service-icons.json
```

All generated artifacts share one `catalogRevision`.

## CycloneDX and Trivy

CycloneDX can represent components, services and their dependency graph. Use it
for two complementary layers.

### 1. Declared homelab service BOM

Generate `catalog/cyclonedx/homelab.cdx.json` from the existing Nabla catalog.

Use stable BOM references:

```text
urn:nabla:service:<service-id>
```

The aggregate BOM should preserve declared service/component dependencies and
carry safe properties such as category, status, criticality, source path and
Backstage entity reference. Do not put credentials, tokens or private secret
material into CycloneDX properties.

### 2. Per-artifact/package SBOM

Generate package/image SBOMs with Trivy, for example:

```bash
trivy image --format cyclonedx --output sbom.cdx.json <image@digest>
trivy fs --format cyclonedx --output sbom.cdx.json <source-tree>
```

Keep the image digest / pURL as the package identity and associate that SBOM with
the stable Nabla service ID. Package SBOMs may be CI/runtime artifacts rather than
large committed files.

Trivy also accepts CycloneDX SBOM as scan input. Keep **inventory generation** and
**vulnerability findings** as distinct evidence so a BOM is not mistaken for a
vulnerability report.

## DefectDojo and Dependency-Track

Use **Dependency-Track** as the CycloneDX component/supply-chain risk engine.

Use **DefectDojo** as the normalized findings layer for Trivy, SAST, DAST, secret,
IaC and other scanner reports. The open-source DefectDojo import/reimport API
supports its file parsers, including CycloneDX and Trivy. Do not design the core
homelab flow around Pro-only asset/SBOM endpoints.

Recommended flow:

```text
Trivy image/fs
   ├── CycloneDX SBOM ──> Dependency-Track
   └── vulnerability report ──> DefectDojo

Nabla service ID
   └── stable correlation key attached to project/product metadata
```

If a DefectDojo deployment later exposes a suitable CycloneDX export, treat it as
an enrichment/snapshot source. It must not replace the original Trivy SBOM or the
declared Nabla topology.

## Security-standard alignment

The catalog already carries `securityFunctions`. Normalize those values to the
NIST CSF 2.0 functions:

- Govern;
- Identify;
- Protect;
- Detect;
- Respond;
- Recover.

This is classification, not a risk score. Risk posture should be derived from
evidence such as exposure, known vulnerabilities, missing controls, identity/
privilege paths and runtime observations.

The combined model can then answer questions such as:

- which internet-exposed services transit a vulnerable component?
- which critical service depends on a database or identity provider with an open
  finding?
- which observed attack path reaches a high-criticality component?
- which NIST CSF functions have no deployed control/evidence?
- which runtime service exists but has no declared catalog identity?
- which declared service is absent from runtime or has an untracked public edge?

## Target architecture

```text
apps/*/catalog-info.yaml                 apps/*/compose.yml
      Backstage-native                        Compose-native
             │                                      │
             └──────────────┬───────────────────────┘
                            │
                 minimal x-nabla operations
                 + custom relation evidence
                            │
                            ▼
                   deterministic generator
                 ┌──────────┼──────────┐
                 ▼          ▼          ▼
          Backstage JSON   provider views  CycloneDX
                 │          + conditions   │
                 │              │          ├──> Dependency-Track
                 │              │          └──> Trivy/DefectDojo joins
                 └──────────────┼──────────────┐
                                ▼              │
                         Cartography/Neo4j <────┘
                                │
                         rules / Cypher
                                │
                                ▼
                         FastAPI Sample
                                │
                                ▼
                        nabla-site-alban
```

Authority boundaries:

- **Backstage descriptors / Git:** catalog identity and standard relations.
- **Compose:** desired runtime definition.
- **minimal `x-nabla`:** exceptional systemd-style order-only constraints, rare relation enrichment, structured risk acceptances and temporary Gateway-like desired exposure intent for non-IaC providers; no flat merged service/exposure inventory.
- **OpenTelemetry:** runtime telemetry identity semantics.
- **CycloneDX/Trivy:** service/package supply-chain inventory.
- **NetBox:** network/infrastructure intent where deployed.
- **TrueNAS/Docker/Kubernetes:** observed runtime/backends; Kubernetes Service/EndpointSlice/Gateway API is consumed natively where present.
- **Dependency-Track:** component/SBOM risk.
- **DefectDojo:** findings and deduplication.
- **Cartography/Neo4j:** graph correlation and attack-path analysis.
- **FastAPI Sample:** Kubernetes-style reconciled read model: Git/provider-native declarations are `spec`-like desired state, provider/runtime evidence is `status`-like observation with conditions; not a second catalog.
- **Site Alban:** presentation only.

## One-shot cutover plan

The detailed field-level plan is in
`docs/service-catalog-v2-normalization.md`.

### nabla-compose

1. Generate initial native Backstage descriptors from the current v1 catalog.
2. Bulk-rewrite Compose files:
   - add top-level project `name`;
   - bind runtime services to Backstage entity refs using one reverse-DNS label;
   - remove redundant catalog fields and standard relations from `x-nabla`;
   - delete phase/priority/wave metadata;
   - derive required cross-entity boot dependencies from Backstage
     `spec.dependsOn`, same-project ordering from Compose `depends_on`, and gate
     dependents on readiness;
   - use x-nabla `after/before/wants` only for exceptional systemd-style order-only/weak constraints;
   - derive project/service/image/network/port/profile/health facts from Compose
     rather than repeating them.
3. Replace static topology JSON with native Backstage static entities; do not recreate a static endpoint inventory.
4. Replace the generator with a standards-first join/validation pipeline.
5. Generate Backstage/CycloneDX projections; preserve desired exposure intent in provider-native Git/IaC or temporary minimal route-intent records, while runtime/network status comes from Compose, Traefik, Cloudflare, pfSense and Kubernetes observations.
6. Remove old generated v1 service/topology/exposure contracts only after every legacy public hostname/visibility/access requirement has a declared v2 home and the coordinated consumer PRs are ready.

### FastAPI Sample

Perform a breaking model replacement, not a compatibility layer:

- replace old flat service/topology DTOs with Backstage entity refs plus resource-oriented runtime/network observations;
- delete `homelab-services.json` and `homelab-exposure-overrides.json` without a canonical flat replacement;
- consume desired routes from Git (Traefik/Gateway/provider IaC or temporary route intent) and observed routes/backends from Cloudflare, pfSense HAProxy, TrueNAS/Docker and Kubernetes Service/EndpointSlice/Gateway status;
- normalize observation state to Kubernetes-style conditions (`True|False|Unknown`, reason/message/transition time);
- join runtime/provider evidence only by full entity ref;
- allow only an optional generated cold-start cache, never a hand-maintained catalog.

### nabla-site-alban

- replace current service DTO in one pass;
- use full entity refs as graph node IDs;
- consume Backstage metadata/relations plus FastAPI runtime/network resource views;
- keep icons/graph positioning as presentation-only data;
- remove the old bundled flat service shape.

### Cartography / security evidence

- map Backstage entity refs to explicit Neo4j identities; keep one canonical declared edge and enrich it only when a security query genuinely needs extra semantics;
- project CycloneDX service/component identities and image digests;
- correlate DefectDojo/Dependency-Track evidence without changing declared
  lifecycle/order;
- add bounded rules for public exposure, vulnerable exposed components, missing
  ownership/runtime binding and shared high-blast-radius dependencies.

## One-shot acceptance gates

There is no permanent v1/v2 compatibility contract.

Before the coordinated cutover, require:

- every managed Compose service has a resolvable Backstage entity ref or explicit
  ignore reason;
- Backstage descriptors validate;
- generated operations/relations/CycloneDX share one revision;
- no relation target is unresolved;
- no duplicate runtime identity exists unexpectedly;
- before legacy flat exposure files are removed, every intended hostname/visibility/access requirement is present in a new declared desired-state source; provider-derived routes/backends then reconcile by entity ref;
- FastAPI parses only the new contract and passes its local gate;
- Site Alban parses only the new contract and passes its local gate;
- any optional generated FastAPI cold-start cache is derived-only and revision-consistent with Backstage inputs;
- one representative Trivy -> CycloneDX -> Dependency-Track flow works;
- one findings import into DefectDojo works;
- one Nabla entity/relation is queryable in Neo4j.

Prepare all three repository PRs before merging because GitHub cannot provide an
atomic cross-repository transaction.

Cutover order:

1. `nabla-compose`;
2. `fastapi-sample`;
3. `nabla-site-alban`;
4. cross-repository revision/health/topology smoke.

## References

- Backstage catalog descriptor format:
  https://backstage.io/docs/features/software-catalog/descriptor-format/
- CycloneDX specification overview:
  https://cyclonedx.org/specification/overview/
- CycloneDX service dependencies:
  https://cyclonedx.org/use-cases/service-dependencies/
- Trivy SBOM documentation:
  https://trivy.dev/docs/latest/supply-chain/attestation/sbom/
- Cartography:
  https://github.com/cartography-cncf/cartography
- Cartography operations / freshness model:
  https://github.com/cartography-cncf/cartography/blob/master/docs/root/ops.md
- Cartography Rules:
  https://github.com/cartography-cncf/cartography/blob/master/docs/root/usage/rules.md
- DefectDojo import/reimport API:
  https://docs.defectdojo.com/import_data/import_scan_files/api_pipeline_modelling/
- DefectDojo supported parsers:
  https://docs.defectdojo.com/supported_tools/parsers/
