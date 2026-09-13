# Cyberbro on TrueNAS

Cyberbro is deployed as a TrueNAS Custom App from `apps/cyberbro/compose.yml` together with its optional MCP bridge.

## Runtime endpoints

- Cyberbro UI/API: `http://172.17.0.24:5100`
- Cyberbro MCP (streamable HTTP): `http://172.17.0.24:8013/mcp`

The MCP endpoint has no upstream authentication mechanism. It is therefore bound to the TrueNAS LAN address only and must not be exposed through a public reverse proxy without an authentication layer.

## Canonical TrueNAS layout

The deployment helper discovers the Compose bind mounts and creates the application dataset through TrueNAS middleware with the repository `APPS` preset contract:

```text
/mnt/cpool/cyberbro/data
/mnt/cpool/cyberbro/logs
```

Runtime environment material is separate and root-only:

```text
/mnt/cpool/secrets/runtime/cyberbro/.env
/mnt/cpool/secrets/runtime/cyberbro/.env.secrets
```

`.env` contains non-secret Cyberbro settings. `.env.secrets` contains provider credentials; when no premium provider is configured it contains the explicit empty optional-provider contract rather than an empty placeholder. Do not put live credentials under `apps/cyberbro/`.

## Bootstrap environment and secrets

Cyberbro can run with its free engines. The Vaultwarden metadata contract declares every optional provider credential under `nabla/prod/cyberbro` and maps imported variables through the `CYBERBRO_` namespace.

The initial Vaultwarden item contains 27 declared secret mappings. Empty optional fields are a valid baseline: they mean the corresponding external provider has not been enrolled yet and do not block Cyberbro free-engine startup.

Create or validate the canonical runtime files on TrueNAS with:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo -E bash scripts/truenas/bootstrap-cyberbro-env.sh --apply
sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check
```

### `bw` is optional on TrueNAS

The TrueNAS runtime does **not** require the Bitwarden CLI. When `/mnt/cpool/secrets/runtime/cyberbro/.env.secrets` already exists and is non-empty, `bootstrap-cyberbro-env.sh --apply` preserves that file if `BW_SESSION` or `bw` is unavailable. If the canonical secret file does not exist yet, the bootstrap creates the explicit empty optional-provider baseline so the free Cyberbro engines can still start.

Secrets stored elsewhere on TrueNAS are not discovered implicitly: stage the Cyberbro-native keys into the canonical `.env.secrets` file first. Existing values already materialized at the canonical path are preserved.

### Keep `BW_SESSION` unprivileged

Vaultwarden rendering on the workstation must run as the logged-in operator, **not** through `sudo`. Do not propagate `BW_SESSION` into root with `sudo -E`; root does not need the Bitwarden session.

The renderer creates new secret directories as `0700`, preserves permissions on existing shared directories such as `/tmp`, and always writes the final file atomically with mode `0600`. When the target is inside a Git worktree, rendering is allowed only if that exact target is ignored by Git; an ad-hoc trackable path such as `./cyberbro.env.secrets` is refused.

### Recommended flow when `bw` is installed only on the workstation

Run Vaultwarden operations from the workstation checkout. For a new item, export only the providers you intentionally configure and perform a dry-run before applying:

```bash
export BW_SESSION="$(bw unlock --raw)"
export CYBERBRO_VIRUSTOTAL='...'
export CYBERBRO_SHODAN='...'

python scripts/secrets/import_env_to_bitwarden.py --app cyberbro
python scripts/secrets/import_env_to_bitwarden.py --app cyberbro --apply
```

For an existing `nabla/prod/cyberbro` item, update only explicitly exported provider values and preserve omitted optional fields:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app cyberbro --update-existing
python scripts/secrets/import_env_to_bitwarden.py --app cyberbro --apply --update-existing
```

Explicitly exporting an optional source as an empty string clears that provider deliberately. Omitting the source variable preserves its existing Vaultwarden value during an update.

Materialize the item on the workstation and transfer the root-only runtime file to TrueNAS:

```bash
umask 077
python scripts/secrets/render_from_bitwarden.py \
  --app cyberbro \
  --output-file /tmp/cyberbro.env.secrets

stat -c '%a %n' /tmp/cyberbro.env.secrets
grep -c '^[A-Z0-9_]*=' /tmp/cyberbro.env.secrets
# Expected: mode 600 and 27 mappings. Do not cat the file.

scp /tmp/cyberbro.env.secrets <truenas-host>:/tmp/cyberbro.env.secrets
rm -f /tmp/cyberbro.env.secrets
```

If an older renderer forced you to create `./cyberbro.env.secrets` in the checkout, remove it before any Git staging operation:

```bash
rm -f ./cyberbro.env.secrets
git status --short
```

Never use `git add -f` for generated secret material.

Then on TrueNAS:

```bash
sudo install -d -o root -g root -m 700 /mnt/cpool/secrets/runtime/cyberbro
sudo install -o root -g root -m 600 /tmp/cyberbro.env.secrets \
  /mnt/cpool/secrets/runtime/cyberbro/.env.secrets
sudo rm -f /tmp/cyberbro.env.secrets

cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --apply
sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check
```

The service-specific `scripts/truenas/import-cyberbro-secrets.sh` helper remains available for hosts where `bw` is installed in the canonical TrueNAS checkout, but it is not required by the workstation-only workflow above.

## Provider onboarding backlog

Provider enrollment is intentionally separate from the Cyberbro deployment transaction. Create accounts, tenants, applications or API tokens only as required by each provider; store resulting values only in Vaultwarden and update `nabla/prod/cyberbro` through the importer. Do not paste provider credentials into GitHub issues, PRs, shell history or documentation.

The current provider inventory is:

- AbuseIPDB — `ABUSEIPDB`;
- AlienVault OTX — `ALIENVAULT`;
- Criminal IP — `CRIMINALIP_API_KEY`;
- CrowdStrike Falcon — `CROWDSTRIKE_CLIENT_ID`, `CROWDSTRIKE_CLIENT_SECRET`;
- DFIR-IRIS — `DFIR_IRIS_API_KEY`;
- Google Programmable Search / CSE — `GOOGLE_CSE_CX`, `GOOGLE_CSE_KEY`;
- Google Safe Browsing — `GOOGLE_SAFE_BROWSING`;
- Hister — `HISTER_TOKEN`;
- ipapi — `IPAPI`;
- IPinfo — `IPINFO`;
- Microsoft Defender for Endpoint — `MDE_CLIENT_ID`, `MDE_CLIENT_SECRET`, `MDE_TENANT_ID`;
- MISP — `MISP_API_KEY`, `MISP_FEEDBACK_TOKEN`;
- OpenCTI — `OPENCTI_API_KEY`;
- Ransomware.live — `RANSOMWARE_LIVE_API_KEY`;
- ReversingLabs Analyze — `RL_ANALYZE_API_KEY`;
- Rosti — `ROSTI_API_KEY`;
- Shodan — `SHODAN`;
- Spur — `SPUR_US`;
- ThreatFox — `THREATFOX`;
- VirusTotal — `VIRUSTOTAL`;
- WebScout — `WEBSCOUT`;
- optional outbound proxy configuration — `PROXY_URL` (configuration, not a provider account).

Onboard in bounded batches and validate the corresponding Cyberbro engine after each credential set. Prefer free/read-only API plans first, least-privilege application identities where OAuth/client credentials are involved, and dedicated homelab identities rather than personal production credentials.

## TrueNAS Custom App deployment

Use the service-specific deployer rather than reproducing the middleware calls manually:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo -E bash scripts/truenas/deploy-cyberbro.sh
```

The deployer performs, in order:

1. `cpool/cyberbro` dataset creation/validation through `pool.dataset.create` with the repository Apps preset contract;
2. `.env` and `.env.secrets` materialization and permission validation;
3. Compose validation without resolving secrets;
4. generated topology/Homarr/Gatus/AutoKuma consistency checks;
5. TrueNAS `app.create` or `app.update` using the supported Custom App YAML `include:` wrapper;
6. wait for the TrueNAS app to become `RUNNING`, Cyberbro to become Docker `healthy`, and the MCP container to be running;
7. direct HTTP/MCP diagnostics and final `curl` acceptance;
8. downstream AutoKuma reconciliation into Uptime Kuma, then Gatus and Homarr redeployment.

Prometheus is deliberately not restarted by this Cyberbro deployment because Cyberbro exposes no documented Prometheus metrics endpoint and this PR does not modify `apps/prometheus` configuration.

## Failure diagnostics

The deployment helper automatically invokes:

```bash
sudo bash scripts/truenas/diagnose-cyberbro.sh
```

The diagnostic is read-only. It inspects:

- `app.query` and recent TrueNAS application jobs;
- `/var/log/app_lifecycle.log` evidence appended after the deployment lifecycle mark;
- Docker state, health and restart counts for `cyberbro` and `mcp-cyberbro`;
- bounded container logs when a container is missing/unhealthy;
- the absence of a database dependency in the current Cyberbro contract;
- final HTTP and MCP listener probes;
- bounded Docker service, TrueNAS middleware and filtered system-journal evidence when acceptance fails.

Review those bounded logs locally before sharing them, because upstream provider errors can include sensitive request metadata.

## Vaultwarden operational debt observed during bootstrap

Two independent Vaultwarden observations remain tracked as platform debt and are not Cyberbro blockers:

1. a transient Cloudflare `502 origin_bad_gateway` occurred while `bw` refreshed an access token after the Cyberbro item had already been created. Direct TrueNAS origin checks were healthy and a later `bw sync` succeeded. Keep post-write sync failure warning-only, verify the exact item before retrying an apply, and investigate recurrence by correlating Cloudflare, reverse-proxy/tunnel and Vaultwarden request latency;
2. Vaultwarden icon retrieval attempted TLS against raw IP `82.66.4.247` while the presented certificate was valid only for `*.int.albandrieu.com`. Identify the originating vault item/URI or redirect and replace raw-IP HTTPS access with a DNS name covered by the intended certificate, or otherwise suppress that icon-fetch path. This certificate-name mismatch is distinct from the transient `bw` 502.

## LiteLLM MCP integration

LiteLLM registers Cyberbro through:

```yaml
mcp_servers:
  cyberbro:
    transport: http
    url: os.environ/CYBERBRO_MCP_URL
```

The default URL is `http://172.17.0.24:8013/mcp`. LiteLLM access policy remains authoritative; the configuration does not grant the Cyberbro MCP server to every API key automatically.

## Observability

Cyberbro is observed through its container healthcheck, the generated Gatus/AutoKuma monitor contracts, Homarr catalog metadata, persistent application logs and the MCP port check. No Prometheus relation is declared because upstream does not document a metrics endpoint.
