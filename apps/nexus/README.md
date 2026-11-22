# Nexus Repository

Data: `/mnt/cpool/nexus3` (dataset `cpool/nexus3`, snapshot class
`recreatable`: one monthly snapshot kept 3 months plus one yearly kept 1 year, see
[`docs/truenas-zfs-snapshot-policy.md`](../../docs/truenas-zfs-snapshot-policy.md)).

## Private HTTPS and workstation package caches (21 November 2026)

The Traefik `nexus-private` router is enabled since 22 November 2026
(`NEXUS_PRIVATE_INGRESS_ENABLED=false` in the app env rolls it back) and
restricts its socket peers to the workstation LANs. Its [post-pfSense reception runbook](../../docs/runbooks/nexus-private-dns-ingress.md)
requires working split DNS, trusted TLS/SNI, an independent WAN denial probe
and a reviewed TrueNAS redeploy before enabling any APT/npm/PyPI/Docker client.

## Two routes, one Nexus (22 November 2026)

| Route | Consumers | Path |
|-------|-----------|------|
| `nexus.int.albandrieu.com` | workstation APT/npm/pip/uv, `infrastructure/nexus` OpenTofu | Pi-hole → Traefik `nexus-private` (LAN allowlist) |
| `nexus.albandrieu.com` | GitHub Actions (Maven, `CF_ACCESS_CLIENT_ID/SECRET` service token) | Cloudflare Access → Tunnel → Traefik `nexus-public` (`crowdsec@file`) |

The OpenTofu provider cannot send Access headers, so `infrastructure/nexus`
targets `nexus.int` (`NEXUS_URL` overrides it). Cut-over order, CI Maven never
loses Nexus because the tunnel keeps `:8081` until the last step:

1. Merge, then redeploy the `nexus` App (labels only, no data change).
2. LAN: `curl -sS -o /dev/null -w '%{http_code}' https://nexus.int.albandrieu.com/service/rest/v1/status` → 200.
3. Public router, as cloudflared calls it (SNI `nexus.int`, Host `nexus.albandrieu.com`):
   `curl -sS -o /dev/null -w '%{http_code}' -H 'Host: nexus.albandrieu.com' https://nexus.int.albandrieu.com/service/rest/v1/status` → 200.
4. `terraform/cloudflare`: plan then apply with `nexus_tunnel_via_traefik = true`.
5. Re-run the `maven-build` workflow of `nabla-servers-bower-sample`: its
   *Check Nexus access* step must print `Nexus: 200 application/java-archive`.
   Rollback: `nexus_tunnel_via_traefik = false` and apply.

The image and repository data remain under Compose/OpenTofu ownership. The
workstation consumer is tracked in
[ansible-workstation #39](https://github.com/AlbanAndrieu/ansible-workstation/pull/39).

## Purge of never-used artifacts (to enable when the Java services are back)

Nexus keeps every proxied component forever. Purge what is never downloaded,
in this order, from the Nexus UI (Administration). The order matters: the
blob store is only compacted after the cleanup, and the monthly ZFS snapshot
(1st of the month, 04:00) only releases space once the purged blobs age out of it.

1. **Cleanup policy** `unused-proxy-90d` (Repository → Cleanup Policies),
   format *All*: *Component Usage* = not downloaded in the last **90 days**,
   *Component Age* = published more than **90 days** ago. Preview it first
   (*Preview results*) and keep the list.
2. Attach it **only to proxy repositories** (Maven Central, npm, PyPI,
   Docker proxies). Never to hosted repositories: their content is the only
   copy of what was uploaded.
3. **Tasks** (System → Tasks), weekly, Saturday night:
   - *Admin - Cleanup repositories using their associated policies*, 01:00;
   - *Admin - Compact blob store* for each blob store, 02:00.
4. Re-enable the Java services, wait one full week of builds, then run the
   two tasks once manually and compare `du -sh /mnt/cpool/nexus3/blobs`
   before and after.

Gate: builds still resolve every dependency after the purge (a purged
component is fetched again from upstream on next use); hosted repositories
unchanged.
