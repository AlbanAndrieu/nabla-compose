# Nabla service topology

`service-topology.json` is the declared, design-time graph for relationships between homelab services.

It intentionally **does not use Docker Compose `depends_on` as the general dependency model**. A service may consume another service, route traffic through it, export telemetry to it, or store data in it while still remaining independently deployable. `depends_on` should only be used in a Compose file when startup/lifecycle ordering is genuinely required by that Compose project.

## Why this catalog lives here

`nabla-compose` owns the deployment configuration and therefore has the best evidence for service-to-service relationships: environment variables, endpoints, proxy labels, metrics labels and explicit Compose dependencies. Presentation repositories should consume this topology rather than inventing it.

Each relation contains an `evidence` array that points back to the configuration from which the relation was derived. This keeps inferred architecture reviewable.

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

## Future `x-nabla` migration

Docker Compose supports extension fields prefixed with `x-`; Compose ignores these fields. The preferred long-term direction is to co-locate relation metadata next to each service, for example:

```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:latest
    x-nabla:
      relations:
        - target: litellm
          type: consumesApi
          strength: required
```

A generator can then normalize all `x-nabla` blocks into `catalog/service-topology.json`. The checked-in JSON remains useful as a portable artifact for FastAPI, the website, tests and other tooling.

This migration is intentionally deferred until a YAML parser/generator is introduced with tests; the first version keeps runtime Compose files unchanged.

## Declared vs observed graph

The declared catalog describes intended architecture. It should eventually be compared with an **observed** service graph derived from OpenTelemetry traces (for example Tempo/Grafana service-graph metrics). These two sources answer different questions:

- declared: *what should talk to what?*
- observed: *what actually talked to what?*

A future UI can highlight `declared-only`, `observed-only` and `declared+observed` edges to detect topology drift without changing deployment order.
