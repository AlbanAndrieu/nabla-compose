# OpenHands on TrueNAS

The TrueNAS deployment follows the current upstream OpenHands Docker contract
instead of the legacy `docker.all-hands.dev/all-hands-ai/*:0.x` images.

Current pinned runtime:

```text
OpenHands    docker.openhands.dev/openhands/openhands:1.8
Agent Server ghcr.io/openhands/agent-server:1.26.0-python
```

The deployment does not depend on a shell `HOME`; persistent state is mounted
from an explicit TrueNAS dataset.

## Prepare persistent state

```bash
sudo install -d -m 750 /mnt/cpool/openhands
sudo install -d -m 750 /mnt/cpool/openhands/state
```

The Compose workload mounts:

```text
/mnt/cpool/openhands/state -> /.openhands
```

Upstream OpenHands versions before 0.44 used `~/.openhands-state`. If this
homelab instance has meaningful legacy state, back up the dataset before
starting the 1.8 image and validate the migrated settings/history before
retiring the old copy.

## Registry preflight

The earlier TrueNAS error:

```text
Get "https://docker.all-hands.dev/v2/": context deadline exceeded
```

targeted the legacy registry. Validate the two current registries independently:

```bash
getent ahostsv4 docker.openhands.dev
getent ahostsv4 ghcr.io

curl -sS -o /dev/null \
  --connect-timeout 5 \
  --max-time 15 \
  -w 'openhands_registry_http=%{http_code}\n' \
  https://docker.openhands.dev/v2/

curl -sS -o /dev/null \
  --connect-timeout 5 \
  --max-time 15 \
  -w 'ghcr_registry_http=%{http_code}\n' \
  https://ghcr.io/v2/

docker pull docker.openhands.dev/openhands/openhands:1.8
docker pull ghcr.io/openhands/agent-server:1.26.0-python
```

HTTP `200` or an authentication response from a `/v2/` endpoint proves that
the host reached the registry. If curl works but Docker times out, inspect the
Docker daemon DNS/proxy path. If both fail, investigate TrueNAS networking,
pfSense/Unbound and upstream connectivity.

The Compose file uses `pull_policy: missing`: once the application image is
cached, an unrelated registry outage does not prevent a normal container
restart. OpenHands will still need the Agent Server image available locally or
reachable through GHCR to create agent sessions.

## Validation

```bash
docker compose -f apps/openhands/compose.yml \
  config --quiet --no-interpolate --no-env-resolution

docker inspect openhands-app \
  --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

Expected persistent mount:

```text
/mnt/cpool/openhands/state -> /.openhands
```
