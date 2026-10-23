# Migration Talos / Kubernetes / PHP / Python — 23 octobre 2026

**Status: code targets staged, live cluster and TrueNAS Apps NOT upgraded.**
No GitHub Actions, deployments, VM reboots, schema changes or billable cloud
calls were performed. The current declarative Talos pin *before this PR* was
`v1.13.9` and the last observed Kubernetes node version was `v1.36.3`.
The *running* versions must be independently observed before proceeding.

## Target selection — support instead of generic 'LTS'

| Component | Reviewed target | Support policy | Source |
|---|---|---|---|
| Talos | v1.14.4 (16 Oct 2026) | Two most recent Talos minor branches; never alpha/RC | https://github.com/siderolabs/talos/releases/tag/v1.14.4 |
| Kubernetes | v1.37.1 | Official release branches (no traditional LTS); three most recent supported | https://kubernetes.io/releases/ |
| PHP | 8.5 | Active support through Dec 2027, security through Dec 2029 | https://www.php.net/supported-versions.php |
| Python | 3.14.9 | Supported bugfix branch and patch-level security fix (21 Oct 2026); 3.15.1 is newer but requires broader compatibility | https://devguide.python.org/versions/ |

`config/talos/VERSION`, `config/talos/KUBERNETES_VERSION` and `mise.toml`
declare **targets**, never evidence that the cluster was upgraded.
`apps/dsomm/baseline/Dockerfile` now selects `python:3.14.9-slim-bookworm`
(official published image tag), but its full rebuild and dependent Python
wheels/packages must be tested in staging before deploying.

Run the *full* offline declaration inventory for **all** Compose Apps and
Dockerfiles. `unknown` means an upstream image controls its PHP/Python
runtime; an opaque image is not a pass, and `latest` is not LTS:

```bash
just upgrade-runtime-test
just upgrade-runtime-audit
python3 scripts/quality/audit-supported-runtimes.py --json > /tmp/nabla-runtime-audit.json
python3 scripts/quality/audit-supported-runtimes.py --strict-eol
```

Prioritize `eol`, then `security-only`, then `floating` and `unknown`,
against **runtime** digests from `docker inspect`. Do not mass-replace image
tags: application schemas, ABI dependencies and upstream support policies differ.

### Known PHP and Python caveats

- **WordPress**: the TrueNAS Compose definition uses
  `ntninja/wordpress-postgresql:latest` with PG4WP; this is not a
  maintained official WordPress image. Its embedded PHP version is unknown.
  Official WordPress images use MySQL/MariaDB and cannot be substituted
  without a DB/application migration. Keep the lab isolated until a
  maintained PHP 8.5-compatible driver and data migration have been tested.
- **OpenClaw tools**: `apps/openclaw/Dockerfile` installs OS-managed Python
  from Debian Bookworm. Changing the base and Python separately would break
  the distribution dependency contract; treat as a dedicated distro migration.
- **LiteLLM, Sentry, DefectDojo, Langflow, OpenRAG, Docling**: runtime lives
  inside a third-party image. Upgrade the **complete validated upstream
  release image** (with digest and schema checks), never `apt`/pip PHP or
  Python over the base container. LiteLLM Anthropic routing and cost limits
  remain a separate blocking gate.
- **Other Apps**: the offline inventory is exhaustive for declared
  `apps/*/compose.yml` and nested Dockerfiles, not proof of the running
  TrueNAS Apps state. Reconcile against `midclt call app.query` and the
  actual image digest per running container before scheduling each migration.

## Talos + Kubernetes: review and operator window

The three known Talos addresses are control-plane `172.17.0.50` and
workers `172.17.0.51`, `172.17.0.52`. The last recorded etcd
topology was a **single member**: the control-plane upgrade has an
unavoidable availability window, and preserving etcd state is critical.

Do **not** use `talosctl bootstrap`, `apply-config --insecure`, `reset`,
`reboot`, or regenerate cluster secrets for this upgrade.
Use workstation/operator `mise` and the current, known-good
`TALOSCONFIG` and `KUBECONFIG`.

### P0 — read-only prerequisites

```bash
cd ~/w/nabla-compose
git status --short
mise install 'aqua:siderolabs/talos'
mise exec -- talosctl version --client
mise exec -- bash scripts/talos/validate-cluster.sh
mise exec -- python3 scripts/talos/preflight-supported-upgrade.py --check
mise exec -- bash scripts/talos/smoke-truenas-csi-nfs.sh --check
mise exec -- kubectl get pods -A -o wide
mise exec -- kubectl get pvc,pv -A
mise exec -- kubectl get storageclass
```

Before the upgrade, record live versions, inventory Kubernetes add-ons,
CNI, democratic-csi version/permissions and node-drain feasibility. Check
that an **authoritative, encrypted** etcd snapshot is taken, retained
off-node, and its recovery procedure is rehearsed; for example (operator
approval required to write a backup file):

```bash
# Example only — choose protected destination and review talosctl help first.
mkdir -p ~/.local/share/nabla/talos-backups
chmod 700 ~/.local/share/nabla/talos-backups
mise exec -- talosctl --nodes 172.17.0.50 etcd snapshot \
  ~/.local/share/nabla/talos-backups/etcd-before-1.14.4.db
chmod 600 ~/.local/share/nabla/talos-backups/etcd-before-1.14.4.db
```

Snapshot presence alone does **not** prove recoverability; check checksum,
retention, off-host copy and decryption. TrueNAS VM and CSI dataset snapshots
are **additional**, not replacements for the etcd backup.

### P1 — Talos rolling OS upgrade (operator commands, not automated)

The `qemu-guest-agent` extension is declared in
`config/talos/image-factory.yaml`: a generic installer image may discard
extensions. Generate the version-matched Image Factory schematic and verify
the image/extension before proceeding:

```bash
mise exec -- bash scripts/talos/image-factory.sh
# Inspect TALOS_INSTALLER_IMAGE emitted by the script; verify it is
# v1.14.4 and resolves to the reviewed schematic/digest.
mise exec -- talosctl upgrade --help
```

During the approved maintenance window only, use the **verified installer
image** in place of `<IMAGE_FROM_REVIEWED_FACTORY>` and upgrade **one
worker at a time**:

```bash
# After recording the workload placement and ensuring drain/PDB safety:
mise exec -- kubectl drain <WORKER_NODE_NAME> --ignore-daemonsets --delete-emptydir-data
mise exec -- talosctl --nodes 172.17.0.51 upgrade \
  --image '<IMAGE_FROM_REVIEWED_FACTORY>'
mise exec -- kubectl uncordon <WORKER_NODE_NAME>
mise exec -- bash scripts/talos/validate-cluster.sh

# Repeat only after healthy recovery for worker 172.17.0.52.
```

Inspect the worker names from `kubectl get nodes -o wide`; the placeholder
is **not** a literal shell value. `--delete-emptydir-data` can delete
ephemeral workloads; review each Pod/PDB and skip the upgrade if this is
unsafe. Never add `--force` to Talos upgrades. Finally, after workers
recover, upgrade the single control-plane (172.17.0.50) in a **separate,
explicitly approved downtime window** with verified rollback and etcd
snapshot available. Validate API/etcd and restored reachability before K8s.

### P2 — Kubernetes 1.37.1 (after all Talos nodes are ready)

```bash
mise exec -- talosctl upgrade-k8s --help
mise exec -- talosctl --nodes 172.17.0.50 upgrade-k8s \
  --to 1.37.1 --dry-run
# ONLY after verifying the displayed plan and the upgrade window:
# mise exec -- talosctl --nodes 172.17.0.50 upgrade-k8s --to 1.37.1

mise exec -- bash scripts/talos/validate-cluster.sh
mise exec -- bash scripts/talos/smoke-truenas-csi-nfs.sh --check
```

If any node remains NotReady, etcd fails, CSI/PVCs cannot mount, or
ingress/health endpoints regress, **stop**. Compare to the captured baseline
before attempting a rollback. Talos `rollback` and Kubernetes downgrade
are not interchangeable: do not attempt unsupervised Kubernetes downgrade
or recreate the cluster. Document steps and outcome in the migration report.

### P3 — Python/PHP service waves, not a bulk restart

1. Inventory read-only first and group services by database and upstream
   version. Check PHP/Python release support, OCI digest, vulnerability
   scan, SBOM and the specific app's migration guide.
2. Rebuild **DSOMM baseline** on Python 3.14.9, validate dependencies and
   package hashes locally. Do not publish or restart before smoke acceptance.
3. Test one low-criticality image at a time in isolation; verify health,
   ingress, persistence, backup restore and service labels.
4. For shared stateful dependencies (Postgres, Sentry, Kafka, ClickHouse,
   OpenSearch) treat database compatibility and rolling topology separately.
5. Keep each release immutable by digest after validation; never mass-run
   `midclt app.update` or restart every App just to update a language runtime.

The temporary `finish-migrations-20261024.sh` wrapper remains the
read-only health/acceptance orchestrator. It does **not** authorize Talos
OS/k8s mutation, PHP/Python image substitutions, or any new App redeploy.

## Acceptance and cleanup

- Talos **live** nodes all report v1.14.4 and etcd healthy (three Ready
  nodes; control plane may have one etcd member).
- Kubernetes server, kubelet and platform add-ons are consistent at
  v1.37.1, CSI smoke, DNS, Traefik, Gatus, Prometheus and critical workloads
  pass. Ingress and data path match the pre-upgrade baseline.
- PHP/Python service audit has no **known** EOL runtime; each opaque
  upstream image has a review ticket and explicit verification or a
  documented isolation exception.
- Runtime evidence and rollback artifact IDs recorded in private runbook
  logs, without API keys or patient/family data.
- Mark runtime acceptance only after real tests; remove the temporary
  operator wrapper in a follow-up once migrations are complete.
