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

[`entrypoint.sh`](entrypoint.sh) replaces the upstream `/run.sh`: it gives the
bind-mounted Redis directory to the image's `redis` user (ntopng keeps users
and preferences in Redis), starts Redis, writes the MD5 of
`NTOPNG_ADMIN_PASSWORD` to `ntopng.user.admin.password`, then starts ntopng.
ntopng only writes its default `admin`/`admin` when that key is absent, so the
UI is never reachable with the default. The entrypoint refuses to start when
the secret is missing. The password comes from `nabla/prod/ntopng`, rendered
to `/mnt/cpool/secrets/runtime/ntopng/.env.secrets` and mounted as a Compose
secret (not in Docker `Config.Env`); a password changed in the UI is reset to
the Vaultwarden value at the next start.

Persistent data: `/mnt/cpool/ntopng` (configuration, category lists) and
`/mnt/cpool/ntopng/redis`. The RRD time series (`/var/lib/ntopng/0` and `-1`)
live in a tmpfs since 21/11: they caused most of the pool's small writes, and
their history restarts empty with the container. The SQLite alert store
(`/var/lib/ntopng/0/alerts`) shares that tmpfs, so the entrypoint sets
`ntopng.prefs.emit_flow_alerts` to 0: flow alerts reached ~700/s on `br0` and
filled it in 13 minutes (27/11). Flow scores and host alerts remain.

## Control: REST API, MCP and OpenTofu

ntopng has no runtime CLI: the REST API v2 (`/lua/rest/v2/...`) is the control
surface. [`scripts/ntopng/control.sh`](../../scripts/ntopng/control.sh)
(`check`, then `apply`, owner terminal with Vaultwarden unlocked) creates two
administrator users, each with its own API token stored straight into
Vaultwarden. ntopng has no finer role: the MCP endpoint and every REST write
require administrator.

- `nabla-control` (`nabla/prod/ntopng-control`): OpenTofu and API scripts.
- `nabla-mcp` (`nabla/prod/ntopng-mcp`): the built-in MCP server
  (`/lua/rest/v2/exec/llm/mcp.lua`, 12 Community tools), registered in the
  LiteLLM gateway `nabla-mcp` by `scripts/litellm/mcp-gateway.sh apply` with the
  11 read-only tools of `scripts/litellm/ntopng-readonly-tools.json`: that list
  is the write barrier (`add_active_monitoring_script` stays out).

[`terraform/ntopng`](../../terraform/ntopng) (Terragrunt `infrastructure/ntopng`,
provider `Mastercard/restapi`, no ntopng provider exists) caps each alert family
at 20,000 rows (default 1,000,000) and disables the three flow checks behind
the 22/11 flood. `control.sh apply` runs it with the `nabla-control` token; no
token reaches the state. Flow alerts stay off in the entrypoint.

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

`--check` changes nothing; it verifies that the interface named in
`ntopng.conf` exists on the host and that the runtime secret is a root-owned
`0600` file holding `NTOPNG_ADMIN_PASSWORD`. If an `ntopng` App already exists,
`--apply` also needs `NABLA_NTOPNG_UPDATE_APPROVED=yes`.

## Observability

- Gatus and the lifecycle audit probe `172.17.0.24:31080`.
- Prometheus: ntopng has no native endpoint. The maintained
  [`aauren/ntopng-exporter`](https://github.com/aauren/ntopng-exporter) (v1.x
  for the v2 REST API) needs a read-only ntopng user created in the UI; add it
  once ntopng runs.
- Alerts: Community supports webhook, Telegram, e-mail and Discord endpoints
  (UI, *Notifications*).
