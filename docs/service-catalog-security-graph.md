# Service catalog, security graph and SBOM architecture

Last reviewed: 2026-09-20.

## Decision

Keep **repository-local `x-nabla` metadata as the declared source of truth** for
service identity, runtime intent and declared service-to-service relationships.
Do not replace it with another hand-maintained catalog.

Standardize the generated views instead:

1. **Backstage catalog entities** are the primary interoperable service-catalog
   projection.
2. **CycloneDX** is the primary software-supply-chain/SBOM interchange format.
3. **Cartography + Neo4j** is the analytical relationship/attack-path layer, not
   the source of lifecycle truth and not a second CMDB.
4. **DefectDojo** aggregates findings; **Dependency-Track** consumes CycloneDX
   for component/supply-chain risk; neither owns Nabla service identity.
5. Existing `catalog/services.json` and `catalog/service-topology.json` remain
   a compatibility contract while FastAPI Sample and Site Alban migrate.

This gives the homelab a standards-oriented catalog without introducing a second
manual inventory.

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
| Lifecycle ordering | Authoritative | Must remain non-authoritative |

Therefore Cartography should **enrich and query** the Nabla catalog, not replace
it. A Cartography-discovered edge must never silently change reboot/deployment
ordering. Declared `x-nabla` relations remain authoritative for operations;
Cartography relations are observed/analytical evidence.

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

## Backstage as the service-catalog interchange schema

Backstage catalog entities provide a mature open-source entity envelope:
`apiVersion`, `kind`, `metadata`, `spec`, entity references and standard
relations. Backstage supports Component, Resource, API, System and Domain entities
and serializes the same shape as YAML descriptors or JSON API entities.

Use it as the **generated interoperability contract**, not the authoring source.

### Direct mapping from the existing catalog

No manual rewrite of all services is required. Generate Backstage entities
directly from the current `services.json` + `service-topology.json` on the
first iteration.

| Nabla | Backstage projection |
| --- | --- |
| service `id` | `metadata.name` and stable entity reference |
| `name` | `metadata.title` |
| `description` | `metadata.description` |
| `category` | `metadata.tags` and/or System mapping |
| deployable/service | `kind: Component` |
| database/storage/cluster | `kind: Resource` |
| explicit API definition | `kind: API` |
| homelab security/network/data grouping | `kind: System` |
| overall homelab | `kind: Domain` |
| `dependsOn` / storage / hosting dependency | `spec.dependsOn` where lossless |
| API provider/consumer | `providesApis` / `consumesApis` when an API entity exists |
| source repository/path | Backstage annotations |
| `active/planned/disabled` | generated lifecycle + lossless `nabla.dev/status` annotation |
| runtime binding | `nabla.dev/*` annotations/properties |
| criticality/security functions | tags + `nabla.dev/*` annotations |

Do not force every Nabla edge into a Backstage native relation. Backstage does not
natively preserve all of `routesTo`, `exposedBy`, `observedBy`, strength and
evidence semantics. Keep those losslessly in the generated topology sidecar and
in the Neo4j graph.

Suggested generated artifacts:

```text
catalog/
├── services.json                      # compatibility v1
├── service-topology.json              # compatibility/lossless topology v1
├── backstage/
│   ├── catalog-info.yaml              # multi-document descriptors
│   └── entities.json                  # same entities for API consumers
└── cyclonedx/
    └── homelab.cdx.json               # aggregate service/component BOM
```

The existing `catalogRevision` remains the revision anchor across all generated
artifacts. A generation run must fail if the projections disagree.

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
Compose / x-nabla                         runtime observations
       │                                  TrueNAS / k8s / NetBox
       │                                           │
       ▼                                           ▼
services.json + service-topology.json      observed assets/state
       │
       ├──────────────┐
       ▼              ▼
Backstage          CycloneDX <── Trivy SBOM / image digest
entities              │
       │               ├──> Dependency-Track
       │               └──> DefectDojo findings correlation
       │
       └──────────────┬─────────────────────────────┐
                      ▼                             │
                Cartography/Neo4j <─────────────────┘
                      │
               Cartography Rules /
               bounded Cypher queries
                      │
                      ▼
          FastAPI Sample read-only facade
                      │
                      ▼
             nabla-site-alban UI
```

Authority boundaries remain explicit:

- **`x-nabla` / Git:** declared service identity, intent, operational dependency.
- **Backstage projection:** interoperable catalog representation.
- **CycloneDX/Trivy:** package/service supply-chain inventory.
- **NetBox:** network/infrastructure intent.
- **TrueNAS/Kubernetes:** runtime observation.
- **Dependency-Track:** component/SBOM risk.
- **DefectDojo:** findings and deduplication.
- **Cartography/Neo4j:** graph correlation and attack-path analysis.
- **FastAPI Sample:** reconciliation/read-only API facade.
- **Site Alban:** presentation only.

## Direct migration plan

The migration must reuse the existing generated catalog to reduce risk and
delivery time.

### Phase A — generator projections in `nabla-compose`

1. Add a deterministic exporter that reads the existing generated
   `services.json` + `service-topology.json`.
2. Generate Backstage `catalog-info.yaml` + `entities.json`.
3. Generate aggregate CycloneDX `homelab.cdx.json`.
4. Add schemas/validation and `--check` integration to the existing
   topology/quality gate.
5. Preserve current v1 files unchanged for consumers.
6. Add cross-projection invariants:
   - every service ID has one Backstage entity;
   - every relation endpoint resolves;
   - every generated identity carries the same `catalogRevision`;
   - no secret field is exported;
   - planned/disabled status remains explicit.

Do not require Backstage itself to be deployed before these artifacts are useful.

### Phase B — FastAPI Sample

Replace the independent hand-maintained service inventory incrementally.

1. Add a v2 loader for generated Backstage entities plus the lossless Nabla
   topology.
2. Reconcile runtime/health/exposure evidence by **stable service ID**, never by
   display name.
3. Keep `homelab-services.json` and exposure overrides as temporary
   compatibility/exception overlays only.
4. Move fields that already exist canonically in `nabla-compose` out of the
   FastAPI copy; retain only observer/runtime evidence and explicit policy
   exceptions.
5. Expose a versioned read-only API whose catalog objects use the Backstage entity
   shape and carry `catalogRevision`.
6. Keep v1 endpoints during one compatibility window and contract-test v1/v2
   identity parity.
7. Add security-enrichment endpoints/fields only as joins to DefectDojo,
   Dependency-Track and Neo4j; do not make FastAPI their database of record.

### Phase C — `nabla-site-alban`

1. Prefer FastAPI v2/Backstage-shaped entities.
2. Keep the current bundled `public/homelab-services.json` only as a
   last-known-good v1 fallback until v2 is proven.
3. Key React Flow nodes/edges by stable catalog IDs/entity refs, not labels.
4. Render relation type, strength and evidence without collapsing the current
   topology into generic `dependsOn`.
5. Add optional security overlays for:
   - internet exposure;
   - runtime drift;
   - vulnerability/finding counts;
   - NIST CSF function;
   - attack-path/rule findings.
6. Display provenance/freshness separately from health so missing security data
   cannot incorrectly mark an application DOWN.
7. Remove the v1 fallback only after revision-parity and stale-artifact tests pass.

### Phase D — Cartography/Neo4j

1. Load the stable Nabla/Backstage identity map into Neo4j.
2. Import runtime/provider observations with Cartography.
3. Correlate on explicit stable IDs, pURLs, image digests, repository URLs and
   infrastructure IDs; never fuzzy-match on display names.
4. Implement a small initial ruleset:
   - public exposure to critical service;
   - vulnerable component on exposed service;
   - missing/unknown owner or runtime binding;
   - required dependency absent from runtime;
   - security finding on shared high-blast-radius dependency.
5. Only after the model is stable, package the Nabla loader as a Cartography-style
   custom module.

## Compatibility and deletion gates

Do not delete the current catalog or consumer files at the start.

Retirement requires all of the following:

- deterministic Backstage/CycloneDX generation;
- stable ID parity across v1/v2;
- FastAPI v2 contract accepted with v1 fallback;
- Site Alban v2 accepted with v1 fallback;
- at least one representative Trivy -> CycloneDX -> Dependency-Track flow;
- at least one findings flow into DefectDojo;
- at least one Nabla entity/edge visible in Neo4j plus one bounded rule/query;
- no unresolved service/relation IDs;
- rollback to the previous v1 consumer path documented and tested.

## Initial implementation order

1. Generator/exporters and contract tests in `nabla-compose`.
2. FastAPI v2 read-only adapter with v1 fallback.
3. Site Alban v2 reader with v1 fallback.
4. Trivy CycloneDX on a representative service/image.
5. Dependency-Track + DefectDojo correlation.
6. Neo4j import and bounded Cartography rules.
7. Remove duplicated FastAPI/Site inventory only after parity is proven.

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
