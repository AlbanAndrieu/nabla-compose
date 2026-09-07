# Shared Kafka on TrueNAS

`apps/kafka/compose.yml` is the canonical TrueNAS Custom App definition for
the homelab Kafka broker.

It is intentionally **not** owned by Sentry. Sentry is one consumer among
potential future services.

## Runtime

- image: `confluentinc/cp-kafka:7.6.6`
- mode: single-node KRaft broker/controller
- internal endpoint: `kafka:9092`
- network: external Docker network `intranet`
- data: `/mnt/cpool/kafka`
- no LAN/WAN port is published by default

The broker is configured for Sentry's 50 MB message requirement, but it does
not inherit Sentry's 3-hour broker-wide retention. Shared infrastructure must
not impose one consumer's retention policy on every topic. Topic-specific
retention can be applied later where required.

## Storage permissions

The Confluent image runs as UID/GID 1000. Prepare the dataset before first
start:

```bash
sudo install -d -m 750 -o 1000 -g 1000 /mnt/cpool/kafka
```

Do not reuse the former Sentry path `/mnt/cpool/sentry/kafka`.

## TrueNAS Custom App

Persist only the absolute include wrapper:

```yaml
include:
  - /mnt/cpool/compose/nabla-compose/apps/kafka/compose.yml
```

For PR/runtime validation, the include may temporarily point to a dedicated
worktree.

## Validation

```bash
docker compose -f apps/kafka/compose.yml config --quiet
```

After TrueNAS starts the app:

```bash
sudo docker ps -a \
  --filter 'label=com.docker.compose.project=ix-kafka' \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

sudo docker exec ix-kafka-kafka-1 \
  kafka-topics \
  --bootstrap-server kafka:9092 \
  --list
```

Consumers on `intranet` should use `kafka:9092`.

## Security roadmap

The initial broker is restricted to the trusted Docker `intranet` network
and uses PLAINTEXT transport. Before exposing Kafka outside that network or
using it across trust boundaries, add SASL/TLS and service-specific
credentials/ACLs.

A future multi-node broker should be deployed as a separate HA migration;
do not mutate the KRaft cluster ID or storage metadata in place.
