# Nabla service topology

`service-topology.json` is the generated, design-time graph for relationships between homelab services.

It intentionally **does not use Docker Compose `depends_on` as the general dependency model**. A service may consume another service, route traffic through it, export telemetry to it, or store data in it while still remaining independently deployable. `depends_on` should only be used in a Compose file when startup/lifecycle ordering is genuinely required by that Compose project.

## Ownership

`nabla-compose` owns deployment configuration and therefore has the best evidence for service-to-service relationships: environment variables, endpoints, proxy labels, metrics labels and explicit Compose dependencies. Presentation repositories consume the generated topology instead of inventing it.

For migrated services, topology metadata lives beside the service under the Compose extension key `x-nabla`. Docker Compose ignores `x-*` extension fields, so these architecture relationships do not alter startup behavior.

Example:

```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:latest
    x-nabla:
      id: openwebui
      name: Open WebUI
      kind: application
      category: ai
      relations:
        - target: litellm
          type: consumesApi
          strength: required
```

Logical integration nodes that are relevant to the architecture but are not currently represented by their own tracked Compose service can be declared at document level:

```yaml
x-nabla:
  nodes:
    - id: searxng
      name: SearXNG
      kind: search
      category: ai
```

This is used for integrations such as SearXNG and Open Terminal without inventing containers that do not exist in this repository.

## Generation

Generate the portable catalog with:

```bash
python scripts/generate-service-topology.py
```

Verify that the committed artifact is synchronized with its sources with:

```bash
python scripts/generate-service-topology.py --check
```

The pre-commit policy runs the generator whenever relevant Compose metadata, the transitional static topology, or the generator itself changes. `catalog/service-topology.json` is therefore a generated artifact and must not be edited manually.

During the incremental migration, `service-topology.static.json` retains nodes and relations that have not yet moved into service-local `x-nabla` blocks. It is merged with `x-nabla` metadata by the generator. The target state is to remove that transitional file once all useful relations are co-located with their deployment configuration.

## Relation semantics

The model borrows the common `dependsOn`, `consumesApi`, `providesApi` and `partOf` vocabulary from software catalogs such as Backstage, then adds operational relations useful for this homelab:

- `dependsOn`: functional data/runtime dependency.
- `consumesApi`: source calls an API exposed by the target.
- `providesApi`: source provides an API used by the target.
- `partOf`: source belongs to a larger system/component.
- `routesTo`: source selects or forwards work to the target.
- `observedBy`: source exports telemetry or metrics to the target.
- `storesIn`: source writes data/object payloads to the target.
- `authenticatesVia`: source delegates authentication/identity to the target.
- `exposedBy`: target proxies or exposes the source.
- `automates`: source orchestrates work in the target.

`strength` is deliberately separate from relation type:

- `required`: the feature described by the relation cannot operate correctly without the target.
- `optional`: integration can be disabled or the source has a degraded/alternative path.

Neither value means Docker Compose must wait for the target at startup.

Each relation also contains an `evidence` array. Prefer a concrete configuration reference when one exists. When a relation is architectural metadata rather than a directly parseable runtime setting, the generator records the corresponding `x-nabla.relations[...]` declaration as evidence.

## Declared vs observed graph

The declared catalog describes intended architecture. It should eventually be compared with an **observed** service graph derived from OpenTelemetry traces (for example Tempo/Grafana service-graph metrics). These two sources answer different questions:

- declared: *what should talk to what?*
- observed: *what actually talked to what?*

A future UI can highlight `declared-only`, `observed-only` and `declared+observed` edges to detect topology drift without changing deployment order.
