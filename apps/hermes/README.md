# Hermes DevSecOps gateway — **not deployed** (catalog status `planned`)

This read-only Compose service **replaces the TrueNAS native App
`hermes-agent`**, which is to be removed (see *Retiring the native App*
below). It does not modify the shared LiteLLM stack, OpenTerminal, SearXNG,
Vaultwarden or Grafana. See
[Secure by Design ADR](../../docs/security/hermes-secure-by-design.md) and
the [Talos migration ADR](../../docs/security/hermes-talos-migration.md).

## What is implemented in Git

| Component | Implemented | Status |
| --- | --- | --- |
| Hermes official Docker image gateway with persistent Hermes data | `compose.yml` (opt-in profile, no ports) | not deployed |
| Non-root runtime user via official image drop-to-UID-10000 | capabilities minimized for s6 bootstrap | runtime unverified |
| Read-only policy configuration and no terminal/browser/file/code/web tools | `config/hermes/config.yaml` | not deployed |
| Local stdio MCP with allowlisted Prometheus jobs | `scripts/hermes/readonly_mcp.py` | source only |
| Cost/token query scoped to the Hermes LiteLLM key alias | MCP + Prometheus scrape/recording rules | no real samples yet |
| Target budget of €20 per calendar month, four allowlisted model routes, 5 RPM | `config/hermes/litellm-key-policy.json` | not provisioned |
| Private, API-key protected OpenAI-compatible Hermes API | `compose.api.yml` | **off** |
| Vaultwarden-only operator provisioning | planned | no automatic secret reads |
| OpenTerminal, Loki logs, SearXNG search | evaluated and deferred to scoped adapters | **not connected** |
| LLM Guard/Presidio fail-closed request/response filters | architectural gate | **not deployed** |

The MCP only returns (1) Prometheus `up` aggregates for an explicit job
allowlist, (2) an overview of five jobs, or (3) real key-scoped LiteLLM
spend/tokens from Prometheus. No raw logs, arbitrary PromQL/LogQL, IPs,
metrics labels, Docker `exec`, shell, trueNAS API or credentials are exposed.
Unknown services, non-finite metrics, SSRF origins and redirects are rejected.

## Anthropic Opus primary, OpenAI last resort (configuration only)

The versioned **Hermes configuration**, not the live native
`hermes-agent` TrueNAS App, now requests these ordered aliases through the
existing **private TrueNAS LiteLLM gateway**:

1. `hermes-opus-5-5` → `anthropic/claude-opus-5-5`
2. `hermes-opus-5` → `anthropic/claude-opus-5`
3. `hermes-opus-4-8` → `anthropic/claude-opus-4-8`
4. `hermes-openai` → `openai/gpt-5.4` (**last resort**)

This is failure-based fallback, not load balancing. Verify model
availability **and LiteLLM version compatibility** before deployment: the
deployed `main-stable` image has not been proven to support these model IDs.
No paid test call has been made.

Upstream `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` belong exclusively
in Vaultwarden `nabla/prod/litellm`, materialized to root-owned
`/mnt/cpool/secrets/runtime/litellm/.env.secrets`. Manifest entries
remain optional **while the Anthropic key has not been supplied** so the
current renderer is not disrupted. Neither key is available merely because
its field name is declared. **Do not redeploy LiteLLM before these fields
have been populated and checked.**

Hermes receives only `HERMES_LITELLM_API_KEY` (never upstream API keys or
the LiteLLM master key), with its dedicated virtual-key allowlist of the
four aliases, 5 RPM, 10k TPM and one concurrent request. Preserve the
previously reviewed **€20/month** ceiling: convert conservatively to an
actual LiteLLM USD `max_budget` with an explicit reset period at provision
time. The existing proxy `default_fallbacks` may point to local inference
for other consumers; restrict the Hermes key to these four groups and
verify fallback access enforcement so no hidden extra route is reachable.

Before changing the deployed TrueNAS LiteLLM configuration, execute the
**read-only provider-secret preflight** (prints status/key names, not values):

```bash
sudo python3 scripts/truenas/check-litellm-hermes-credentials.py --check
just hermes-opus-routing-test
```

`hermes_cloud_route=blocked` is expected until the upstream credentials are
supplied in Vaultwarden and materialized. A status of
`credentials_present_metadata_only` is **not** proof of valid key
permissions, LiteLLM compatibility, provider reachability or monthly-budget
enforcement. The script performs **no inference requests**.

The native TrueNAS `hermes-agent` App is never reconfigured: it is audited,
then retired (see below). Privacy of prompts in LiteLLM logs, Langfuse
and Redis cache remains a P0 gate before cloud inference.

References: https://platform.claude.com/docs/en/models/overview and
https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers/.

## Preparation on TrueNAS (explicit operator transaction)

**No script in this service installs or restart applications automatically.**
Before any activation:

1. Export the current `midclt app.query` and actual rendered App deployment
   for `hermes-agent`; determine its running image/digest, mounts, network,
   UID, existing Telegram/Discord credentials and data location. Back up its
   existing state. **Do not reuse a bot token simultaneously in two gateways.**
2. Verify that the `nousresearch/hermes-agent@sha256:...` release is authentic,
   current, and supports the chosen `platform_toolsets`, MCP and model schema.
   `HERMES_IMAGE_REF` must be an immutable digest; the default `:stable` is
   only for rendering the template and **fails** the security preflight.
3. Create a dedicated `/mnt/cpool/hermes/data` directory owned by UID 10000,
   mode 0700 (it is mounted at the image's `HERMES_HOME`, `/opt/data`).
   Never mount `/mnt/cpool/hermes` itself: it still holds legacy native-App
   files (`.env`). Do not alter the parent dataset or its ZFS ACLs.
   Review security preset and snapshots. Persisted `config.yaml` comes from
   a read-only mount; explicit `HERMES_SKIP_CONFIG_MIGRATION=1` prevents
   automatic schema changes. Do not silently overwrite legacy state.
4. Via the existing operator-managed `bw` and manifest flow, create a
   **restricted** Hermes collection/identity with separately generated
   Telegram and Discord bot tokens and a LiteLLM **virtual key**, never the
   LiteLLM master key or Vaultwarden account credentials. The existing
   Vaultwarden store does not implement the Bitwarden Secrets Manager
   machine-account API. No Vaultwarden MCP/server access for Hermes.
5. Materialize only Hermes-specific `.env.secrets` on TrueNAS at
   `/mnt/cpool/secrets/runtime/hermes/.env.secrets`, root-owned 0600.
   Required keys: `HERMES_LITELLM_API_KEY` and one bot token/allowed user
   pair (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USERS` or
   `DISCORD_BOT_TOKEN` + `DISCORD_ALLOWED_USERS`). Do not set `ALLOW_ALL`,
   `HERMES_YOLO_MODE`, cloud provider keys or API master credentials.
6. Review the [key budget contract](../../config/hermes/litellm-key-policy.json):
   **€20 per calendar month** is an operator spending ceiling, not a token
   price and not yet enforced. LiteLLM virtual-key `max_budget` accounting
   is USD-denominated; convert the EUR limit to a conservative USD ceiling
   at key provisioning using a documented FX rate and period/reset policy.
   Do not send `monthly_budget` directly to LiteLLM as though it were a
   recognized API field. No automated conversion or key provisioning is
   implemented here. Create the LiteLLM key only after that review.
   It must have `key_alias=hermes`, a strict four-model allowlist and
   management routes blocked. **Do not pass LiteLLM master key to Hermes**.
   Before sending anything non-public, eliminate/validate the existing
   LiteLLM `store_prompts_in_spend_logs: true`,
   `turn_off_message_logging: false`, Redis cache and Langfuse body logging
   for this profile. Paid cloud fallback is now explicitly modeled but must
   remain disabled at runtime until both upstream keys, the bounded virtual
   key, model compatibility and privacy/egress gates are verified.
7. **Network gate:** enforce an actual container/VM egress allowlist for
   Discord/Telegram, DNS/NTP, the internal authorized LiteLLM endpoint and
   Prometheus endpoint; deny all other destinations including admin APIs,
   Docker proxy, RFC1918 metadata, IPv6 escapes, arbitrary DNS/web/SSRF.
   An ordinary Compose bridge network **does NOT enforce egress ACLs**.
   If the TrueNAS firewall cannot isolate one Docker container reliably,
   run Hermes on a separate unprivileged VM. `cap_drop` alone does not
   constitute network isolation.
8. Confirm the native TrueNAS App is retired (next section). Check
   restore/snapshot plan, then review the Compose model without disclosing
   resolved secret values:

```bash
cd /mnt/cpool/compose/nabla-compose
export HERMES_IMAGE_REF='nousresearch/hermes-agent@sha256:<verified-digest>'
python3 scripts/hermes/preflight.py --check
docker compose -f apps/hermes/compose.yml --profile hermes config --quiet
# Only after all runtime/security gates are independently accepted:
docker compose -f apps/hermes/compose.yml --profile hermes up -d
```

The `up` command is an operator action, **not** an instruction that the agent
executes automatically. Never run a plain `docker compose config` without
`--quiet` when env files might contain credentials. The image
capabilities preserve just `CHOWN`, `SETUID`, `SETGID` so the official s6
supervisor can drop gateway privileges; prove the gateway process runs as
UID 10000 and has no effective Linux capabilities. If the image requires
more capabilities or mutable system paths, pause rather than using
`privileged`/root or writable system mounts.

## Retiring the native App `hermes-agent` (operator only)

Decision 2026-10-23: the native TrueNAS App is removed in favour of this
service. It is no longer listed in `config/truenas/restore-optional-apps.txt`.
Deletion is irreversible; run it by hand, in this order:

1. Audit without printing secrets: `sudo bash scripts/truenas/diagnose-hermes-agent.sh --check`.
2. Export the App definition for the record:
   `midclt call app.config hermes-agent > /mnt/cpool/backups/hermes-agent.app-config.json`
   (root-owned, mode 0600: it may contain credentials).
3. ZFS snapshot of the dataset holding `/mnt/cpool/hermes` before anything else.
4. Stop the App, then **revoke** its Telegram/Discord bot tokens (or keep them
   only for this service, never both running).
5. Delete the App from the TrueNAS UI or `midclt call app.delete hermes-agent`,
   **without** removing its host data; keep `/mnt/cpool/hermes` for forensics
   until this service is accepted.

## Exposure to other homelab applications (opt-in only)

Hermes' OpenAI-compatible API can act as an agent backend for **Open WebUI**,
**FastAPI Sample**, **n8n** and internal orchestrators, but it exposes the
agent's toolset. Enable it only after the read-only profile, independent
`API_SERVER_KEY` secret (32+ chars), private network and auth tests pass:

```bash
python3 scripts/hermes/preflight.py --check --api
docker compose -f apps/hermes/compose.yml -f apps/hermes/compose.api.yml \
  --profile hermes config --quiet
# Then controlled apply/acceptance separately.
```

Clients on the shared `intranet` Docker network can use
`http://hermes:8642/v1` and a dedicated API bearer key. Do not publish
`:8642` through Traefik/Cloudflare/HAProxy, bind a host port, or route public
external tools to Hermes. The API key grants **all tools still enabled** in the
profile; do not confuse CORS with authentication. Keep distinct per-client
identities, separate rate limits and require call quotas at the API boundary.
Open WebUI already uses shared LiteLLM; adding Hermes must be a **separate
model/backend option**, not replace its existing model path.

## How to reuse OpenTerminal safely

The repo contains `open-terminal` as a **planned migration** with a declared
`OPEN_TERMINAL_API_KEY` secret and expected port 30377; no runtime service
health/ACL proof was obtained. It is NOT a constrained read-only API merely
because it has a key.

Do **not** connect OpenTerminal to Hermes in this first phase. A later optional
`hermes-ops` worker should use a **separate unprivileged workload VM/sandbox**
with no Docker socket, host mounts, TrueNAS SSH/root or shared secrets. Even
there, terminal commands are only for ephemeral development and testing.
Operations against the homelab continue through a typed external task broker
with independent approval, not OpenTerminal's arbitrary shell API.

## Observability and costs

The canonical `apps/prometheus/prometheus.yml` now has
`litellm_hermes` scrape **every 60 seconds**, filtered at ingestion to
the `hermes` virtual key alias and cost/token counters. It removes
user/email/IP/hashed-key labels before storing/remote-writing to Mimir.
`apps/prometheus/rules/hermes.rules.yml` defines:
- `hermes:litellm_spend_usd`, based only on observed samples;
- `hermes:litellm_tokens_total`;
- `HermesSpendReview` when cumulative observed spend exceeds $1.50.

Prometheus being configured to scrape does **not** prove `/metrics` works,
that the alias exists or that spend accounting is correct. The budget is
enforced by the separate LiteLLM virtual key, not by Prometheus alerts.
Local Ollama requests may report zero USD despite consuming GPU/CPU;
track tokens/latency separately and investigate LiteLLM zero-cost metrics.

Read-only functional scenarios: accepted Telegram DM, rejected second user,
no memory/skill writes, unknown MCP service rejected, forged instructions in
a fake `up` label not surfaced, simulated Prometheus outage fail-closed,
missing cost metrics -> `incomplete` (never zero), blocked API access,
bot token revocation, restart persistence without stored secrets in logs,
CPU/memory caps, SearXNG/Cloud fallback impossible in this profile.

## Rollback

Stop only `hermes`; leave `/mnt/cpool/hermes` and its snapshots untouched,
revoke its bot/API/LiteLLM virtual keys, detach the optional intranet network,
preserve the `/mnt/cpool/hermes/data` snapshot for forensics, and roll back
Prometheus scrape/rules if necessary. Never delete shared LiteLLM, Loki,
OpenTerminal, SearXNG, Vaultwarden or Prometheus state to roll back this service.
