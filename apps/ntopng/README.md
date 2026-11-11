# ntopng

ntopng **Community** (free, no licence) captures the TrueNAS bridge `br0`
(172.17.0.24, physical uplink `enp10s0` plus the Talos VMs) and serves its UI on
<http://172.17.0.24:31080>. Port 3000 is taken by Langfuse.

## Configuration as code

Every runtime option lives in [`ntopng.conf`](ntopng.conf), mounted read-only
at `/etc/ntopng/nabla.conf`:

- `--community`: forces the free edition, so no licence file is mounted;
- `--interface=br0`: reviewed capture interface (host networking);
- `--http-port=172.17.0.24:31080`: LAN address only;
- `--local-networks`: the LAN and the TrueNAS Docker pool.

[`entrypoint.sh`](entrypoint.sh) gives the bind-mounted Redis directory to the
image's `redis` user (ntopng keeps users and preferences in Redis), then hands
the configuration file to the upstream `/run.sh`.

Persistent data: `/mnt/cpool/ntopng` (RRD time series) and
`/mnt/cpool/ntopng/redis`.

## Out of scope without a licence

- historical flows in ClickHouse (`--dump-flows=clickhouse`): Enterprise M+;
- nAnalyst, the LLM assistant: it reads those ClickHouse flows. Revisit both
  only with a licence; LiteLLM would then be configured as a custom
  OpenAI-compatible endpoint (`http://172.17.0.24:4000/v1`).

## Deploy

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-repository-storage.sh --check ntopng
sudo bash scripts/truenas/deploy-ntopng.sh --check
# After review:
# sudo env NABLA_RUNTIME_CHANGE_APPROVED=yes bash scripts/truenas/deploy-ntopng.sh --apply
```

`--check` changes nothing and verifies that the interface named in
`ntopng.conf` exists on the host. If an `ntopng` App already exists, `--apply`
also needs `NABLA_NTOPNG_UPDATE_APPROVED=yes`.

At the first login ntopng asks to replace the default `admin`/`admin`
password: do it immediately and store the new login in `nabla/prod/ntopng`.

## Observability

- Gatus and the lifecycle audit probe `172.17.0.24:31080`.
- Prometheus: ntopng has no native endpoint. The maintained
  [`aauren/ntopng-exporter`](https://github.com/aauren/ntopng-exporter) (v1.x
  for the v2 REST API) needs a read-only ntopng user created in the UI; add it
  once ntopng runs.
- Alerts: Community supports webhook, Telegram, e-mail and Discord endpoints
  (UI, *Notifications*).
