# Kubernetes security policy and Headlamp roadmap

Last updated: 2026-09-10.

This roadmap is intentionally sequenced around the current TrueNAS CSI
acceptance gate. Do not introduce a second admission-policy engine while
storage provisioning/reclaim is still being validated.

Useful external reference:

- Stéphane Robert — Kubernetes hardening, RBAC, Network Policies and CKS:
  <https://blog.stephane-robert.info/docs/securiser/kubernetes/>

## Security objective — Zero Trust / Security First

The target is the **most restrictive security posture that remains functional**.
Normal application workloads should converge on the Kubernetes Pod Security
Standards **Restricted** profile, not merely Baseline. Any workload that cannot
run under Restricted must have a narrowly scoped, documented and tested
exception.

Security invariants:

- default-deny before allow-by-exception;
- least privilege for human, workload and automation identities;
- `Restricted` PSS for application namespaces wherever technically possible;
- `Baseline` is an intermediate compatibility floor, not the long-term target;
- `Privileged` is reserved for documented node-level infrastructure such as
  CSI/CNI/runtime-security components that genuinely require it;
- every privileged namespace is a security boundary and must have tightly
  constrained RBAC;
- ServiceAccount tokens are not mounted unless the workload actually calls the
  Kubernetes API;
- network paths, image provenance, secrets, admission policy and runtime
  behaviour are all verified independently; a green layer must not mask a weak
  adjacent layer.

## Current security baseline

- Talos v1.13.9 / Kubernetes v1.36.3 is the current cluster baseline.
- Talos enables Kubernetes Pod Security Admission by default.
- The Talos default is `enforce=baseline`, `audit=restricted`,
  `warn=restricted`, with `kube-system` exempted.
- `truenas-csi` needs a namespace-scoped `enforce=privileged` policy because
  the CSI node plugin requires `hostNetwork`, kubelet `hostPath` mounts,
  mount propagation and a privileged/root mount helper.
- Keep application namespaces at baseline or stricter; do not create a
  cluster-wide privileged exception for CSI.
- The long-term target is to move normal application namespaces from inherited
  Talos `baseline` enforcement to explicit `restricted` enforcement after
  server-side dry-run and runtime compatibility evidence are green.

## P0/P1 — continuously verify PSA/PSS

- [x] Add `scripts/talos/diagnose-security-posture.sh` to execute the effective
  Talos admission-control query, including:

  ```bash
  talosctl -n 172.17.0.50 \
    get admissioncontrolconfigs.kubernetes.talos.dev \
    admission-control \
    -o yaml
  ```

  It reports namespace PSA labels, inherited namespaces and explicit
  `privileged` overrides, accepts `restricted` as stronger than `baseline`, and
  fails if the cluster default becomes weaker than the Talos baseline posture.
- [x] Include the PSA/PSS posture check in
  `scripts/talos/validate-cluster.sh`.
- [x] Add `scripts/truenas/diagnose-platform.sh` as the standard TrueNAS
  platform diagnostic aggregator: TrueNAS app lifecycle + Talos/Kubernetes +
  PSA/PSS posture.
- [ ] Add a CI/static contract for intended namespace posture. At minimum:
  - normal application namespaces must not use `enforce=privileged`;
  - `truenas-csi` is an explicitly justified privileged infrastructure
    namespace;
  - policy versions are pinned/reviewed during Kubernetes minor upgrades;
  - target application namespaces are `Restricted` once compatibility is
    proven.
- [ ] Use server-side dry-run for representative manifests where cluster access
  is available so admission behaviour is tested, not inferred only from YAML.
- [ ] Preserve Pod Security rejection evidence in diagnostics (`FailedCreate`,
  policy level and violating fields) so rollout timeouts are not mistaken for
  scheduling or image-pull failures.
- [ ] Inventory every namespace that does not satisfy `Restricted`, classify the
  exact control preventing migration, and remediate before adding an exception.
- [ ] Review Talos minor upgrades against PSS version changes before changing
  `*-version` labels.

## P1 — harden Talos and Kubernetes control plane

Keep Talos defaults that already provide a strong immutable/minimal platform,
then continuously prove rather than assume them:

- [ ] audit Kubernetes API anonymous access, authorization modes and audit-log
  configuration against current Talos defaults;
- [ ] verify Kubernetes Secret encryption-at-rest and etcd mTLS remain enabled;
- [ ] verify kubelet certificate authentication/rotation and default seccomp;
- [ ] inventory cluster-admin bindings and remove human/service identities that
  do not require them;
- [ ] separate operator, CI/CD, observer and application ServiceAccounts;
- [ ] disable unnecessary ServiceAccount token automounting;
- [ ] add CIS/Kubernetes posture checks with **Kubescape** and/or kube-bench
  where they are compatible with Talos' immutable architecture; interpret
  findings against Talos-specific defaults rather than blindly applying Linux
  host remediation intended for mutable distributions;
- [ ] add Trivy/KICS/Checkov-style IaC and manifest scanning to CI where not
  already covered;
- [ ] consider Kubernetes audit-event forwarding into the existing
  Graylog/Wazuh observability path.

## P1 — evaluate Kyverno vs Gatekeeper

Do **not** deploy both policy engines by default. Select one after a bounded
proof-of-concept and keep built-in PSA/PSS as the coarse first security layer.

Preferred evaluation order: **Kyverno first**, then Gatekeeper as the OPA/Rego
alternative.

- [ ] Evaluate **Kyverno** for Kubernetes-native YAML policies, mutation,
  generation, image verification and PolicyReports.
- [ ] Evaluate **OPA Gatekeeper** for Rego/OPA-based policy reuse,
  ConstraintTemplates/Constraints and environments already standardizing on
  OPA.
- [ ] Compare operational cost on this 3-node homelab:
  - controller/webhook footprint and availability;
  - admission latency and failure-policy behaviour;
  - audit/reporting quality;
  - GitOps/CI testability;
  - policy exception ergonomics;
  - Prometheus metrics and alerting;
  - upgrade/rollback complexity.
- [ ] Start candidates in audit/report-only mode before enforcing new policy.
- [ ] Initial candidate policies after evaluation:
  - prohibit `latest`/floating images for production workloads;
  - require immutable image digests for critical workloads;
  - require resource requests/limits for long-running services;
  - require `runAsNonRoot`, `allowPrivilegeEscalation=false`, seccomp
    `RuntimeDefault` and capability drop `ALL` where compatible;
  - reject unnecessary ServiceAccount token automounting;
  - restrict `hostPath`, `hostNetwork`, host PID/IPC, privileged containers and
    dangerous capabilities to documented infrastructure namespaces;
  - require explicit ownership/environment metadata used by the homelab
    topology catalogue;
  - require NetworkPolicy after enforcement is validated;
  - evaluate Sigstore/Cosign signature and provenance verification before
    enforcing image admission.
- [ ] Keep escape hatches narrow, named and reviewable; every privileged
  exception must carry a workload/namespace justification and regression test.

## P1 — network Zero Trust and runtime detection

Falco is valuable, but it is primarily **runtime threat detection**, not a
NetworkPolicy engine. Treat the layers separately.

- [ ] First make Kubernetes `NetworkPolicy` enforcement real on the current
  Talos/Flannel cluster and prove it with positive and negative connectivity
  tests before applying default-deny policies broadly.
- [ ] Introduce namespace/workload default-deny ingress and egress policies,
  then explicitly allow DNS, ingress-controller, observability and required
  service-to-service flows.
- [ ] Decide whether the current Flannel NetworkPolicy capability is sufficient
  or whether a later CNI migration to **Cilium** is justified for
  identity-aware/L7 policy and stronger flow observability. Do not change CNI
  during the active CSI acceptance gate.
- [ ] If Cilium is evaluated, evaluate **Hubble** for network-flow visibility
  and **Tetragon** for eBPF runtime observability/enforcement.
- [ ] Evaluate **Falco** after the base policy layers are stable for runtime
  detection of suspicious syscalls/container behaviour. Forward high-signal
  events into the existing security observability/SIEM path.
- [ ] Compare Falco and Tetragon roles rather than treating them as identical:
  Falco is a portable runtime detection layer; Tetragon is tightly integrated
  with eBPF/Cilium and can also enforce selected kernel events.
- [ ] Evaluate whether NeuVector adds enough container/runtime/network security
  value beyond PSA + chosen admission policy engine + NetworkPolicy +
  Falco/Tetragon before adding its operational footprint.
- [ ] Add network-policy regression tests so a policy change cannot silently
  break DNS, TrueNAS NFS, ingress, Prometheus scraping or control-plane paths.

## P1 — supply-chain and workload hardening

- [ ] Pin production/critical images by digest while retaining human-readable
  version metadata.
- [ ] Produce and retain SBOMs; scan images and dependencies with Trivy/Grype or
  the existing project scanners.
- [ ] Sign critical images with Sigstore/Cosign and evaluate admission-time
  verification through the selected policy engine.
- [ ] Keep root filesystems read-only where possible and provide explicit
  `emptyDir`/PVC writable paths only where needed.
- [ ] Require non-root UID/GID, `seccompProfile: RuntimeDefault`, capability
  drop `ALL`, no privilege escalation and no host namespaces for normal apps.
- [ ] Prefer short-lived/workload identities and External Secrets/Vault/OpenBao
  over long-lived Kubernetes Secret material where practical.

## P1 — FastAPI generic-service Restricted profile

Coordinate with `AlbanAndrieu/fastapi-sample/charts/generic-service`:

- [ ] render successfully under **PSS Restricted** by default;
- [ ] default `automountServiceAccountToken` to false;
- [ ] explicitly disable host networking/PID/IPC for normal workloads;
- [ ] retain non-root execution, RuntimeDefault seccomp,
  `allowPrivilegeEscalation=false`, read-only root filesystem and `drop: ALL`;
- [ ] add an optional namespace PSA template/profile with
  `enforce/audit/warn=restricted` for deployments where the chart owns the
  namespace lifecycle;
- [ ] add configurable NetworkPolicy support with default-deny semantics and
  explicit DNS/ingress/application egress allows;
- [ ] add Helm rendering/CI tests that fail if the default chart drifts away
  from the Restricted contract;
- [ ] test with `kubectl apply --dry-run=server` against the Talos cluster before
  declaring the deployment profile compatible;
- [ ] document justified exceptions separately rather than weakening the generic
  defaults.

## P1 — Headlamp operator UX

### Workstation first

- [ ] Install Headlamp Desktop on the workstation and use the existing trusted
  kubeconfig; do not create a new cluster-admin credential merely for Headlamp.
- [ ] Validate that Headlamp can see the Talos cluster, namespaces, workloads,
  events, DaemonSets, CSI resources and owner relationships using the same RBAC
  identity as `kubectl`.
- [ ] Use Headlamp during CSI acceptance to visualize:
  `StorageClass -> PVC -> PV -> CSIDriver/CSINode`, Pod placement and events.

### In-cluster service after CSI

- [ ] Add Headlamp to `nabla-compose` as a **Kubernetes service**, not a
  TrueNAS/Docker-socket application. Prefer the upstream Helm chart with a
  repository-owned pinned chart/app version and reviewed values.
- [ ] Deploy in a dedicated `headlamp` namespace rather than broadening
  `kube-system` for the homelab UI.
- [ ] Give the Headlamp runtime ServiceAccount no unnecessary cluster-wide
  privileges; user actions must be authorized through explicit user/OIDC RBAC.
- [ ] Prefer OIDC for shared in-cluster access when the identity gate is ready;
  do not publish a static cluster-admin bearer token.
- [ ] Initially expose only through `kubectl port-forward` or internal ingress.
  If later exposed through an ingress/tunnel, require TLS, authentication and
  the same internal/external exposure policy used by other administrative UIs.
- [ ] Add `x-nabla`/topology metadata so Headlamp appears as an observability /
  Kubernetes-operations service in the homelab catalogue.
- [ ] Add readiness/health probing without granting the health observer write
  access to the Kubernetes API.
- [ ] Add backup/rollback documentation and prove that removing Headlamp does
  not affect cluster workloads, CSI, CNI or admission policy.

## Zero Trust implementation order

Implement the security layers in this order so later controls do not hide gaps
in earlier ones:

1. **Platform trust root** — Talos immutable/minimal OS, Kubernetes/etcd PKI,
   encryption-at-rest, API audit and upgrade discipline.
2. **Identity + RBAC** — least privilege, distinct human/automation/workload
   identities, no unnecessary cluster-admin, ServiceAccount tokens off by
   default.
3. **PSS/PSA** — target `Restricted` for normal namespaces; keep narrowly
   justified privileged infrastructure namespaces only where required.
4. **Network default-deny** — real NetworkPolicy enforcement plus tested DNS,
   ingress, storage and observability allows.
5. **Secrets/workload identity** — Vault/OpenBao/External Secrets and rotation;
   minimize static Kubernetes secrets.
6. **Policy-as-code** — Kyverno first candidate, Gatekeeper alternative; begin
   in audit then enforce high-confidence controls.
7. **Supply chain** — SBOM, vulnerability scanning, digest pinning, signing and
   admission-time provenance verification.
8. **Runtime detection/enforcement** — Falco and, if Cilium is adopted,
   Hubble/Tetragon; route detections into SIEM/observability.
9. **Operator UX and continuous assurance** — Headlamp, Kubescape/CIS checks,
   Prometheus/Grafana/Wazuh/Graylog evidence and recurring regression tests.

## Acceptance order

1. finish TrueNAS CSI node/controller readiness;
2. create the non-default `nabla-truenas-nfs` StorageClass;
3. prove dynamic PVC, cross-worker persistence and TrueNAS reclaim;
4. install/use Headlamp Desktop on the workstation;
5. inventory PSA/PSS posture and privileged namespace exceptions;
6. make one representative application namespace `Restricted` and prove it;
7. enable/test default-deny NetworkPolicy on one representative application;
8. evaluate Kyverno versus Gatekeeper in audit/report-only mode;
9. select at most one policy engine for initial enforcement;
10. evaluate Falco/runtime detection, then Cilium/Hubble/Tetragon only if the
    additional network/runtime capabilities justify a CNI change;
11. deploy Headlamp in-cluster with least-privilege RBAC/OIDC only after the
    Kubernetes storage/security foundations are stable.
