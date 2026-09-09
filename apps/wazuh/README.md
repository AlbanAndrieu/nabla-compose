# Wazuh

Wazuh 4.14.7 runs with its native manager/indexer/dashboard stack. This is
intentional: the Wazuh dashboard/indexer lifecycle is version-coupled and must
not be pointed at the OpenRAG OpenSearch 3.x instance.

A Logstash forwarding sidecar can copy Wazuh alerts to the shared
`opensearch-security` 2.19.5 service used by Graylog. It is profile-gated
under `forwarding` and deliberately disabled during the core
manager/indexer/dashboard stabilization gate.

## TrueNAS runtime bootstrap

The runtime keeps API credentials and TLS private keys outside Git:

```text
/mnt/cpool/wazuh/
├── .env.secrets
└── certs/
    ├── root-ca.pem
    ├── root-ca-manager.pem
    ├── wazuh.indexer.pem
    ├── wazuh.indexer-key.pem
    ├── admin.pem
    ├── admin-key.pem
    ├── wazuh.manager.pem
    ├── wazuh.manager-key.pem
    ├── wazuh.dashboard.pem
    └── wazuh.dashboard-key.pem
```

Bootstrap them without printing the generated API password:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-wazuh.sh --apply
```

`app.update` is already the deployment job for an existing Custom App. The
helper deliberately does **not** call `app.redeploy` immediately afterwards;
doing both starts a second lifecycle cycle and can reset startup convergence.

The helper:

- removes only **empty directories** previously created at legacy PEM file paths
  by Docker short-bind syntax;
- refuses to delete a non-empty legacy directory;
- creates `/mnt/cpool/wazuh/.env.secrets` mode `0600` and generates
  `API_PASSWORD` only when absent;
- generates the upstream Wazuh 4.14 certificate set with
  `wazuh/wazuh-certs-generator:0.0.4`;
- refuses a partial certificate set rather than mixing old and new keys;
- verifies every required PEM is a regular non-empty file;
- validates the repository Compose without expanding secrets.

Read-only validation:

```bash
sudo bash scripts/truenas/bootstrap-wazuh.sh --check
```

The production Compose uses long bind syntax with
`bind.create_host_path: false`. A missing PEM therefore fails immediately
instead of silently creating a directory and later producing the OCI
"not a directory" mount error.

The manager and dashboard read the shared container-facing `API_PASSWORD`
from `/mnt/cpool/wazuh/.env.secrets`. Do not set
`WAZUH_API_PASSWORD` as a Compose interpolation variable.

The upstream bootstrap users in `internal_users.yml` still use the reviewed
Wazuh sample indexer/dashboard passwords in this phase. Do **not** replace
`WAZUH_INDEXER_PASSWORD` or `WAZUH_DASHBOARD_PASSWORD` with random values
until the corresponding hashes in `internal_users.yml` are rotated in the
same reviewed change.

## TrueNAS deployment

Use the canonical helper instead of calling `app.update` directly:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/deploy-wazuh.sh
```

The helper:

1. runs `bootstrap-wazuh.sh --apply`;
2. runs the fail-closed bootstrap `--check`;
3. validates the Compose definition without expanding secrets;
4. creates or updates the TrueNAS Custom App;
5. waits for the core manager/indexer/dashboard path;
6. finishes with `diagnose-wazuh.sh --check`.

Read-only runtime acceptance:

```bash
sudo bash scripts/truenas/diagnose-wazuh.sh --check
```

The diagnostic requires the TrueNAS app to be `RUNNING`, all three core
containers to be running, and the loopback HTTPS listeners for the indexer,
manager API and dashboard to answer. HTTP 401/403 is accepted for unauthenticated
management probes because it proves the TLS/API listener without printing or
using credentials.

The optional `wazuh-forwarder` is not part of this first gate. Keep the
`forwarding` profile disabled until the manager -> indexer -> dashboard path
is stable and the shared `nabla-security` / OpenSearch forwarding path has a
separate acceptance test.

Do not expose the dashboard beyond the trusted LAN until API/indexer/dashboard
credentials have been rotated together and the complete manager -> indexer ->
dashboard path is healthy.
