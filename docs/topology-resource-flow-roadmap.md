# Topology resource and network-flow roadmap

## Goal

Make `fastapi-sample /api/topology` useful as an operator map without turning a
declared dependency graph into a misleading pseudo-monitoring screen.

The visualization should combine two independent layers:

1. **declared topology** from the canonical `nabla-compose` contract;
2. **observed telemetry** from bounded Prometheus/cAdvisor and Akvorado evidence.

Telemetry loss is a blind spot. It must never change a declared service into
`DOWN` or invent a dependency that is not present in the canonical topology.

## P1 — topology readability

- [x] Add a shape legend. The current renderer already uses different shapes,
  notably a hexagon for security controls; shape semantics must be explicit.
- [x] Add temporary operator hiding for high-cardinality/noisy infrastructure,
  starting with the shared Docker runtime and its generated `hostedBy` placement
  edges. Hiding is presentation state only and must not mutate the topology.
- [x] Add `Lifecycle` grouping using canonical `x-nabla.lifecycle.phase`.
- [ ] Export Docker network membership from tracked Compose service definitions
  into generated topology metadata, then enable `Docker network` grouping.
- [ ] Allow grouping to be combined with lifecycle where this remains readable,
  preferably as nested/compound groups rather than duplicated nodes.
- [ ] Persist presentation state in URL parameters so filtered views can be
  shared without changing the underlying contract.

## P1.1 — Docker network contract

Do not infer network membership from service names, URLs, host ports or
container names. The topology generator already parses Compose documents and
must export the actual Compose service `networks` membership.

Target generated metadata:

```json
{
  "runtime": {
    "provider": "truenas-app",
    "containerService": "fastapi-sample",
    "networks": ["intranet", "sample-observer", "traefik_network"]
  }
}
```

Requirements:

- normalize list and mapping Compose syntaxes;
- export logical network names and prefer a literal top-level Compose `name`
  when an external network has a stable canonical runtime name;
- never expand or guess unresolved `${...}` network-name expressions;
- keep the field optional for non-Compose/logical nodes;
- preserve all memberships: a service can belong to more than one Docker network;
- add schema + generator tests before the UI consumes it.

For visualization, a Cytoscape node can have only one compound parent. The UI
therefore must not silently pick the first network for a multi-network service.
Use the exact membership set as the grouping key (for example
`intranet + sample-observer + traefik_network`) or provide an explicit network
filter/highlight mode when a single-network view is desired.

## P1.2 — resource-aware node sizing

TrueNAS already exposes cAdvisor and Prometheus already scrapes it as
`job="truenas_cadvisor"`. Do not add a second container resource collector.

Use bounded Prometheus queries grouped by the Docker Compose service label:

```promql
sum by (container_label_com_docker_compose_service) (
  rate(container_cpu_usage_seconds_total{
    job="truenas_cadvisor",
    container_label_com_docker_compose_service!=""
  }[2m])
)

sum by (container_label_com_docker_compose_service) (
  container_memory_working_set_bytes{
    job="truenas_cadvisor",
    container_label_com_docker_compose_service!=""
  }
)
```

Also expose per-container total RX/TX as supplementary evidence:

```promql
sum by (container_label_com_docker_compose_service) (
  rate(container_network_receive_bytes_total{job="truenas_cadvisor"}[2m])
)

sum by (container_label_com_docker_compose_service) (
  rate(container_network_transmit_bytes_total{job="truenas_cadvisor"}[2m])
)
```

Presentation rules:

- default remains declared criticality sizing;
- optional `CPU + RAM telemetry` sizing uses observed data only;
- normalize against a robust fleet percentile (for example P95), not a fixed
  absolute maximum that one outlier can dominate;
- use a square-root visual scale so small services remain selectable;
- show the real CPU/RAM values in the node detail/hover;
- display the observation window, timestamp and stale state;
- missing cAdvisor/Prometheus data keeps declared sizing and shows a telemetry
  warning only.

### P1.2.1 — optimize cAdvisor after rollout

cAdvisor is useful for topology sizing, but the current TrueNAS deployment is
resource-heavy enough that its own CPU/RAM cost must be treated as an explicit
follow-up rather than accepted as observability overhead.

First establish a before/after baseline for cAdvisor itself (CPU, working-set
memory, scrape duration, exported series count and Prometheus sample volume).
Then tune one dimension at a time while preserving the four signals required by
the topology: CPU, working-set memory, network RX/TX and the Docker Compose
service label used for identity reconciliation.

Candidate tuning controls supported by cAdvisor include:

- keep dynamic housekeeping enabled and increase `--housekeeping_interval`
  from the very aggressive 1s default after validating the required freshness;
- retain a conservative `--global_housekeeping_interval` because container
  discovery uses kernel events and the global scan is primarily a fallback;
- use `--docker_only=true` on this Docker-only TrueNAS collector so unrelated
  raw cgroups are not monitored;
- prefer an explicit minimal metric allow-list (`--enable_metrics`) or disable
  unused metric families instead of collecting disk/perf/process/TCP detail
  that the topology does not consume;
- consider `--store_container_labels=false` plus a reviewed label allow-list,
  but **only** if the Docker Compose service label needed for reconciliation is
  still exported;
- review cAdvisor in-memory history (`--storage_duration`) and Prometheus scrape
  interval together so local retention and scrape frequency are not much finer
  than the operator UI needs;
- apply container CPU/memory limits only after observing normal peaks, so a
  resource limit does not silently create a telemetry blind spot.

Any increase in collection/scrape interval must be reflected in PromQL rate
windows (the current `[2m]` examples must still contain enough samples).
Optimization is accepted only when cAdvisor resource consumption and metric
cardinality materially fall **without losing** the topology CPU/RAM/RX/TX
series or their Compose-service identity labels.

## P1.3 — bandwidth-aware relation width

Do **not** use aggregate firewall throughput to resize every topology edge.
An edge may only be widened when traffic is attributed to that exact
`source -> target` relationship.

### Existing validated flow path

The canonical architecture already is:

```text
PF state table
  -> pfSense Plus pflow/IPFIX v10
     -> TrueNAS 172.17.0.24:2055/udp
        -> Akvorado Inlet
        -> Kafka
        -> Akvorado Outlet
        -> ClickHouse database akvorado
```

A second independent pfSense exporter sends IPFIX to Cloudflare Network Flow.
Keep it as corroborating external evidence; do not make the public topology
depend on Cloudflare flow analytics.

Existing recording rules already provide pipeline/global evidence:

```promql
nabla:network_flow:pfsense_packets_per_second
nabla:network_flow:pfsense_bytes_per_second
nabla:network_flow:pfsense_kafka_messages_per_second
nabla:network_flow:outlet_kafka_messages_per_second
nabla:network_flow:clickhouse_flows_per_second
nabla:network_flow:clickhouse_batches_per_second
```

These metrics prove flow-pipeline throughput but **not per-topology-edge
attribution**.

### Required attribution step

Add a read-only bounded Akvorado/ClickHouse aggregation which maps recent flow
records to canonical topology identities using reviewed address/interface/
Docker-network metadata. This reconciliation layer is required before the UI can
claim a service-to-service bandwidth relationship. Target output should be
sanitized and cardinality-bounded:

```json
{
  "source": "pfsense",
  "target": "truenas",
  "bytesPerSecond": 123456.0,
  "packetsPerSecond": 123.0,
  "windowSeconds": 120,
  "observedAt": "..."
}
```

For Docker east-west traffic, cAdvisor can provide per-container totals but not
a trustworthy pairwise `service A -> service B` matrix. Do not infer pairwise
flow from total RX/TX. If pairwise Docker traffic is required later, collect it
from a source that preserves endpoints and can be reconciled with canonical
Docker network/IP metadata. In other words, cAdvisor is sufficient for node
CPU/RAM and total container traffic, while the **Bandwidth per-edge** feature
requires the small Akvorado/ClickHouse attribution aggregator that reconciles
observed IPs/interfaces with canonical topology identities.

Presentation rules:

- default relation width remains declarative;
- bandwidth mode only scales edges with exact attributed evidence;
- use log/square-root or percentile-clipped scaling to avoid one WAN-heavy edge
  flattening the rest of the graph;
- show `bytes/s`, packets/s, observation window and source in edge details;
- stale/missing flow evidence keeps the original width;
- never expose raw client IPs, Internet peers, ports, AS paths or per-user flow
  history from the public FastAPI topology page.

## Network probe decision

### pfSense

No additional packet/flow probe is required now.

pfSense Plus already exports native Packet Flow Data via `pflow(4)` / IPFIX.
This is preferable to reinstalling `softflowd` or running `ntopng` on the
memory-constrained Netgate 1100. The validated steady state remains:

```text
pflow/IPFIX   enabled
Akvorado      on TrueNAS
softflowd     disabled
ntopng        disabled on pfSense
```

### Akvorado

Akvorado is the correct routed-flow source. It accepts NetFlow/IPFIX/sFlow,
enriches flow records and persists them to ClickHouse. Its optional SNMP
enrichment can provide interface names/metadata; SNMP is metadata enrichment,
not a replacement packet collector.

### Supplemental sources only when justified

- TrueNAS node-exporter interface counters: useful for host/interface throughput
  corroboration, not service-to-service attribution.
- cAdvisor container network counters: useful per container, not pairwise edges.
- SNMP interface metadata: useful to improve Akvorado interface naming/speed
  context if pfSense SNMP access is deliberately enabled and least-privilege.

Do not add another high-cardinality collector merely to make the graph animate.

## Public API / privacy boundary

The FastAPI topology endpoint should expose only sanitized aggregates required
for rendering:

- node CPU cores / RAM working set / RX+TX bytes per second;
- exact attributed relation bytes/s and packets/s;
- observation timestamp/window/source;
- telemetry availability/freshness.

Do not expose:

- raw Akvorado flow rows;
- internal client inventories beyond already-public topology identifiers;
- external peer IP addresses;
- ports, AS paths or per-user traffic history;
- Cloudflare/API/Prometheus credentials.

Cache resource/flow aggregation for at least 15 seconds and keep all provider
queries server-side.

## Acceptance

- [ ] Shape semantics are visible without selecting a node.
- [ ] Docker can be hidden without hiding the services hosted by Docker.
- [ ] Lifecycle grouping preserves dependency edges and selection.
- [ ] Docker network grouping uses canonical exported Compose networks and does
  not silently discard secondary memberships.
- [ ] CPU/RAM mode changes node size only when fresh cAdvisor data exists.
- [ ] Resource values remain inspectable numerically; size is never the only
  representation.
- [ ] cAdvisor resource usage/cardinality is baselined and reduced after rollout
  while CPU/RAM/RX/TX + Compose-service identity remain available.
- [ ] Bandwidth mode changes only edges with exact source/target attribution.
- [ ] Akvorado pipeline blind spots are warnings, not firewall/service outages.
- [ ] Public topology never returns raw flow records or sensitive peer data.
- [ ] Additional pfSense collectors are not introduced unless the native
  pflow/Akvorado path is proven insufficient for a specific missing signal.
