# Nabla Service Catalog v2 and open-standard projections

## Purpose

`x-nabla` remains the authoritative authoring contract. The v2 catalog is a
generated interoperability layer, not a second CMDB and not a replacement for
Compose metadata.

The pipeline is:

```text
Compose + x-nabla
  -> catalog/services.json + catalog/service-topology.json
  -> catalog/service-catalog-v2.json
       -> catalog/backstage/catalog-info.yaml
       -> catalog/cyclonedx/homelab.cdx.json
       -> future Cartography/Neo4j declared-state ingestion
       -> future OSCAL control/evidence linkage
```

## Contract boundaries

- **Nabla v2** keeps stable IDs, typed relations, strength and evidence while
  adding stable cross-format references.
- **Backstage** is a software-catalog projection. Components/resources are
  generated with owner/system/lifecycle metadata and required dependency
  relations. Optional dependencies stay explicit as Nabla annotations because
  Backstage does not model dependency strength.
- **CycloneDX 1.7** is the security/service BOM projection. Every Nabla entity
  receives a stable `bom-ref`; required functional/runtime dependencies become
  CycloneDX dependency edges. The original typed relation remains authoritative
  in Nabla v2.
- **Cartography + Neo4j** remain an observed/enrichment graph. They must never
  rewrite declared `x-nabla` intent.
- **OSCAL** is reserved for control implementation and assessment evidence. Do
  not infer compliance from `securityFunctions` or from the mere presence of a
  service.

## Stable identity

Each v2 entity has:

- `id`: existing canonical Nabla ID;
- `ref`: `nabla:component:<id>` or `nabla:resource:<id>`;
- `standards.backstage.entityRef`;
- `standards.cyclonedx.bomRef`.

The mapping is deterministic and generated from the current topology.

## Generation and validation

```bash
python scripts/generate-service-topology.py
python scripts/generate-service-catalog-v2.py

python scripts/generate-service-topology.py --check
python scripts/generate-service-catalog-v2.py --check
```

Generated files are reviewable artifacts; edit `x-nabla` or the projection
logic instead of hand-editing them.

## Migration rule for consumers

Consumers should parse v2 first and adapt to their existing view model during
migration. Keep the v1 contracts as bounded compatibility fallbacks until
FastAPI and `nabla-site-alban` have accepted the v2 API end to end.
