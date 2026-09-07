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

The native TrueNAS App already uses `webserver.port=20720`. The first Compose cutover therefore preserves `20720` both inside and outside the container so the migration changes ownership without also changing the Pi-hole listener contract.

## Emergency recovery of an exhausted API session pool

The Pi-hole CLI lives inside the native TrueNAS container, not on the TrueNAS
host. If the UI cannot authenticate because all API seats are occupied, first
stop the crash-looping synchronizer:

```bash
sudo docker stop pihole-dns-sync
```

Then temporarily increase the native Pi-hole session limit:

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

Record the native image/version and mounts. On the 2026-09-07 appliance these were proven as `pihole/pihole:2026.07.2`, `/mnt/cpool/pihole/config -> /etc/pihole`, and `/mnt/cpool/pihole/dnsmasq -> /etc/dnsmasq.d`:

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

No data copy is required on this host: the native TrueNAS App already mounts the repository target datasets directly. Back them up before cutover, but do not duplicate or rsync them into a second location merely for the migration.

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
3. Confirm host ports `53`, `20720` and `9617` are free.
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

```text
sample.int.albandrieu.com -> 172.17.0.24
```

HTTP:

```bash
curl -fsS http://172.17.0.24:20720/admin/ >/dev/null
```

FastAPI ingress contract:

```bash
CF_ACCESS_CLIENT_ID='...' \
CF_ACCESS_CLIENT_SECRET='...' \
  bash scripts/ingress/verify-sample-exposure.sh
```

This must validate both independent paths:

```text
LAN -> Pi-hole -> sample.int.albandrieu.com -> Traefik -> FastAPI
Internet -> Cloudflare Access -> sample.albandrieu.com -> Tunnel -> FastAPI
```

Finally monitor the Pi-hole API session count/UI. The steady-state synchronizer
must not continuously consume new seats.

## Rollback

If DNS or the web/API contract fails:

1. stop the repository-managed Pi-hole project;
2. confirm its host ports are released;
3. restart the native TrueNAS Pi-hole app;
4. verify DNS on `172.17.0.24:53` and UI on `:20720`;
5. leave `pihole-dns-sync` stopped until its network/auth path is known-good.

Do not uninstall the native application or delete its storage until the
repository-managed replacement is proven and rollback is no longer required.
