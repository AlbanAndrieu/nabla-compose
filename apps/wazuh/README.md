# Wazuh

Wazuh 4.14.7 runs with its native manager/indexer/dashboard stack. This is
intentional: the Wazuh dashboard/indexer lifecycle is version-coupled and must
not be pointed at the OpenRAG OpenSearch 3.x instance.

A Logstash forwarding sidecar copies Wazuh alerts to the shared
`opensearch-security` 2.19.5 service used by Graylog.

## Bootstrap

Generate the Wazuh TLS material once:

```bash
docker compose -f generate-indexer-certs.yml run --rm generator
```

Then provide `WAZUH_API_PASSWORD` and start the normal `compose.yml`.

The upstream bootstrap users in `internal_users.yml` use Wazuh's documented
sample passwords. Rotate the indexer/dashboard credentials before exposing the
dashboard beyond the trusted LAN.
