# Homelab roadmap

Last updated: 2026-09-08.

This is the concise operational index. Detailed design, evidence and rollback
notes remain in the specialized roadmaps:

- [Homelab platform migration roadmap](./homelab-platform-migration-roadmap.md)
- [Secrets migration roadmap](./secrets-migration-roadmap.md)
- [pfSense WAN exposure roadmap](./pfsense-wan-exposure-roadmap.md)
- [Kubernetes FastAPI Sample smoke](./kubernetes-fastapi-smoke.md)
- [Kubernetes CSI preflight](./kubernetes-csi-preflight.md)

## Current platform state

- [x] Talos control plane and both workers are Kubernetes `Ready`.
- [x] kubelet/flannel are healthy and the single-control-plane etcd member is healthy.
- [x] `scripts/talos/validate-cluster.sh` provides the read-only base-cluster gate.
- [x] FastAPI Sample uses the repository-owned `sample-observer` bridge.
- [x] TrueNAS observer source is pinned to `10.254.255.9/32`.
- [x] persisted and active TrueNAS `ui_allowlist` values converge after UI restart/reconciliation.
- [x] authenticated TrueNAS WebSocket `system.version` and `app.query` succeed with TLS verification enabled.
- [x] PR #144 fixed allowlist activation so persisted state is never treated as sufficient by itself.

## P0 — Kubernetes DNS/CNI + FastAPI Sample acceptance

Do not start CSI installation until all items below are green.

Current live blocker (2026-09-08): the workstation currently receives
`no route to host` while connecting to the Talos API at
`172.17.0.50:50000`. The cluster was previously validated Ready, so treat this
as a reachability/runtime regression first. The Talos VMs are intentionally
declared with `autostart=false`; verify VM power state, `br0` attachment,
neighbor resolution and TCP/50000 before changing Talos machine configuration.

- [ ] restore and prove workstation reachability to Talos API TCP/50000 on `.50`, `.51` and `.52`;
- [ ] run `scripts/talos/validate-cluster.sh` immediately before the network smoke;
- [ ] run `scripts/talos/smoke-kubernetes-network.sh`;
- [ ] prove CoreDNS resolution for `kubernetes.default.svc.cluster.local`;
- [ ] prove disposable Service DNS and ClusterIP routing;
- [ ] prove cross-node pod routing between workers `172.17.0.51` and `172.17.0.52`;
- [ ] run `scripts/talos/smoke-fastapi-sample.sh --preflight`;
- [ ] prove the selected Kubernetes IngressClass exists;
- [ ] prove `test.albandrieu.com` resolves before deployment;
- [ ] deploy FastAPI Sample from an immutable `@sha256:` image;
- [ ] prove Deployment rollout and ready Service endpoints;
- [ ] prove external `https://test.albandrieu.com/health`;
- [ ] prove external `https://test.albandrieu.com/v2/version`;
- [ ] retain Pod/Node/PodIP/Service/Ingress correlation evidence;
- [ ] clean up/recreate the smoke workload without affecting `sample.albandrieu.com`.

## Parallel diagnostic — Sentry lifecycle

Functional Sentry health and TrueNAS lifecycle state are separate gates.

- [ ] diagnose why TrueNAS still reports Sentry `DEPLOYING`;
- [ ] inventory every Sentry container state, restart count and health;
- [ ] distinguish one-shot migration containers from required steady-state services;
- [ ] inspect the TrueNAS Custom App job/state reason instead of inferring failure from the aggregate label;
- [ ] preserve the already-proven synthetic event ingestion path while fixing lifecycle convergence.

This diagnostic must not delay P0 Kubernetes networking unless it reveals a
shared TrueNAS resource failure.

## P0.1 — TrueNAS-backed Kubernetes CSI

Start only after the complete P0 network/ingress smoke is green.

- [ ] run the read-only CSI preflight;
- [ ] select/pin the reviewed CSI implementation;
- [ ] create a dedicated least-privilege TrueNAS CSI identity;
- [ ] provision storage below `cpool/k8s/csi`;
- [ ] create an explicit StorageClass;
- [ ] attach a disposable PVC to the FastAPI Sample smoke;
- [ ] prove data survives Pod recreation;
- [ ] prove reclaim/cleanup and at least one rollback path.

NFS remains the first persistence smoke path unless a separate architecture
review selects another transport.

## P1 — infrastructure secrets

After CSI persistence/rollback is proven:

1. OpenTofu/Terragrunt + Garage backend credentials;
2. dedicated TrueNAS automation credentials;
3. Nexus automation credentials;
4. Talos/Kubernetes/CSI credentials;
5. Vaultwarden-backed rendering into minimum root-owned `0600` runtime files;
6. retain git-crypt as encrypted recovery material;
7. move long-term machine secrets to Vault/OpenBao only after Kubernetes storage is proven.

## P2/P3 — core services and migrations

After the platform gates above:

1. Prometheus;
2. Grafana;
3. Graylog;
4. CrowdSec;
5. Scrutiny + standalone InfluxDB;
6. Langflow;
7. AutoKuma;
8. OpenRAG + Docling;
9. Wazuh / Akvorado / ntopng-Suricata reconciliation;
10. Pi-hole and remaining application cutovers.

## P4 — identity

Keycloak/GitHub SSO and Vault/OpenBao human authentication remain after the
network, storage and infrastructure-secret gates.
