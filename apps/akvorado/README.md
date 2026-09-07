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

Use native **Firewall -> Packet Flow Data** / pflow exporters. The local
Akvorado path is:

- source: `172.17.0.1`;
- destination: `172.17.0.24:2055`;
- protocol: IPFIX (version 10);
- observation domain: `1`.

A second native pflow exporter sends the same PF state telemetry to Cloudflare
Network Flow from the WAN address `82.66.4.247` to
`162.159.65.1:2055/udp` with observation domain `2`. Legacy softflowd and
native ntopng stay disabled on the memory-constrained Netgate 1100.

The TrueNAS host should observe packets with:

```bash
sudo tcpdump -ni br0 'udp dst port 2055 and src host 172.17.0.1'
```

## Prometheus / NetFlow pipeline monitoring

Akvorado exposes native Prometheus metrics from each component. The deployment
publishes only the two flow-path metric endpoints needed by the TrueNAS
Prometheus instance:

```text
Akvorado Inlet   172.17.0.24:31057/api/v0/metrics
Akvorado Outlet  172.17.0.24:31058/api/v0/metrics
```

These ports are bound to the TrueNAS LAN address. Do not expose them to WAN.

Prometheus scrapes the endpoints as:

```text
job="akvorado_inlet"
job="akvorado_outlet"
```

Stable recording rules provide the bounded flow-monitoring contract:

```promql
nabla:telemetry:akvorado_inlet_up
nabla:telemetry:akvorado_outlet_up
nabla:network_flow:pfsense_packets_per_second
nabla:network_flow:pfsense_bytes_per_second
nabla:network_flow:pfsense_kafka_messages_per_second
nabla:network_flow:outlet_kafka_messages_per_second
nabla:network_flow:clickhouse_flows_per_second
nabla:network_flow:clickhouse_batches_per_second
```

Alerts cover:

- Inlet or Outlet scrape loss;
- exporter `172.17.0.1` disappearing from Akvorado;
- a known pfSense exporter becoming silent;
- UDP receive errors;
- kernel UDP receive-queue drops;
- Kafka publish errors;
- Outlet Kafka consumer stalls;
- ClickHouse insertion errors;
- Inlet traffic increasing while Outlet ClickHouse batches stall.

The provisioned Grafana dashboard
`pfSense NetFlow/IPFIX → Akvorado` correlates flow throughput with pfSense
memory headroom and pipeline errors.

After deployment, validate:

```promql
up{job="akvorado_inlet"}
up{job="akvorado_outlet"}
akvorado_inlet_flow_input_udp_packets_total{exporter="172.17.0.1"}
nabla:network_flow:pfsense_packets_per_second
nabla:network_flow:clickhouse_batches_per_second
```

A successful HTTP scrape proves telemetry availability. It does not by itself
prove that flows are moving end-to-end; require the exporter packet counter and
ClickHouse batch counter to advance.

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


## Related pfSense hardening

The validated dual-export architecture, Cloudflare Network Flow dashboard,
pfBlockerNG feed changes, PHP memory limit, Snort HTTP Inspect memcap and
Netgate 1100 OOM incident are documented in
[`docs/pfsense-flow-observability-memory.md`](../../docs/pfsense-flow-observability-memory.md).
