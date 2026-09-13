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

Create the canonical runtime files with:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo -E bash scripts/truenas/bootstrap-cyberbro-env.sh --apply
sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check
```

If `BW_SESSION` and `bw` are available, the bootstrap tries to render the existing Vaultwarden item. Otherwise it writes the explicit optional-provider baseline with empty values, which keeps the free Cyberbro engines functional without inventing credentials.

To populate provider secrets, import only variables you intentionally exported, then rerun the bootstrap so the canonical `.env.secrets` is rendered from Vaultwarden:

```bash
export BW_SESSION="$(bw unlock --raw)"
export CYBERBRO_VIRUSTOTAL='...'
export CYBERBRO_SHODAN='...'

python scripts/secrets/import_env_to_bitwarden.py --app cyberbro
python scripts/secrets/import_env_to_bitwarden.py --app cyberbro --apply

sudo -E bash scripts/truenas/bootstrap-cyberbro-env.sh --apply
```

If the Vaultwarden item already exists, review the mapping first and use `--update-existing` explicitly rather than overwriting it implicitly.

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
- Docker state, health and restart counts for `cyberbro` and `mcp-cyberbro`;
- bounded container logs when a container is missing/unhealthy;
- the absence of a database dependency in the current Cyberbro contract;
- final HTTP and MCP listener probes;
- bounded Docker service and TrueNAS middleware evidence when acceptance fails.

Review those bounded logs locally before sharing them, because upstream provider errors can include sensitive request metadata.

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
