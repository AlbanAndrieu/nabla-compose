# Nexus Repository

Data: `/mnt/cpool/nexus3` (dataset `cpool/nexus3`, snapshot class
`artifact-cache`: one weekly snapshot kept 4 weeks, see
[`docs/truenas-zfs-snapshot-policy.md`](../../docs/truenas-zfs-snapshot-policy.md)).

## Purge of never-used artifacts (to enable when the Java services are back)

Nexus keeps every proxied component forever. Purge what is never downloaded,
in this order, from the Nexus UI (Administration). The order matters: the
blob store is only compacted after the cleanup, and the weekly ZFS snapshot
(Sunday 03:30) only releases space once the purged blobs age out of it.

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
