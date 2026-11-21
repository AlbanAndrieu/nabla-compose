# Nexus Repository

Data: `/mnt/cpool/nexus3` (dataset `cpool/nexus3`, snapshot class
`recreatable`: one monthly snapshot kept 3 months plus one yearly kept 1 year, see
[`docs/truenas-zfs-snapshot-policy.md`](../../docs/truenas-zfs-snapshot-policy.md)).

## Private HTTPS and workstation package caches (21 November 2026)

The existing Traefik `nexus-private` router is opt-in and now restricts its
socket peers to the workstation LANs. Its [post-pfSense reception runbook](../../docs/runbooks/nexus-private-dns-ingress.md)
requires working split DNS, trusted TLS/SNI, an independent WAN denial probe
and a reviewed TrueNAS redeploy before enabling any APT/npm/PyPI/Docker client.

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
