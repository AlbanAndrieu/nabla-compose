# OpenSearch exporters

Two Prometheus Community exporters are provided:

- `opensearch-exporter` monitors the existing OpenRAG/OpenSearch instance.
- `opensearch-security-exporter` monitors the isolated OpenSearch 2.19.5 instance
  shared by Graylog and the Wazuh forwarding pipeline.

Set `OPENSEARCH_EXPORTER_URI` to a URL containing a **dedicated read-only
monitoring account**, for example:

```text
https://metrics-user:REDACTED@172.17.0.24:9200
```

Do not use the OpenSearch `admin` account for monitoring.
