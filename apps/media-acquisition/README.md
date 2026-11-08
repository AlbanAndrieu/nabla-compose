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

## qBittorrent settings (WebUI, once)

Read the temporary WebUI password with `sudo docker logs qbittorrent`, then:

- Web UI: set a strong password (store it in Vaultwarden), keep CSRF and Host
  header validation enabled, enable **Bypass authentication for clients on
  localhost** (required by the Gluetun UP/DOWN commands).
- Connection: disable UPnP / NAT-PMP; do not set a fixed listening port.
- BitTorrent: encryption **Require**, anonymous mode on, local peer discovery off.
- Downloads: default save path `/data/torrents`, incomplete files in
  `/data/torrents/incomplete`, categories `movies`, `tv` and `music` saving to
  `/data/torrents/<category>`.
- Excluded file names: `*.exe`, `*.scr`, `*.lnk`, `*.bat`, `*.cmd`, `*.com`,
  `*.msi`, `*.vbs`, `*.ps1`, `*.js`.
- Never configure "Run external program".
- Advanced: disk IO type **POSIX-compliant** (ZFS).

## Acceptance

Run the anonymity battery of the roadmap section 9 (public IP, IPv6, kill
switch, DNS capture inside the namespace, torrent IP check, port forwarding)
before switching `status: planned` to `active` in `compose.yml` and
`catalog-info.yaml`.
