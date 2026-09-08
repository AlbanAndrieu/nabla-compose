# Wazuh

Wazuh 4.14.7 runs with its native manager/indexer/dashboard stack. This is
intentional: the Wazuh dashboard/indexer lifecycle is version-coupled and must
not be pointed at the OpenRAG OpenSearch 3.x instance.

A Logstash forwarding sidecar copies Wazuh alerts to the shared
`opensearch-security` 2.19.5 service used by Graylog.

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

Use the canonical deploy helper:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/deploy-wazuh.sh
```

It always runs `bootstrap-wazuh.sh --apply` first. Therefore a missing
`/mnt/cpool/wazuh/.env.secrets` is created before TrueNAS parses the Compose,
`API_PASSWORD` is generated without being printed, TLS material is generated
or verified, and only then are `app.update wazuh` and `app.redeploy wazuh`
executed.

Do not call `app.update wazuh` directly on a fresh host before this bootstrap:
the Compose intentionally declares the runtime env file as `required: true`
and will fail closed when it is absent.

Then inspect only the Wazuh project:

```bash
midclt call app.query \
  '[["id","=","wazuh"]]' |
jq '.[0] | {id,state,active_workloads}'

docker ps -a \
  --filter 'label=com.docker.compose.project=ix-wazuh' \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
```

Do not expose the dashboard beyond the trusted LAN until API/indexer/dashboard
credentials have been rotated together and the complete manager -> indexer ->
dashboard path is healthy.
