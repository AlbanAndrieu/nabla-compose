# Hermes DevSecOps POC — **not deployed**

This is an **isolated experimental alternative** to the existing TrueNAS native
App `hermes-agent`; it does not overwrite that App, the shared LiteLLM stack,
OpenTerminal, SearXNG, Vaultwarden or Grafana. See
[Secure by Design ADR](../../docs/security/hermes-secure-by-design.md).

## What is implemented in Git

| Component | Implemented | Status |
| --- | --- | --- |
| Hermes official Docker image gateway with persistent POC data | `compose.yml` (opt-in profile, no ports) | not deployed |
| Non-root runtime user via official image drop-to-UID-10000 | capabilities minimized for s6 bootstrap | runtime unverified |
| Read-only policy configuration and no terminal/browser/file/code/web tools | `config/hermes/poc-config.yaml` | not deployed |
| Local stdio MCP with allowlisted Prometheus jobs | `scripts/hermes/readonly_mcp.py` | source only |
| Cost/token query scoped to the Hermes LiteLLM key alias | MCP + Prometheus scrape/recording rules | no real samples yet |
| Virtual key budget of $2 per 30 days, one model, 5 RPM | `config/hermes/litellm-key-policy.json` | not provisioned |
| Private, API-key protected OpenAI-compatible Hermes API | `compose.api.yml` | **off** |
| Vaultwarden-only operator provisioning | planned | no automatic secret reads |
| OpenTerminal, Loki logs, SearXNG search | evaluated and deferred to scoped adapters | **not connected** |
| LLM Guard/Presidio fail-closed request/response filters | architectural gate | **not deployed** |

The MCP only returns (1) Prometheus `up` aggregates for an explicit job
allowlist, (2) an overview of five jobs, or (3) real key-scoped LiteLLM
spend/tokens from Prometheus. No raw logs, arbitrary PromQL/LogQL, IPs,
metrics labels, Docker `exec`, shell, trueNAS API or credentials are exposed.
Unknown services, non-finite metrics, SSRF origins and redirects are rejected.

## Preparation on TrueNAS (explicit operator transaction)

**No scripts in this POC install or restart applications automatically.**
Before any activation:

1. Export the current `midclt app.query` and actual rendered App deployment
   for `hermes-agent`; determine its running image/digest, mounts, network,
   UID, existing Telegram/Discord credentials and data location. Back up its
   existing state. **Do not reuse a bot token simultaneously in two gateways.**
2. Verify that the `nousresearch/hermes-agent@sha256:...` release is authentic,
   current, and supports the chosen `platform_toolsets`, MCP and model schema.
   `HERMES_IMAGE_REF` must be an immutable digest; the default `:stable` is
   only for rendering the template and **fails** the security preflight.
3. Create a dedicated `/mnt/cpool/hermes/poc` directory owned by UID 10000,
   mode 0700, without altering the existing Hermes dataset or ZFS ACLs.
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
6. Create the LiteLLM key with the reviewed
   [key budget contract](../../config/hermes/litellm-key-policy.json).
   It must have `key_alias=hermes-poc`, a restricted model list and
   management routes blocked. **Do not pass LiteLLM master key to Hermes**.
   Before sending anything non-public, eliminate/validate the existing
   LiteLLM `store_prompts_in_spend_logs: true`,
   `turn_off_message_logging: false`, Redis cache and Langfuse body logging
   for this profile. No automatic cloud fallback.
7. **Network gate:** enforce an actual container/VM egress allowlist for
   Discord/Telegram, DNS/NTP, the internal authorized LiteLLM endpoint and
   Prometheus endpoint; deny all other destinations including admin APIs,
   Docker proxy, RFC1918 metadata, IPv6 escapes, arbitrary DNS/web/SSRF.
   An ordinary Compose bridge network **does NOT enforce egress ACLs**.
   If the TrueNAS firewall cannot isolate one Docker container reliably,
   run Hermes on a separate unprivileged VM. `cap_drop` alone does not
   constitute network isolation.
8. Confirm current native TrueNAS Hermes app is stopped, or give this PoC
   entirely separate bot tokens. Check restore/snapshot plan, then review
   the Compose model without disclosing resolved secret values:

```bash
cd /mnt/cpool/compose/nabla-compose
export HERMES_IMAGE_REF='nousresearch/hermes-agent@sha256:<verified-digest>'
python3 scripts/hermes/poc_preflight.py --check
docker compose -f poc/hermes/compose.yml --profile hermes-poc config --quiet
# Only after all runtime/security gates are independently accepted:
docker compose -f poc/hermes/compose.yml --profile hermes-poc up -d
```

The `up` command is an operator action, **not** an instruction that the agent
executes automatically. Never run a plain `docker compose config` without
`--quiet` when env files might contain credentials. The POC's image
capabilities preserve just `CHOWN`, `SETUID`, `SETGID` so the official s6
supervisor can drop gateway privileges; prove the gateway process runs as
UID 10000 and has no effective Linux capabilities. If the image requires
more capabilities or mutable system paths, pause rather than using
`privileged`/root or writable system mounts.

## Exposure to other homelab applications (opt-in only)

Hermes' OpenAI-compatible API can act as an agent backend for **Open WebUI**,
**FastAPI Sample**, **n8n** and internal orchestrators, but it exposes the
agent's toolset. Enable it only after the read-only profile, independent
`API_SERVER_KEY` secret (32+ chars), private network and auth tests pass:

```bash
python3 scripts/hermes/poc_preflight.py --check --api
docker compose -f poc/hermes/compose.yml -f poc/hermes/compose.api.yml \
  --profile hermes-poc config --quiet
# Then controlled apply/acceptance separately.
```

Clients on the shared `intranet` Docker network can use
`http://hermes-poc:8642/v1` and a dedicated API bearer key. Do not publish
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

Do **not** connect OpenTerminal to Hermes in this first PoC. A later optional
`poc-ops` worker should use a **separate unprivileged workload VM/sandbox**
with no Docker socket, host mounts, TrueNAS SSH/root or shared secrets. Even
there, terminal commands are only for ephemeral development and testing.
Operations against the homelab continue through a typed external task broker
with independent approval, not OpenTerminal's arbitrary shell API.

## Observability and costs

The canonical `apps/prometheus/prometheus.yml` now has
`litellm_hermes` scrape **every 60 seconds**, filtered at ingestion to
the `hermes-poc` virtual key alias and cost/token counters. It removes
user/email/IP/hashed-key labels before storing/remote-writing to Mimir.
`apps/prometheus/rules/hermes.rules.yml` defines:
- `hermes_poc:litellm_spend_usd`, based only on observed samples;
- `hermes_poc:litellm_tokens_total`;
- `HermesPocSpendReview` when cumulative observed spend exceeds $1.50.

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

Stop only `hermes-poc`; leave the native Hermes App and dataset untouched,
revoke its bot/API/LiteLLM virtual keys, detach the optional intranet network,
preserve the isolated POC state snapshot for forensics, and roll back
Prometheus scrape/rules if necessary. Never delete shared LiteLLM, Loki,
OpenTerminal, SearXNG, Vaultwarden or Prometheus state to roll back this PoC.
