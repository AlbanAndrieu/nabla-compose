# OpenHands on TrueNAS

OpenHands uses the upstream `docker.all-hands.dev` registry for both the
application image and the sandbox runtime. The TrueNAS deployment must not
depend on a shell `HOME`: all host paths are explicit datasets under
`/mnt/cpool/openhands`.

## Prepare persistent paths

```bash
sudo install -d -m 750 \
  /mnt/cpool/openhands \
  /mnt/cpool/openhands/workspace \
  /mnt/cpool/openhands/state
```

The Compose workload mounts:

```text
/mnt/cpool/openhands/workspace -> /opt/workspace_base
/mnt/cpool/openhands/state     -> /.openhands-state
```

## Registry preflight

A TrueNAS error such as:

```text
Get "https://docker.all-hands.dev/v2/": context deadline exceeded
```

is a registry/network reachability failure, not a Compose validation failure.
Check DNS, HTTPS and the Docker daemon path separately:

```bash
getent ahostsv4 docker.all-hands.dev

curl -sS -o /dev/null \
  --connect-timeout 5 \
  --max-time 15 \
  -w 'registry_http=%{http_code}\n' \
  https://docker.all-hands.dev/v2/

docker pull docker.all-hands.dev/all-hands-ai/openhands:0.23
docker pull docker.all-hands.dev/all-hands-ai/runtime:0.24-nikolaik
```

HTTP `200` or an authentication response from `/v2/` proves that the host can
reach the registry. If curl works but Docker still times out, inspect Docker
daemon DNS/proxy configuration. If both time out, investigate the TrueNAS
network path, pfSense/Unbound and upstream connectivity before retrying the app.

The Compose file uses `pull_policy: missing` so a successfully cached image can
survive registry outages during later restarts.

## Validation

```bash
docker compose -f apps/openhands/compose.yml \
  config --quiet --no-interpolate --no-env-resolution

docker inspect openhands-app \
  --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```
