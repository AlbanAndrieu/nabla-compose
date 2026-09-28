# TrueNAS reboot incident · 2026-09-11

This note records the operational failures and successful recovery path observed
during the controlled TrueNAS reboot transaction. It complements
`homelab-reboot-runbook.md` and `truenas-csi-orphan-datasets.md`.

## Confirmed lessons

### 1. `system.ready` CLI output is not stable enough for case-sensitive parsing

On TrueNAS 26 the healthy middleware state rendered as:

```text
True
```

rather than lowercase `true`. Reboot orchestration must normalize case and
whitespace before deciding readiness.

### 2. `--prepare` is a persistent transaction, not a stateless command

A prepare may stop many Apps before a later App fails. Re-running a fresh
`--prepare` at that point is unsafe because already-stopped Apps can be
reclassified as intentionally stopped and disappear from the resume set.

The original `apps-before.json`, `shutdown-plan.json`, `resume-plan.json` and
`resume-apps.txt` remain authoritative until the reboot transaction completes.
Use `--continue-prepare`; never create a second same-boot snapshot.

The 2026-09-11 rehearsal demonstrated this concretely: the first manifest had
49 pre-existing STOPPED Apps, while a second accidental prepare observed 57.
The original manifest was therefore restored as `STATE_ROOT/latest` before the
reboot boundary.

### 3. A Docker `Running/Restarting + Pid=0` state can be runtime bookkeeping debt

`pihole-dns-sync` failed to stop with:

```text
tried to kill container, but did not receive an exit event
```

Docker reported Running/Restarting while `.State.Pid=0`, and an exact
`containerd-shim-runc-v2` process remained. A guarded single-container recovery
was sufficient; Docker/containerd were not restarted globally.

After the shim cleanup, the supported lifecycle call converged:

```text
midclt call -j app.stop pihole
pihole = STOPPED
```

The same `Pid=0` observation can also be transient. Suricata briefly reported
`restarting=true,pid=0`, but a normal `docker stop -t 60 suricata` converged to
`exited`. Always retry the least invasive supported stop before classifying a
shim as orphaned.

### 4. The Docker zero-running gate is meaningful

The reboot transaction intentionally refused Talos shutdown while unmanaged
Suricata was still running. After Suricata stopped, `docker ps` was empty and
the transaction could cross the Kubernetes/Talos shutdown boundary safely.

### 5. Talos workers-first shutdown was validated

The manual fallback reproduced the orchestrator order successfully:

```text
172.17.0.51 worker -> shutdown --wait
172.17.0.52 worker -> shutdown --wait
172.17.0.50 control plane -> shutdown --wait
```

All three TrueNAS VMs then reported `STOPPED` with `autostart=true`.

### 6. The historical CSI orphan disappeared only after full quiesce

The historical dataset:

```text
cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530
```

had no Kubernetes PV, no VolumeAttachment, no NFS share, no child dataset and
no snapshot, yet returned `EBUSY` before quiesce. After all TrueNAS Apps,
Docker containers and Talos VMs were stopped, the supported call:

```bash
sudo midclt call zfs.resource.destroy \
  '{"path":"cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530","recursive":true}'
```

returned `null`, and the required postcondition was:

```text
cannot open 'cpool/k8s/csi/pvc-03741395-a00a-4eaf-a04e-da10e08ec530': dataset does not exist
```

This confirms the orphan was blocked by remaining runtime/mount state rather
than by a live Kubernetes/NFS reference. Do not use `zfs destroy -f` for this
class of incident.

### 7. Bundle identity must be verifiable

A directory name containing a Git SHA is not sufficient evidence that its
contents match that commit. During the rehearsal, the active `current` pointer
still referenced an older `readyfix1` bundle, while a proposed newer bundle
directory had never actually been created.

Future bundle creation uses `scripts/truenas/materialize-reboot-bundle.sh`:

```bash
sudo bash scripts/truenas/materialize-reboot-bundle.sh \
  --ref <reviewed-commit> \
  --activate
```

The helper:

1. resolves one exact Git commit;
2. materializes into a temporary directory;
3. validates shell/Python syntax;
4. requires `--continue-prepare` in the reboot orchestrator;
5. writes `SOURCE_COMMIT` and `SHA256SUMS`;
6. verifies all checksums;
7. refuses silent overwrite of a mismatched existing bundle;
8. atomically renames the staged directory;
9. atomically updates `current` only after successful validation.

`reboot-homelab.sh` verifies `SHA256SUMS` automatically when present and stores
its source/script identity in the transaction manifest.

## Reboot acceptance boundary

A supported TrueNAS reboot is authorized only when all of the following are
true:

```text
phase = PREPARED
docker ps = empty
taloswk01 = STOPPED, autostart=true
taloswk02 = STOPPED, autostart=true
taloscp01 = STOPPED, autostart=true
```

A proven orphan CSI dataset should be retried after this full quiesce and before
the host reboot. If supported deletion still returns `EBUSY`, preserve evidence
and proceed without forced deletion.

## Post-reboot priority

After TrueNAS returns:

1. confirm the boot ID changed and middleware is ready;
2. run Docker IPAM post-reboot validation;
3. require Talos VM autostart and Kubernetes 3/3 Ready;
4. run one fresh CSI RWX/reclaim regression;
5. resume only Apps captured by the original manifest;
6. run final verification and bounded cleanup.
