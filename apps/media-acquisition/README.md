# Media acquisition (Gluetun + qBittorrent)

Status: **planned**. Design, DNS strategy and acceptance tests:
[`docs/arr-media-library-roadmap.md`](../../docs/arr-media-library-roadmap.md).

Only `qbittorrent` shares the `gluetun` network namespace
(`network_mode: service:gluetun`). Nothing else may join it: qBittorrent's
"bypass authentication for localhost" option, required by the port-forwarding
command, gives every process of the namespace full control of qBittorrent.

## Prerequisites

1. The never-finished native TrueNAS PoC Apps (`transmission`, `qbittorrent` if
   any) are deleted (roadmap P0).
2. A ProtonVPN plan with P2P servers. Generate a WireGuard configuration on a P2P
   server with **NAT-PMP (port forwarding)** enabled.
3. Vaultwarden item `nabla/prod/media-acquisition` (folder `TrueNAS`) with the
   fields `WIREGUARD_PRIVATE_KEY`, `HTTPPROXY_USER` and `HTTPPROXY_PASSWORD`,
   rendered to `/mnt/cpool/secrets/runtime/media-acquisition/.env.secrets`
   (`root:root 0600`). Never paste the private key in a ticket or a commit.
4. The shared external network `media` and the storage of the roadmap section 7
   (`cpool/media` with a quota). `scripts/truenas/deploy-media-stack.sh` checks
   both.

## Deployment

```bash
sudo bash scripts/truenas/deploy-media-stack.sh --check media-acquisition
sudo bash scripts/truenas/deploy-media-stack.sh --apply media-acquisition
```

## qBittorrent settings (as code)

Read the temporary WebUI password with `sudo docker logs qbittorrent`, set a
strong password in the WebUI and store it in Vaultwarden
(`QBITTORRENT_WEBUI_PASSWORD`). Every other setting is declared in
[`config/media/settings.yml`](../../config/media/settings.yml) and converged by:

```bash
scripts/quality/python-with-repo-deps.sh scripts/media/reconcile-media-settings.py --check --app qbittorrent
scripts/quality/python-with-repo-deps.sh scripts/media/reconcile-media-settings.py --apply --app qbittorrent
```

It covers encryption required, anonymous mode, no UPnP/LSD, localhost bypass
for the Gluetun UP/DOWN commands, CSRF/Host/clickjacking protections, no
external program, excluded executable extensions, `/data/torrents` paths, the
`movies`/`tv`/`music` categories and POSIX disk IO. Gluetun keeps ownership of
the listening port and network interface.

## Telemetry

- Metrics: `apps/qbittorrent-exporter` (separate App, never in this namespace,
  API key `QBITTORRENT_API_KEY` created in the WebUI), Prometheus job
  `qbittorrent`, Grafana dashboard *Nabla Media Stack*.
- Logs: both containers carry `com.albandrieu.nabla.logs: media`; Alloy ships
  them to Loki (`{container="gluetun"}` shows tunnel, DNS and port events).

## Acceptance

Run the anonymity battery of the roadmap section 9 (public IP, IPv6, kill
switch, DNS capture inside the namespace, torrent IP check, port forwarding)
before switching `status: planned` to `active` in `compose.yml` and
`catalog-info.yaml`.
