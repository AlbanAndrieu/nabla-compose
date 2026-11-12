# Plumber — PostgreSQL TLS 1.3 (homelab)

Status: planned / currently unused. Temporary downtime and a failed startup
until the lab PKI is ready are acceptable. The shared PostgreSQL service
must be configured for TLS 1.3 with a valid server certificate and SCRAM
authentication, separately from these Plumber clients.

Both `plumber-api` and `plumber-worker` now use:

- `JOBS_DB_SSLMODE=prefer`, a shortcut approved on 11/11/2026 like FastAPI
  Sample: the shared server still runs `ssl=off`, so `verify-full` cannot
  connect. Restore `verify-full` with the TLS 1.3 roadmap item;
- `PGSSLROOTCERT=/etc/nabla/pki/postgres-ca.crt` for libpq/pgx-compatible
  clients, with a read-only PEM CA mount from
  `/mnt/cpool/secrets/runtime/postgres/tls/ca.crt`;
- `JOBS_DB_HOST` defaulting to `172.17.0.24`: the shared PostgreSQL App is
  not on the `intranet` network;
- `JOBS_REDIS_PASSWORD` from `nabla/prod/plumber`, equal to the shared
  Redis `REDIS_AUTH` (Redis refuses unauthenticated clients);
- images pinned by digest (`backend:v2.44.1`, `frontend:v2.37.3`), updated
  by Renovate.

**Certificate name verification (once TLS is on):** the server certificate
must include the exact `JOBS_DB_HOST` as a DNS or IP SAN, or change that
host to a name covered by its SAN. Never set `sslmode=disable`; `prefer`
is only the temporary shortcut above. A CA file is public and is not a
server private key.

**Runtime check required:** the exact Plumber backend PostgreSQL
driver/DSN construction has not yet been exercised. Verify that
`JOBS_DB_SSLMODE` and `PGSSLROOTCERT` are respected, including on
worker connections, before claiming TLS is enforced. If the backend
ignores `PGSSLROOTCERT`, implement its upstream-specific root CA setting
rather than weakening `verify-full`.

After initial deployment, check the PostgreSQL side:

```sql
SELECT a.usename, a.application_name, a.client_addr,
       s.ssl, s.version, s.cipher
FROM pg_stat_activity a
JOIN pg_stat_ssl s USING (pid)
WHERE a.datname = 'jobs';
```

Only accept TCP application sessions reporting `ssl=true` and
`version='TLSv1.3'` when the server is configured with
`ssl_min_protocol_version='TLSv1.3'`.

The public CA may be rotated by distributing a new trust bundle and
restarting these **currently unused** services. Runtime secrets stay
in `/mnt/cpool/secrets/runtime/plumber/.env.secrets` (never in Git).

See [PostgreSQL/FIPS/TLS roadmap](../../docs/security/postgresql-fips-tls13-vault-oauth-20261110.md).
