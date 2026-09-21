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
| public Cloudflare route desired state | temporary Git route intent until Cloudflare IaC exists |
| public Cloudflare route observed state | Cloudflare Tunnel Public Hostname API |
| public Cloudflare authorization desired state | route intent `access.required` until Access policy is IaC-managed |
| public Cloudflare authorization observed state | Access Application + attached policy + Service Token/live-edge evidence |
| direct WAN desired state | temporary Git route intent until pfSense/HAProxy has a reviewed declarative source |
| direct WAN observed state | pfSense HAProxy frontend/backend |
| actual Docker/TrueNAS backend | TrueNAS/Docker observation |
| runtime/route state | FastAPI Kubernetes-style conditions |
| exceptional accepted risk | structured risk-acceptance metadata only |

The v2 model must preserve **desired exposure/security intent even when the
provider is unreachable**.

Kubernetes calls this the object `spec`: desired state persists independently
from `status`. Nabla follows the same rule.

For providers that are already declarative in Git, the provider-native
configuration is the desired state. For providers that are still dashboard/API
managed, a temporary minimal Git route-intent declaration preserves:

- intended hostname;
- intended visibility/security boundary;
- desired protocol;
- desired gateway/provider;
- desired access-protection requirement.

Example:

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

`backendPort` references a named Compose/Kubernetes service port and therefore
does not copy an IP address or numeric port.

The provider observer supplies status such as `Accepted`, `ResolvedRefs`,
`Programmed`, `AccessProtected` and `Ready`. If Cloudflare is down, the
desired hostname and access requirement remain declared while the relevant
status becomes `Unknown`.

Do not infer `external=false` from missing provider evidence.

The temporary route-intent record is removed once the corresponding provider has
a real Git/IaC desired-state source such as Gateway API or OpenTofu/Terraform.

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

Do not add new long-lived fields to either legacy JSON. Before deleting them,
run a desired-intent parity check proving that every relevant public hostname,
visibility rule, Access requirement and accepted security exception has a v2
declarative home.

New v2 work should go to Backstage, Compose, provider-native desired state or the
temporary minimal route-intent model.
