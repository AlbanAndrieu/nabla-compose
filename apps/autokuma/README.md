# AutoKuma on TrueNAS

AutoKuma is a **configuration reconciler for Uptime Kuma**, not an Uptime Kuma
server replacement. It reads the repository-generated monitor inventory and
creates/updates those monitors through an already-running Uptime Kuma API.

The former native TrueNAS Uptime Kuma App has been removed. The target
architecture is therefore two repository-owned Compose workloads:

1. **Uptime Kuma** — monitoring engine/UI, exposed on TrueNAS host port `31050`;
2. **AutoKuma** — declarative controller that reconciles generated Nabla
   monitors into Uptime Kuma.

Until the Uptime Kuma Compose service exists and `172.17.0.24:31050` is
reachable, keep AutoKuma stopped. Starting AutoKuma alone cannot provide uptime
monitoring and will fail its required `kuma.url`/connection contract.

The repository owns the desired monitor definitions under:

```text
apps/autokuma/static/generated-monitors.json
```

The TrueNAS runtime is a dedicated Custom App named `autokuma`.

## Runtime secrets

Store the Uptime Kuma connection only in:

```text
/mnt/cpool/secrets/runtime/autokuma/.env.secrets
```

Create the runtime directory and secret file:

```bash
sudo install -d -o root -g root -m 700 /mnt/cpool/secrets/runtime/autokuma
sudo install -o root -g root -m 600 /dev/null /mnt/cpool/secrets/runtime/autokuma/.env.secrets
sudoedit /mnt/cpool/secrets/runtime/autokuma/.env.secrets
```

The file contains authentication material only. The Uptime Kuma endpoint is
non-secret configuration owned by `apps/autokuma/compose.yml`, which defaults
to `http://172.17.0.24:31050`. Do not duplicate
`AUTOKUMA__KUMA__URL` in the runtime secret file.

Preferred token form:

```dotenv
AUTOKUMA__KUMA__AUTH_TOKEN=<jwt-or-auth-token>
AUTOKUMA__KUMA__TLS__VERIFY=true
```

Or username/password:

```dotenv
AUTOKUMA__KUMA__USERNAME=<username>
AUTOKUMA__KUMA__PASSWORD=<password>
AUTOKUMA__KUMA__TLS__VERIFY=true
```

Do not commit credentials. If a future HTTPS internal endpoint is selected,
review its hostname/certificate first and keep TLS verification enabled unless
a documented local exception is required.

The Compose file loads this file directly. This avoids depending on
`UPTIME_KUMA_*` variables being present in the TrueNAS middleware process when
the Custom App parses the repository include.

## Generate the Uptime Kuma JWT

AutoKuma 2.0.0 includes the `kuma` CLI. Generate a JWT from an existing Uptime
Kuma user without printing the password or token **only after Uptime Kuma has
been deployed and initialized**:

```bash
sudo bash scripts/truenas/bootstrap-autokuma-token.sh \
  --url 'http://172.17.0.24:31050' \
  --username '<Uptime Kuma username>'
```

The password is requested interactively without echo. The helper runs the
bundled `/usr/local/bin/kuma login`, extracts the returned JWT and atomically
writes the generated token plus TLS policy to
`/mnt/cpool/secrets/runtime/autokuma/.env.secrets` with mode `0600`. The URL
is used for login but is deliberately not persisted in the secret file.

Prefer the direct internal Uptime Kuma URL. Do not route this controller through
Cloudflare Access merely to reach a service on the same homelab.

## Create or update the TrueNAS Custom App

Deploy AutoKuma only after the Uptime Kuma endpoint is healthy:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/deploy-autokuma.sh
```

The helper:

- validates that the secret file exists, is non-empty and mode `0600`;
- rejects a legacy `AUTOKUMA__KUMA__URL` entry in the secret file because the
  endpoint is Compose-owned configuration;
- requires either `AUTOKUMA__KUMA__AUTH_TOKEN` or username/password;
- validates the repository Compose without expanding secrets;
- refuses an empty generated monitor inventory;
- runs `app.create` when `autokuma` does not yet exist;
- otherwise runs `app.update autokuma` followed by `app.redeploy autokuma`;
- waits for the `autokuma` container and prints only non-secret runtime state.

The canonical TrueNAS include is:

```yaml
include:
  - /mnt/cpool/compose/nabla-compose/apps/autokuma/compose.yml
```

Do not paste a duplicate Compose definition into the TrueNAS UI. The repository
include keeps `./static` resolved relative to `apps/autokuma/compose.yml`.

## pfSense exporter monitor policy

AutoKuma must not use the pfSense Exporter `/metrics?target=...` endpoint as a
health check. That endpoint fans out into pfREST calls on the constrained
firewall.

The generated monitor therefore checks only:

```text
tcp://172.17.0.24:9945
```

Prometheus is the only component allowed to trigger the exporter collectors in
steady state.

## Acceptance

First prove Uptime Kuma itself:

```bash
curl -fsS --max-time 5 http://172.17.0.24:31050/ >/dev/null &&
echo 'Uptime Kuma reachable'
```

Then, after AutoKuma deployment:

```bash
midclt call app.query '[["id","=","autokuma"]]' |
jq '.[0] | {id,state,active_workloads}'

docker ps --filter 'name=^/autokuma$' \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

docker logs --since 5m autokuma 2>&1 |
tail -100
```

Finally verify in Uptime Kuma that the generated monitors are tagged `Nabla`
and that the pfSense Exporter monitor is TCP-only. Keep
`AUTOKUMA__ON_DELETE=keep` during migration so an incomplete first
reconciliation cannot delete unmanaged monitors.
