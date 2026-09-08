# AutoKuma on TrueNAS

AutoKuma reconciles the repository-generated monitor inventory into the existing
Uptime Kuma instance. The repository owns the desired monitor definitions under:

```text
apps/autokuma/static/generated-monitors.json
```

The TrueNAS runtime is a dedicated Custom App named `autokuma`.

## Runtime secrets

Store the Uptime Kuma connection only in:

```text
/mnt/cpool/autokuma/.env.secrets
```

Create the runtime directory and secret file:

```bash
sudo install -d -o root -g root -m 700 /mnt/cpool/autokuma
sudo install -o root -g root -m 600 /dev/null /mnt/cpool/autokuma/.env.secrets
sudoedit /mnt/cpool/autokuma/.env.secrets
```

The file must contain `AUTOKUMA__KUMA__URL` plus one authentication method.

Preferred token form:

```dotenv
AUTOKUMA__KUMA__URL=https://uptime-kuma.example.internal
AUTOKUMA__KUMA__AUTH_TOKEN=<jwt-or-auth-token>
AUTOKUMA__KUMA__TLS__VERIFY=true
```

Or username/password:

```dotenv
AUTOKUMA__KUMA__URL=https://uptime-kuma.example.internal
AUTOKUMA__KUMA__USERNAME=<username>
AUTOKUMA__KUMA__PASSWORD=<password>
AUTOKUMA__KUMA__TLS__VERIFY=true
```

Do not commit the real URL credential set. If the selected internal endpoint
uses a certificate that cannot be validated by that hostname, review the
endpoint/certificate first; use `AUTOKUMA__KUMA__TLS__VERIFY=false` only as an
explicit local exception.

The Compose file loads this file directly. This avoids depending on
`UPTIME_KUMA_*` variables being present in the TrueNAS middleware process when
the Custom App parses the repository include.

## Generate the Uptime Kuma JWT

AutoKuma 2.0.0 includes the `kuma` CLI. Generate a JWT from an existing Uptime
Kuma user without printing the password or token:

```bash
sudo bash scripts/truenas/bootstrap-autokuma-token.sh \
  --url '<internal Uptime Kuma URL>' \
  --username '<Uptime Kuma username>'
```

The password is requested interactively without echo. The helper runs the
bundled `/usr/local/bin/kuma login`, extracts the returned JWT and atomically
writes only:

```dotenv
AUTOKUMA__KUMA__URL=<selected URL>
AUTOKUMA__KUMA__AUTH_TOKEN=<generated JWT>
AUTOKUMA__KUMA__TLS__VERIFY=true
```

to `/mnt/cpool/autokuma/.env.secrets` mode `0600`.

Prefer an internal URL that reaches Uptime Kuma directly. Do not route this
controller through Cloudflare Access merely to reach a service on the same
homelab. If the reviewed internal endpoint intentionally uses a certificate
that cannot be validated, pass `--tls-no-verify`; otherwise keep TLS
verification enabled.

## Create or update the TrueNAS Custom App

Use the idempotent migration helper:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/deploy-autokuma.sh
```

The helper:

- validates that the secret file exists, is non-empty and mode `0600`;
- requires `AUTOKUMA__KUMA__URL`;
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

After deployment:

```bash
midclt call app.query   '[["id","=","autokuma"]]' |
jq '.[0] | {id,state,active_workloads}'

docker ps --filter 'name=^/autokuma$'   --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

docker logs --since 5m autokuma 2>&1 |
tail -100
```

Then verify in Uptime Kuma that the generated monitors are tagged `Nabla` and
that the pfSense Exporter monitor is TCP-only. Keep `AUTOKUMA__ON_DELETE=keep`
during migration so an incomplete first reconciliation cannot delete unmanaged
monitors.
