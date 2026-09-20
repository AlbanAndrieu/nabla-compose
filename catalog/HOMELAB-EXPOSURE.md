# Homelab exposure contract — legacy v1 and v2 retirement

The current v1 runtime still contains:

- `catalog/homelab-services.json`;
- `catalog/homelab-exposure-overrides.json`;
- `catalog/service-topology.json`.

These files remain operational until the coordinated catalog-v2 cutover, but
**they are not the target architecture**.

The v2 decision is documented in
`docs/service-catalog-v2-normalization.md`.

## Why the two exposure JSON files are being deleted

The current model collapses several different concerns:

- catalog identity/presentation;
- desired container/runtime configuration;
- internal service endpoints;
- public routing;
- authorization policy;
- observed runtime health;
- explicit security exceptions.

This then requires an override-precedence rule, including cases where
`homelab-services.json` and `homelab-exposure-overrides.json` disagree.

Kubernetes avoids this shape by keeping desired and observed state in separate
resources: workload spec, Service, EndpointSlice, Gateway/Route, policy and
status conditions. Nabla v2 follows that separation without fabricating fake
Kubernetes resources for non-Kubernetes workloads.

## v2 authority map

| Concern | Authority |
| --- | --- |
| service/application identity | Backstage `catalog-info.yaml` |
| catalog lifecycle / ownership / standard dependencies | Backstage |
| Compose runtime definition | Docker Compose |
| internal published port/protocol | Compose long-syntax `ports`, including `name` and `app_protocol` |
| internal HTTP routing | Traefik labels/config |
| Kubernetes stable endpoint | Kubernetes Service |
| Kubernetes concrete backends | EndpointSlice |
| Kubernetes external route | Gateway API |
| public Cloudflare route | Cloudflare Tunnel Public Hostname API/config |
| public Cloudflare authorization | Access Application + attached policy + Service Token evidence |
| direct WAN route | pfSense HAProxy frontend/backend |
| actual Docker/TrueNAS backend | TrueNAS/Docker observation |
| runtime/route state | FastAPI Kubernetes-style conditions |
| exceptional accepted risk | structured risk-acceptance metadata only |

There is no v2 `external=true/false` inventory field. Public exposure is derived
from an actual route/listener.

There is no v2 `tunnelSecure` field. TLS/transport security is derived from the
actual listener/route/provider configuration.

There is no v2 `cloudflareAccessRequired` copy. Cloudflare Access is read from
the Cloudflare control plane. If/when Cloudflare configuration becomes
OpenTofu/Terraform-managed, that provider configuration becomes desired-state
source and the API remains observed state.

## FastAPI model

FastAPI becomes a reconciled read model, not a second catalog.

It joins resources by full Backstage entity reference and exposes separate
resource-oriented views for:

- catalog entities/relations;
- runtime observations/backends;
- network routes/listeners;
- security enrichments.

Current provider uncertainty remains `Unknown`, not a fabricated failure.

An optional build-time last-known-good cache may exist for cold start, but it is
generated and non-authoritative. It is not a replacement
`homelab-services.json`.

## Current v1 precedence until cutover

Until the coordinated v2 consumer PRs are ready, existing v1 consumers **must
still** merge `homelab-exposure-overrides.json` after
`homelab-services.json`. Removing that precedence before the one-shot cutover
would change current security behavior.

Do not add new long-lived fields to either legacy JSON. New v2 work should go to
Backstage/Compose/provider-derived models instead.
