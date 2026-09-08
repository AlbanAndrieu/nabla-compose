# Keycloak on TrueNAS

This repository-managed Keycloak replaces the removed empty native TrueNAS
application while keeping the established public hostname:

```text
https://keycloak.albandrieu.com
```

The previous application had no identity data to migrate. The existing
`/mnt/cpool/keycloak` dataset is retained for runtime secrets and future
providers/themes, but **Keycloak does not run a dedicated PostgreSQL container**.

## Database contract

Keycloak uses the shared PostgreSQL service:

```text
host     172.17.0.24
port     5432
database keycloak
role     keycloak
```

Create the dedicated database and role in the global PostgreSQL instance before
registering the TrueNAS Custom App. Use an operator/admin PostgreSQL identity and
do not print the generated password:

```bash
KEYCLOAK_DB_PASSWORD="$(openssl rand -hex 32)"

psql -h 172.17.0.24 -U postgres -d postgres \
  --set=ON_ERROR_STOP=1 \
  --set=keycloak_password="${KEYCLOAK_DB_PASSWORD}" <<'SQL'
SELECT format(
  'CREATE ROLE keycloak LOGIN PASSWORD %L',
  :'keycloak_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'keycloak'
) \gexec

SELECT 'CREATE DATABASE keycloak OWNER keycloak'
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = 'keycloak'
) \gexec

ALTER DATABASE keycloak OWNER TO keycloak;
SQL
```

If the role already exists, rotate it deliberately with:

```bash
psql -h 172.17.0.24 -U postgres -d postgres \
  --set=ON_ERROR_STOP=1 \
  --set=keycloak_password="${KEYCLOAK_DB_PASSWORD}" \
  -c "ALTER ROLE keycloak PASSWORD :'keycloak_password';"
```

## Runtime secrets

The Compose file consumes:

```text
/mnt/cpool/keycloak/.env.secrets
```

with:

```text
KC_DB_PASSWORD=<password matching the global PostgreSQL keycloak role>
KC_BOOTSTRAP_ADMIN_PASSWORD=<one-time initial administrator password>
```

The repository Vaultwarden manifest maps the migration-friendly import names
`KEYCLOAK_DB_PASSWORD` and `KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD` to those
container-facing Keycloak variables.

Render the file with:

```bash
python scripts/secrets/render_from_bitwarden.py \
  --app keycloak \
  --output-file /mnt/cpool/keycloak/.env.secrets
chmod 600 /mnt/cpool/keycloak/.env.secrets
```

The bootstrap administrator password is used to create the initial local
break-glass administrator. Keep that local account until GitHub SSO is proven.

## Reverse proxy and management boundary

Application/OIDC traffic is available on:

```text
http://172.17.0.24:30238
```

with canonical external hostname:

```text
https://keycloak.albandrieu.com
```

The Keycloak management interface is bound only to the trusted LAN:

```text
http://172.17.0.24:30239
```

Do **not** expose port `30239` through Cloudflare, HAProxy or Traefik. It carries
health and metrics endpoints.

## TrueNAS Custom App

After the database and secret file exist:

```bash
KEYCLOAK_WRAPPER="$(
  cat <<'EOF'
include:
  - /mnt/cpool/compose/nabla-compose/apps/keycloak/compose.yml
EOF
)"

sudo midclt call -j app.create "$(
  jq -cn \
    --arg compose "${KEYCLOAK_WRAPPER}" \
    '{
      app_name: "keycloak",
      custom_app: true,
      custom_compose_config_string: $compose
    }'
)"
```

## Acceptance

```bash
curl -fsS http://172.17.0.24:30239/health/ready
curl -fsS http://172.17.0.24:30239/metrics | head
curl -fsS \
  http://172.17.0.24:30238/realms/master/.well-known/openid-configuration |
jq '{issuer,authorization_endpoint,token_endpoint}'
```

The issuer must resolve to `https://keycloak.albandrieu.com/realms/master`,
not the internal host/port.

Only after this is healthy should the public reverse-proxy route and GitHub
identity provider be validated.
