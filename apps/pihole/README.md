# Pi-hole repository-managed migration

This directory is the target source of truth for Pi-hole on TrueNAS.

## Why migrate

The native TrueNAS Pi-hole application and the Traefik-owned DNS synchronizer
exposed two operational faults on 2026-09-07:

1. `pihole-dns-sync` repeatedly authenticated to Pi-hole until
   `webserver.api.max_sessions=16` was exhausted;
2. the synchronizer could not resolve `docker-socket-proxy` because it was not
   attached to the shared `intranet` Docker network, so it restarted and
   allocated additional API sessions without completing a useful sync.

A third lifecycle fault was confirmed during the controlled reboot preparation
on 2026-09-11: Docker could report `pihole-dns-sync` as both
`Running=true`/`Restarting=true` while `.State.Pid=0`, with only an orphaned
`containerd-shim-runc-v2` process left behind. In that state `app.stop pihole`
failed with `tried to kill container, but did not receive an exit event` until
the exact orphan shim was recovered.

The repository-managed target keeps the default API session budget and fixes the
network/lifecycle cause instead of permanently increasing the seat count.

## Current endpoint contract

Keep these client-visible endpoints stable during migration:

```text
DNS TCP/UDP     172.17.0.24:53
Pi-hole HTTP    http://172.17.0.24:20720/admin/
Pi-hole HTTPS   https://172.17.0.24:30132/
Exporter        http://172.17.0.24:9617
```

Inside the Compose project, Pi-hole uses standard HTTP/HTTPS ports `80/443`.
Host mappings preserve the existing `20720/30132` contract.

## Emergency recovery of an exhausted API session pool

The Pi-hole CLI lives inside the native TrueNAS container, not on the TrueNAS
host. If the UI cannot authenticate because all API seats are occupied, first
stop the crash-looping synchronizer:

```bash
sudo docker stop pihole-dns-sync
```

If that stop fails with `did not receive an exit event`, do not repeatedly run
`docker kill` and do not restart Docker/containerd globally. First run the
read-only orphan-shim diagnostic:

```bash
sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh --check
```

A recoverable ghost state must show Docker `Running=true` or `Restarting=true`
with `.State.Pid=0`, plus exactly one shim whose command line contains the exact
full container ID. Recover only that container:

```bash
sudo bash scripts/truenas/diagnose-docker-orphan-shims.sh \
  --recover pihole-dns-sync
```

The helper refuses to signal a shim when a live container init PID exists. It
sets restart policy to `no`, signals the exact shim, waits for Docker to converge
and never uses a daemon-wide restart. After recovery, retry the supported
TrueNAS lifecycle operation:

```bash
sudo midclt call -j app.stop pihole
```

The 2026-09-11 incident converged to `pihole=STOPPED` with no remaining Pi-hole
containers. When this happens during `reboot-homelab.sh --prepare`, preserve the
existing reboot manifest and continue it with `--continue-prepare`; never start
a new `--prepare` snapshot after Apps have already been stopped.

Then temporarily increase the native Pi-hole session limit when that is still
required for the separate API-seat incident:

```bash
sudo docker exec ix-pihole-pihole-1 \
  pihole-FTL --config webserver.api.max_sessions 32
```

Use the recovered UI only to inspect/revoke stale sessions if needed. Restore the
normal limit after recovery:

```bash
sudo docker exec ix-pihole-pihole-1 \
  pihole-FTL --config webserver.api.max_sessions 16
```

Do not use a larger permanent value as the fix for a restarting API client.

## Pre-cutover inventory

Do not stop or remove the native TrueNAS application until its storage has been
identified and backed up.

Record the native image/version and mounts:

```bash
sudo docker inspect ix-pihole-pihole-1 \
  --format '{{.Config.Image}}'

sudo docker inspect ix-pihole-pihole-1 \
  --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

Record the effective Pi-hole settings that matter to the cutover:

```bash
sudo docker exec ix-pihole-pihole-1 \
  pihole-FTL --config webserver.port

sudo docker exec ix-pihole-pihole-1 \
  pihole-FTL --config webserver.api.max_sessions

sudo docker exec ix-pihole-pihole-1 \
  pihole-FTL --config dns.listeningMode
```

Create the destination datasets/directories before copying data:

```bash
sudo install -d -m 700 /mnt/cpool/pihole
sudo install -d -m 700 /mnt/cpool/pihole/config
sudo install -d -m 700 /mnt/cpool/pihole/dnsmasq
```

Copy the native `/etc/pihole` data from the exact source path discovered by
`docker inspect`. Do not guess the ixVolume path. Preserve ownership, modes,
timestamps and extended metadata where the backing filesystem supports them.

If the native deployment has meaningful `/etc/dnsmasq.d` contents, migrate
those as well. The directory is retained in the target Compose specifically to
make the first v6 cutover conservative.

## Secrets

`/mnt/cpool/pihole/.env.secrets` must remain root-restricted and outside Git.

Keep the existing Pi-hole UI/API credential unchanged during migration. The
target Pi-hole container can consume the canonical Pi-hole v6 variable:

```dotenv
FTLCONF_webserver_api_password=<existing password>
PIHOLE_PASSWORD=<same existing password for current exporter compatibility>
```

The DNS synchronizer temporarily continues to consume the already-working
credential from `/mnt/cpool/traefik/.env.secrets` during the first cutover.
Consolidate that secret into the Pi-hole secret file only after functional
validation; do not rotate credentials during a data/runtime migration.

## Validate the Compose definition

From the repository root:

```bash
docker compose \
  --project-directory apps/pihole \
  -f apps/pihole/compose.yml \
  config --quiet --no-interpolate --no-env-resolution
```

## Adopt an already-running repository Pi-hole

If `docker compose ... up -d pihole-exporter` reports that container name
`/pihole` is already in use, do not delete the DNS container blindly. First
identify its Compose owner:

```bash
docker inspect pihole |
  jq '.[0] | {
    status: .State.Status,
    health: (.State.Health.Status // null),
    project: .Config.Labels["com.docker.compose.project"],
    working_dir: .Config.Labels["com.docker.compose.project.working_dir"],
    config_files: .Config.Labels["com.docker.compose.project.config_files"],
    networks: (.NetworkSettings.Networks | keys)
  }'
```

The exporter no longer has a Compose `depends_on` edge to Pi-hole, because the
functional dependency must not force DNS lifecycle ownership. Once the existing
Pi-hole is confirmed healthy and attached to `intranet`, start only the
exporter:

```bash
docker compose \
  --project-directory apps/pihole \
  -f apps/pihole/compose.yml \
  up -d --no-deps pihole-exporter
```

Then verify the metrics endpoint instead of relying only on container state:

```bash
curl -fsS http://172.17.0.24:9617/metrics | head
```

Also confirm the shared read-only Docker proxy is healthy and attached to
`intranet`:

```bash
sudo docker inspect docker-socket-proxy \
  --format '{{json .NetworkSettings.Networks}}' | jq .

sudo docker exec docker-socket-proxy wget -qO- http://127.0.0.1:2375/_ping
```

## Cutover

1. Back up native Pi-hole configuration/data.
2. Stop `pihole-dns-sync` and the native Pi-hole application.
3. Confirm host ports `53`, `20720`, `30132` and `9617` are free.
4. Start the repository-managed Compose project.
5. Validate DNS, UI/API, synchronization and exporter.
6. Keep the native TrueNAS app stopped but recoverable until the acceptance
   checks have passed over a normal observation window.

Start the repository-managed services only after the native ports are free:

```bash
docker compose -f apps/pihole/compose.yml up -d
```

## Acceptance tests

Container state:

```bash
sudo docker ps --filter name=pihole
sudo docker logs --tail 100 pihole
sudo docker logs --tail 100 pihole-dns-sync
```

The synchronizer must resolve the shared proxy and must not enter a restart loop:

```bash
sudo docker exec pihole-dns-sync getent hosts docker-socket-proxy
```

Expected: an `intranet` address for `docker-socket-proxy`.

DNS:

```bash
dig @172.17.0.24 pi.hole
dig @172.17.0.24 sample.int.albandrieu.com
```

The private FastAPI route must resolve to TrueNAS:
