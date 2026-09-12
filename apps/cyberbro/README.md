# Cyberbro on TrueNAS

Cyberbro is deployed as a TrueNAS Custom App from `apps/cyberbro/compose.yml` together with its optional MCP bridge.

## Runtime endpoints

- Cyberbro UI/API: `http://172.17.0.24:5100`
- Cyberbro MCP (streamable HTTP): `http://172.17.0.24:8013/mcp`

The MCP endpoint has no upstream authentication mechanism. It is therefore bound to the TrueNAS LAN address only and must not be exposed through a public reverse proxy without an authentication layer.

## Persistent data

Repository bootstrap discovers the Compose bind mounts and owns the top-level dataset:

```text
/mnt/cpool/cyberbro/data
/mnt/cpool/cyberbro/logs
```

The secret materialization is separate and root-only:

```text
/mnt/cpool/secrets/runtime/cyberbro/.env.secrets
```

Do not put live credentials under `apps/cyberbro/`.

## Secrets

Cyberbro can start without provider API credentials and keeps its free engines available. The metadata-only Vaultwarden contract nevertheless declares every supported provider credential under the item:

```text
nabla/prod/cyberbro
```

All fields are optional and rotatable. Import variables are namespaced with `CYBERBRO_` so they do not collide with credentials used by other applications.

Examples:

```bash
export CYBERBRO_VIRUSTOTAL='...'
export CYBERBRO_SHODAN='...'
export CYBERBRO_ABUSEIPDB='...'
```

Unset optional provider variables are imported as empty hidden fields. Values are never printed by the importer.

Configure and unlock the Bitwarden CLI, then preview the item creation:

```bash
bw config server https://vaultwarden.albandrieu.com
export BW_SESSION="$(bw unlock --raw)"
python scripts/secrets/import_env_to_bitwarden.py --app cyberbro
```

Create the item only after reviewing the dry-run:

```bash
python scripts/secrets/import_env_to_bitwarden.py --app cyberbro --apply
```

Render the runtime file on TrueNAS:

```bash
sudo install -d -o root -g root -m 700 /mnt/cpool/secrets/runtime/cyberbro
python scripts/secrets/render_from_bitwarden.py \
  --app cyberbro \
  --output-file /mnt/cpool/secrets/runtime/cyberbro/.env.secrets
sudo chown root:root /mnt/cpool/secrets/runtime/cyberbro/.env.secrets
sudo chmod 600 /mnt/cpool/secrets/runtime/cyberbro/.env.secrets
```

Then validate the repository-owned runtime prerequisites:

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check cyberbro
```

## LiteLLM MCP integration

LiteLLM registers Cyberbro as an HTTP MCP server through:

```yaml
mcp_servers:
  cyberbro:
    transport: http
    url: os.environ/CYBERBRO_MCP_URL
```

The default URL is `http://172.17.0.24:8013/mcp`. LiteLLM access policy remains authoritative; the configuration does not grant the Cyberbro MCP server to every API key automatically.

The MCP server exposes the upstream Cyberbro tools for submitting observables, checking analysis state, retrieving results, enumerating engines, and getting the Cyberbro web URL.

## Observability

Cyberbro currently has no documented Prometheus metrics endpoint, so the Compose file does not invent one. The service is observed through:

- a container HTTP healthcheck against `/`;
- `x-nabla.monitoring` HTTP status metadata for the UI/API;
- a TCP/port monitor for the MCP endpoint;
- persistent application logs under `/mnt/cpool/cyberbro/logs`.

The generated Nabla catalog and its monitoring consumers remain the source for downstream Gatus/AutoKuma/Homarr integration.
