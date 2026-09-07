# Akvorado network-flow observability

Akvorado replaces the resource-heavy native ntopng workload on the Netgate 1100
for homelab flow collection.

## Data path

```text
pfSense Plus pflow/IPFIX
  -> 172.17.0.24:2055/udp
  -> Akvorado Inlet
  -> shared Kafka kafka:9092, dedicated topic akvorado-flows
  -> Akvorado Outlet
  -> shared ClickHouse clickhouse:9000, dedicated database akvorado
  -> Akvorado Console on 172.17.0.24:31056
```

The Sentry and Akvorado workloads share the Kafka broker but never share topics.
Akvorado uses the main shared ClickHouse service, not the temporary
Sentry-compatible ClickHouse instance.

## TrueNAS preparation

Create persistent paths:

```bash
sudo install -d -m 700 /mnt/cpool/akvorado
sudo install -d -m 750 /mnt/cpool/akvorado/run /mnt/cpool/akvorado/console
```

Create `/mnt/cpool/akvorado/.env.secrets` with mode `0600`:

```dotenv
AKVORADO_CLICKHOUSE_PASSWORD=<dedicated-secret>
```

Prepare the ClickHouse identity before starting Akvorado:

```sql
CREATE DATABASE IF NOT EXISTS akvorado;
CREATE USER IF NOT EXISTS akvorado
IDENTIFIED WITH sha256_password BY '<dedicated-secret>';

GRANT ALL ON akvorado.* TO akvorado;
```

The grant is intentionally database-scoped. Do not grant `akvorado` global
`*.*` privileges or `WITH GRANT OPTION`.

## pfSense

Use the native **Firewall -> Packet Flow Data** exporter:

- source: `172.17.0.1`;
- destination: `172.17.0.24:2055`;
- protocol: IPFIX (version 10);
- observation domain: `1`.

The TrueNAS host should observe packets with:

```bash
sudo tcpdump -ni br0 'udp dst port 2055 and src host 172.17.0.1'
```

## Validation

Before runtime deployment:

```bash
docker compose -f apps/akvorado/compose.yml config --quiet --no-interpolate --no-env-resolution
python scripts/generate-service-topology.py
python scripts/generate-service-topology.py --check
bash scripts/quality-gate.sh
```

After deployment, validate that the UDP listener, Kafka topic, ClickHouse
database/tables, and console are all populated before retiring any legacy flow
collector configuration.
