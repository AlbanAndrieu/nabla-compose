# Akvorado network-flow observability

> Runtime image note: upstream released source tag `v2026.8.1`, but the
> corresponding container manifest was not available on the configured Quay
> registry during the 2026-09-08 recovery. The deployment therefore pins the
> published GHCR image `ghcr.io/akvorado/akvorado:2026.8.0` until a newer
> container tag is verified before promotion.

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
AKVORADO_CFG_ORCHESTRATOR_CLICKHOUSEDB_PASSWORD=<dedicated-secret>
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

### TrueNAS Custom App deployment

The repository Compose file is included by the TrueNAS Custom App. The
Akvorado runtime variable is now read directly from the service-level
`/mnt/cpool/akvorado/.env.secrets`; no include-level interpolation file is
required.

The canonical Vaultwarden manifest maps the existing import name
`AKVORADO_CLICKHOUSE_PASSWORD` to the runtime name
`AKVORADO_CFG_ORCHESTRATOR_CLICKHOUSEDB_PASSWORD`. Render the file with:

```bash
python scripts/secrets/render_from_bitwarden.py \
  --app akvorado \
  --output-file /mnt/cpool/akvorado/.env.secrets
chmod 600 /mnt/cpool/akvorado/.env.secrets
```

Use this Custom App YAML:

```yaml
include:
  - /mnt/cpool/compose/nabla-compose/apps/akvorado/compose.yml
```

If the app is not registered yet (`app.redeploy akvorado` returns `ENOENT`),
create it from the canonical include wrapper:

```bash
AKVORADO_WRAPPER="$(
  cat <<'EOF'
include:
  - /mnt/cpool/compose/nabla-compose/apps/akvorado/compose.yml
EOF
)"

sudo midclt call -j app.create "$(
  jq -cn \
    --arg compose "${AKVORADO_WRAPPER}" \
    '{
      app_name: "akvorado",
      custom_app: true,
      custom_compose_config_string: $compose
    }'
)"
```

Then **Save/Deploy** the `akvorado` Custom App. Do not paste a copy of
`apps/akvorado/compose.yml` into the UI: the external include preserves the
repository-relative `./config` bind mount.

After deployment, verify the application before enabling any legacy flow
collector:

```bash
midclt call app.query | jq '.[] | select(.name == "akvorado") | {name,state,version}'
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '^akvorado-'
```

Functional checks:

```bash
curl -fsS http://172.17.0.24:31057/api/v0/healthcheck
curl -fsS http://172.17.0.24:31058/api/v0/healthcheck
curl -fsS http://172.17.0.24:31056/
```

Do not consider the deployment successful from container state alone; the
Inlet/Outlet healthchecks and the end-to-end flow counters below must advance.

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

## pfSense NetFlow v5 → Akvorado: evidence (2026-10-23, operator)

The current pfSense flow exporter is **NetFlow v5**, not the historic IPFIX v10
configuration shown above. Keep `Track by Default` **OFF** and scope sampling
exclusively with the LAN rule `Always Track Flow Data` because the Netgate 1100
has suffered OOM. Do not enable additional exporters or increase collection scope.

Evidence recorded without packet payloads:

- TrueNAS `br0`: UDP `172.17.0.1:38341 → 172.17.0.24:2055`, 504-byte datagram.
- Docker host: `docker-proxy` socket bound to `172.17.0.24:2055/udp`.
- Inlet application (not merely host socket): 139 packets, 105768 bytes for
  exporter `172.17.0.1`; zero UDP receive errors and zero receive-queue drops.
- Inlet Kafka producer: 139 sent messages; observed internal topic
  `akvorado-flows-v5` (configuration declares `akvorado-flows`). Verify the
  version suffix and Outlet subscription before changing the GitOps topic.
- Outlet consumption, ClickHouse persisted rows, and Console flow visibility
  remain **unverified**. Cumulative metrics do not prove rates or end-to-end delivery.

Read-only bounded, redacted counters (both Inlet and Outlet):

```bash
python3 scripts/truenas/diagnose-akvorado-flow.py --strict
python3 -m unittest discover -s tests -p test_akvorado_flow_diagnostic.py
```

For a final runtime acceptance, verify an increasing Outlet Kafka consumption
counter, increasing ClickHouse insertion counters, and nonzero recent rows in
`akvorado` via an authorized **read-only**, database-scoped SQL identity.
Confirm that recent records are displayed in Console. Keep raw captures,
flow addresses and SQL result samples private. Do not infer success from HTTP
200, container RUNNING, or UDP packet receipt alone.

### Outlet findings — 2026-10-23 (later operator metrics)

- Kafka Outlet `received_messages_total=164`; matching internal topic
  `akvorado-flows-v5`. The suffix does not currently indicate a mismatch.
- Decoder: 164 NetFlow **v5** packets and 2511 PDU records.
- Core: 2511 flows received and 2511 `metadata missing` errors.
- Metadata provider: 5021 errors; SNMP poller `get` failures: 81.
  These counters count different events; they must **not** be added together.
- ClickHouse batch/insert histogram counts: **zero**. Persistence and Console
  display remain unverified; do not present the app as functioning end-to-end.

Run `python3 scripts/truenas/diagnose-akvorado-flow.py --strict` to get
bounded metrics and a classified pipeline status. This is read-only, does
not print raw labels or flow details, and uses short network timeouts.
Cumulative counter values need successive measurements to establish activity.

Per upstream Akvorado troubleshooting, `metadata missing` means unavailable
exporter interface information, commonly because SNMP requests fail.
Investigate SNMP reachability and exporter metadata configuration **without**
enabling pfSense `Track by Default`, increasing capture or globally
changing `pflow`. Prefer a narrowly scoped, documented static metadata
provider if SNMP from the Outlet cannot be safely enabled. Validate interface
indexes and actual metadata before specifying a static mapping; never guess
interfaces or credentials. Even after resolving metadata, verify ClickHouse
persisted rows using a separately authorized read-only identity.

References:
- https://demo.akvorado.net/docs/troubleshooting
- https://demo.akvorado.net/docs/configuration
