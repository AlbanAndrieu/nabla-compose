---
name: nabla-service-catalog
description: Keep Docker Compose applications synchronized with the Nabla service inventory and dependency topology.
---

# Nabla service catalog

Use this skill whenever adding, renaming, removing, or materially reconnecting a service in an `apps/**/compose.yml` file.

## Required metadata

Every newly tracked runtime service must normally define a service-local `x-nabla` block with:

- `id`: stable lowercase kebab-case identifier;
- `name`: human-readable service name;
- `kind`: architectural role;
- `category`: catalog grouping;
- `runtime.provider`: normally `truenas-app` for services deployed from this repository;
- `runtime.containerService`: exact Compose service key.

Use document-level `x-nabla.nodes` only for logical or external dependencies that do not have their own tracked Compose service, such as an external firewall or database.

## Dependency model

Model architecture independently from Compose lifecycle ordering. Do not use `depends_on` as a substitute for catalog relations.

Use the existing relation vocabulary:

- `dependsOn`: functional runtime/data dependency;
- `consumesApi`: calls an API exposed by the target;
- `providesApi`: exposes an API used by the target;
- `partOf`: workload belongs to a larger logical system;
- `routesTo`: selects or forwards work to the target;
- `observedBy`: exports telemetry/metrics/logs observed by the target;
- `storesIn`: writes durable data or telemetry to the target;
- `authenticatesVia`: delegates authentication to the target;
- `exposedBy`: target proxies or exposes the source;
- `automates`: source orchestrates work in the target.

Every relation must include `strength: required|optional` and should include concrete `evidence` pointing to the configuration that proves the relationship. Do not invent dependencies merely to make the graph look complete.

## Generated contracts

Never hand-edit `catalog/services.json` or `catalog/service-topology.json` as the source of truth. After Compose metadata or static logical nodes change, run:

```bash
python scripts/generate-service-topology.py
python scripts/generate-service-topology.py --check
```

Review both generated files and ensure all relation targets resolve to known nodes.

## Dashboard and monitoring consumers

Homarr, Heimdall, Gatus, Uptime Kuma/AutoKuma and future portals or status pages are consumers of the Nabla catalog, not independent service inventories.

When implementing or updating one of these integrations:

- derive identity, name, category, URL, description and icon from `x-nabla` / `catalog/services.json`;
- use stable `x-nabla.id` values as reconciliation identifiers;
- do not make a Homarr board, Heimdall database/export, Gatus YAML file, Uptime Kuma database, AutoKuma file or Docker label the authoritative service definition;
- do not infer a health endpoint merely from a dashboard `url`;
- add validated `x-nabla` monitoring metadata before generating health-monitor definitions;
- keep credentials and API tokens in runtime secret/environment providers, never in catalog metadata or generated consumer files;
- make generated consumer artifacts deterministic and include them in the quality gate when they become repository-managed outputs;
- avoid destructive synchronization by default; deletion from a consumer requires an explicit reconciliation policy.

See `docs/service-catalog-consumers.md` for the current Homarr, Heimdall, Gatus and Uptime Kuma integration strategy and MCP choices.

## Validation

Validate each changed Compose file with:

```bash
docker compose --project-directory "$(dirname FILE)" -f FILE config --quiet --no-interpolate --no-env-resolution
```

Before publishing, run the repository quality gate:

```bash
bash scripts/quality-gate.sh
```

A new application is not complete until its Compose configuration, `x-nabla` catalog metadata, generated contracts, dependency graph and any repository-managed consumer artifacts are synchronized.
