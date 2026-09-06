# Homelab health observability

## Objective

The homelab exists to provide a controlled platform for experimenting with,
measuring and improving security. The observable end result is therefore the
**services and experiments delivered by the platform**, while the underlying
TrueNAS, Talos, Kubernetes, networking, storage, security and observability
components explain availability, blast radius and security posture.

Use two independent evidence paths:

1. direct control-plane/API checks for current state and incident diagnosis;
2. Prometheus -> Mimir -> Grafana for trends, capacity, alerting and history.

A Prometheus outage must not prevent direct verification of TrueNAS, Talos,
etcd or Kubernetes health.

## Current baseline — 2026-09-06

The base cluster is no longer only planned. The current repository/runtime
baseline is:

- TrueNAS hosts the platform and the existing observability stack;
- Talos Linux is pinned to v1.13.9;
- control-plane: `172.17.0.50`;
- workers: `172.17.0.51`, `172.17.0.52`;
- all three Kubernetes nodes were validated `Ready`;
- flannel reported `NetworkUnavailable=False`;
- worker kubelets were validated healthy;
- the current single-control-plane topology has one expected healthy etcd member;
- `scripts/talos/validate-cluster.sh` is the read-only direct health gate;
- Prometheus remote-writes to the existing Mimir stack;
- Grafana remains the operator dashboard surface.

Do not deploy a second Grafana, Mimir, Alertmanager or long-term Prometheus
stack for Kubernetes.

## Health semantics

Keep these concepts separate:

- **service outcome**: can the actual service/experiment do its job?
- **platform health**: are shared foundations operating correctly?
- **criticality**: how urgently does the component's own failure matter?
- **dependency impact**: which services are actually blocked by it?
- **security posture**: is the system configured and behaving according to the
  intended security policy?
- **telemetry health**: are monitoring/metrics sources fresh and trustworthy?

A telemetry backend outage should produce `telemetry_unavailable`; it must not
silently transform a healthy service into a failed service.

## Service-first observability model

### Services and experiments

These are the finality of the homelab. Prefer user/service-facing signals:

- functional availability;
- successful/failed request or job rate;
- latency percentiles where traffic is sufficient;
- traffic/throughput;
- service-specific saturation;
- later, SLO compliance and error-budget burn.

CPU/RAM alone are not service health.

### Critical core platform

Core components explain shared failure domains. Important examples include:

- TrueNAS;
- pfSense/network edge;
- Docker/container runtime;
- Talos;
- Kubernetes API/control-plane;
- etcd;
- CNI/DNS/ingress;
- CSI/storage once deployed.

For these components, capacity and pressure are valid first-class signals.

### Security controls

Security tooling needs two independent states:

1. **control health** — is the IDS/IPS/WAF/SIEM/agent running and fresh?
2. **security posture** — policy drift, exposure violations, stale feeds,
   detections, blocks, configuration exceptions.

A high detection count is not service downtime.

### Observability and support

Prometheus, Mimir, Grafana, exporters and collectors can be operationally
important without being functional dependencies of every monitored service.

## TrueNAS host metrics

The existing TrueNAS-hosted Prometheus now scrapes:

- itself: `job="prometheus"`;
- TrueNAS node-exporter: `job="truenas_node"`, target `172.17.0.24:9100`;
- TrueNAS cAdvisor: `job="truenas_cadvisor"`, target `172.17.0.24:8089`.

Initial TrueNAS alerts cover:

- node-exporter unavailable for 2 minutes — **warning / telemetry blind spot**;
- cAdvisor unavailable for 2 minutes — **warning / telemetry blind spot**;
- less than 10% host memory available for 5 minutes — warning platform pressure;
- less than 5% host memory available for 2 minutes — **critical platform pressure**;
- less than 15% writable filesystem capacity available for 15 minutes — warning;
- less than 5% writable filesystem capacity available for 5 minutes — **critical**.

Exporter/collector loss is deliberately not a critical TrueNAS outage signal.
Direct platform/service checks remain authoritative for current availability.
Critical alerts are reserved for actual platform pressure/capacity symptoms.

Stable recording rules provide a bounded backend contract for future UI/API
consumers:

```promql
nabla:core:truenas_memory_available_ratio
nabla:core:truenas_cpu_busy_ratio
nabla:telemetry:truenas_node_up
nabla:telemetry:truenas_cadvisor_up
nabla:telemetry:pfsense_metrics_up
nabla:observability:prometheus_up
```

The `nabla:telemetry:*` series describe evidence coverage, not the health of
the observed platform. A missing exporter must render as **telemetry
unavailable / blind spot**, not as TrueNAS or pfSense down.

Filesystem/ZFS capacity is intentionally not collapsed into one stable
recording rule yet. First inspect the actual TrueNAS filesystem/ZFS label set
so an irrelevant mount cannot become the fleet-wide minimum by accident.

### Runtime acceptance

After deployment, validate:

```promql
up{job="prometheus"}
up{job="truenas_node"}
up{job="truenas_cadvisor"}
```

Then inspect the actual ZFS/filesystem label set before relying on capacity
alerts for notification routing.

Do not assume every node-exporter filesystem series maps one-to-one to a ZFS
dataset until verified on the deployed TrueNAS host.

## Direct Talos/Kubernetes gate

`scripts/talos/validate-cluster.sh` is the independent direct path. It is
read-only and now checks:

- Talos API/version on the control-plane and workers;
- kubelet `Running` / `OK` on the control-plane and both workers;
- etcd service `Running` / `OK`;
- `talosctl etcd status` succeeds;
- Talos `/var` usage telemetry is readable on every node;
- Kubernetes `/readyz` succeeds;
- expected Kubernetes node count is 3;
- all expected nodes are `Ready`;
- no node reports `DiskPressure=True`;
- no node reports `MemoryPressure=True`;
- no node reports `PIDPressure=True`;
- no node reports `NetworkUnavailable=True`;
- the current topology contains exactly one etcd member.

The gate deliberately performs no apply, reboot, drain, defrag, repair,
bootstrap or machine-config mutation.

## Disk and EPHEMERAL capacity

Talos `/var` lives on EPHEMERAL storage and is particularly relevant because it
contains runtime state such as logs/images/containers and etcd data on the
control-plane.

The direct gate currently verifies that `talosctl usage /var -H` is readable
and relies on Kubernetes `DiskPressure` for a coarse failure signal.

That is not sufficient for capacity planning. Add historical free-space metrics
before considering this item complete.

Target outcomes:

- bytes/percent available for each Talos node EPHEMERAL volume;
- warning and critical thresholds;
- growth trend;
- time-to-exhaustion when meaningful;
- explicit control-plane/etcd disk pressure attribution.

## etcd

Direct evidence remains authoritative:

```bash
talosctl --nodes 172.17.0.50 etcd members
talosctl --nodes 172.17.0.50 etcd status
talosctl --nodes 172.17.0.50 etcd alarm list
```

For the current single-control-plane cluster, loss of the sole etcd member is a
critical control-plane failure.

Future metrics should cover:

- `etcd_server_has_leader`;
- unexpected leader changes;
- failed proposals;
- database total/in-use size;
- backend quota pressure;
- WAL/fsync latency;
- peer RTT if the control-plane becomes multi-node.

Talos can expose etcd metrics on TCP/2381. Do not broadly expose this endpoint.
Only enable it together with a reviewed Talos ingress rule restricted to the
monitoring source.

Keep direct `talosctl` checks even after Prometheus scraping exists.

## Kubernetes metrics

Preferred staged implementation:

1. keep the direct `validate-cluster.sh` gate;
2. deploy metrics-server for Kubernetes Resource Metrics / `kubectl top`;
3. deploy kube-state-metrics for object/state metrics;
4. collect authenticated kubelet/resource metrics;
5. expose etcd metrics only to the monitoring source;
6. send historical metrics into the existing Prometheus/Mimir/Grafana path.

The preferred architecture is for the existing TrueNAS Prometheus to scrape the
cluster using a dedicated least-privilege service account and trusted CA.

If external discovery/routing proves unnecessarily fragile, use an in-cluster
**collector-only** Prometheus or Alloy with short/no local retention and
remote-write to the existing Mimir. Do not create another long-term monitoring
stack.

Useful Kubernetes alerts include:

- API readiness failure;
- expected node count mismatch;
- node not `Ready`;
- `DiskPressure`, `MemoryPressure`, `PIDPressure`;
- kube-system workload unavailable;
- excessive restart/crash-loop rate;
- PVC stuck `Pending`;
- storage/CNI/DNS failures.

## FastAPI Sample aggregation

The TrueNAS-local FastAPI Sample instance is the intended LAN-side aggregator.

It can combine:

- sanitized TrueNAS JSON-RPC evidence;
- direct Talos health;
- Kubernetes API state;
- selected Prometheus instant queries.

Do not give FastAPI Cloud public access to Prometheus, the Kubernetes API,
Talos API or the TrueNAS management API merely to populate the health board.

Target flow:

```text
TrueNAS / Talos / Kubernetes APIs
             |
             +---- direct evidence
             |
Prometheus --+
             v
local FastAPI Sample
             |
             +---- sanitized bounded health model
             v
service-first health board / protected relay
```

Prometheus queries used by FastAPI Sample must be:

- fixed server-side queries;
- low-cardinality;
- bounded;
- protected by short timeouts;
- cached for a short TTL;
- attributed to a freshness/source timestamp.

Never expose an arbitrary PromQL proxy in the public API.

Application-side work is tracked in
`AlbanAndrieu/fastapi-sample#195`; the service-first presentation is developed
in `AlbanAndrieu/fastapi-sample#196`.

## Hardening follow-ups

### P0 — validate TrueNAS metrics

- [ ] deploy the Prometheus changes;
- [ ] verify `up{job="truenas_node"} == 1`;
- [ ] verify `up{job="truenas_cadvisor"} == 1`;
- [ ] inspect ZFS/filesystem labels;
- [ ] validate warning/critical filesystem expressions against real series;
- [ ] configure a real Alertmanager receiver before relying on notification delivery.

### P1 — harden metric endpoints

No other repository consumer currently requires host ports 9100 or 8089.

After runtime acceptance:

- [ ] confirm no external operational consumer depends on them;
- [ ] move node-exporter/cAdvisor behind a private monitoring network where practical;
- [ ] scrape by service DNS instead of publishing metric endpoints broadly on the host;
- [ ] evaluate migration of cAdvisor from the legacy GCR image location separately.

### P2 — extend direct Talos health

- [x] validate control-plane/worker kubelets;
- [x] validate Kubernetes API readiness;
- [x] validate node Ready count;
- [x] reject Kubernetes node pressure;
- [x] validate current etcd membership/status;
- [ ] validate etcd alarms without brittle human-table parsing;
- [ ] add explicit quantitative EPHEMERAL free-space thresholds;
- [ ] validate Kubernetes DNS and pod-to-pod / pod-to-service networking;
- [ ] validate storage once democratic-csi is introduced.

### P3 — Kubernetes/etcd metrics

- [ ] deploy metrics-server;
- [ ] deploy kube-state-metrics;
- [ ] define least-privilege Prometheus RBAC;
- [ ] collect kubelet/resource metrics;
- [ ] securely expose etcd 2381 metrics;
- [ ] add Grafana views backed by Mimir.

### P4 — service-first health board metrics

- [x] establish stable initial TrueNAS/pfSense/telemetry recording names under
      `nabla:core:*`, `nabla:telemetry:*` and
      `nabla:observability:*`;
- [ ] service outcome metrics: availability/errors/latency/traffic;
- [ ] core metrics: capacity/pressure/component state, adding Kubernetes/etcd
      after their authenticated scrape paths exist;
- [ ] security-control health separate from security posture;
- [ ] retain evidence provenance and freshness in the UI;
- [ ] ensure telemetry failures never overwrite direct service health;
- [ ] expose only fixed/bounded server-side metric queries to the health UI,
      never an arbitrary PromQL proxy.

## References

- Talos v1.13 CLI: https://docs.siderolabs.com/talos/v1.13/reference/cli
- Talos etcd maintenance: https://docs.siderolabs.com/talos/v1.13/build-and-extend-talos/cluster-operations-and-maintenance/etcd-maintenance
- Talos etcd metrics: https://docs.siderolabs.com/kubernetes-guides/monitoring-and-observability/etcd-metrics
- Talos storage resources: https://docs.siderolabs.com/talos/v1.13/configure-your-talos-cluster/storage-and-disk-management/disk-management/resources
- Kubernetes node metrics: https://kubernetes.io/docs/reference/instrumentation/node-metrics/
- TrueNAS 26 API: https://api.truenas.com/v26.0/
