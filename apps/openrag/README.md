# OpenRAG on TrueNAS

This application intentionally contains only the OpenRAG backend and frontend.
It does **not** deploy a private `openrag-langflow` service. OpenRAG consumes
the single global repository-managed Langflow service named `langflow`, plus
the shared OpenSearch service, through the external `intranet` Docker network.

The global service still uses the upstream OpenRAG-compatible Langflow image
`langflowai/openrag-langflow:0.7.1`. That image name is an implementation
detail: the runtime service/container and Docker DNS identity are both
`langflow`.

## Runtime topology

```text
172.17.0.24:31060
        |
        v
openrag-frontend:3000
        |
        +--> openrag-backend:8000
                 |
                 +--> langflow:7860
                 |
                 +--> opensearch:9200
                 |
                 +--> Docling through DOCLING_SERVE_URL
```

OpenRAG backend/frontend and the global OpenRAG-compatible Langflow image are
all pinned to `0.7.1`.

The Langflow and backend images already contain the matching built-in OpenRAG
flow definitions. Do not bind an empty, unversioned directory over
`/app/flows`: doing so hides the image-bundled flows. The repository therefore
keeps only the mutable backend `/app/flows/backup` bind mount.

## Why the UI can stay "starting"

OpenRAG 0.7.1's frontend endpoint
`/health/collective_health` defaults to the upstream Compose Langflow service
name `openrag-langflow` and health path `/health`.

This homelab runs Langflow separately as:

```text
langflow:7860/health_check
```

The repository therefore explicitly sets:

```text
LANGFLOW_HOST=langflow
LANGFLOW_PORT=7860
LANGFLOW_HEALTH_PATH=/health_check
```

Without those values the frontend can be reachable on TCP/31060 while its own
collective health remains degraded.

## Read-only diagnostic

Run from TrueNAS:

```bash
cd /mnt/cpool/compose/nabla-compose

midclt call app.query \
  '[["id","=","openrag"]]' \
  '{"extra":{"retrieve_config":true}}' |
jq '.[0] | {id,state,active_workloads}'

docker ps -a --filter 'name=openrag' \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

docker inspect openrag-backend openrag-frontend |
jq '.[] | {
  name: .Name,
  status: .State.Status,
  health: (.State.Health.Status // "none"),
  failing_streak: (.State.Health.FailingStreak // 0)
}'

docker exec openrag-backend \
  curl -fsS http://127.0.0.1:8000/health

docker exec openrag-backend \
  curl -fsS http://127.0.0.1:8000/search/health

curl -fsS http://172.17.0.24:31060/health/collective_health |
jq .

docker exec openrag-backend getent hosts langflow
docker exec openrag-backend getent hosts opensearch

docker logs --since 15m openrag-backend 2>&1 |
tail -200

docker logs --since 15m openrag-frontend 2>&1 |
tail -200

cat /proc/pressure/io
```

Expected collective health:

```json
{
  "status": "ok",
  "pods": {
    "backend": {"alive": true},
    "langflow": {"alive": true}
  }
}
```

The backend `/search/health` must also return HTTP 200 to prove OpenSearch
readiness.

## Docling / ingestion

OpenRAG document ingestion requires Docling. No repository-managed Docling
service currently exists in `nabla-compose`.

OpenRAG 0.7.1 defaults to:

```text
DOCLING_SERVE_URL=http://host.docker.internal:5001
```

The Compose file maps `host.docker.internal` to the Docker host gateway on
Linux, matching upstream behavior. This only provides routing; a Docling
service still has to listen on the configured endpoint.

Check it without printing secrets:

```bash
docker exec openrag-backend sh -lc '
  url="${DOCLING_SERVE_URL:-http://host.docker.internal:5001}"
  printf "Docling target: %s\n" "$url"
  curl -fsS --max-time 8 "${url%/}/health"
'
```

Until this succeeds, treat OpenRAG as usable only for the capabilities that do
not require document ingestion. Do not delete OpenSearch indices as a first
recovery step.

## Reconcile the global Langflow and OpenRAG TrueNAS Custom Apps

If runtime still reports any of these images, it is executing a stale stored
Compose snapshot:

```text
langflowai/openrag-langflow:latest
langflowai/openrag-backend:latest
langflowai/openrag-frontend:latest
```

Reconcile the **global Langflow first**, prove it healthy, and only then
redeploy OpenRAG:

```bash
cd /mnt/cpool/compose/nabla-compose

sudo midclt call -j app.update langflow \
'{
  "custom_compose_config": {
    "include": [
      "/mnt/cpool/compose/nabla-compose/apps/langflow/compose.yml"
    ]
  }
}'

sudo midclt call -j app.redeploy langflow

curl -fsS --retry 15 --retry-delay 2 --retry-connrefused \
  http://172.17.0.24:7860/health_check

sudo midclt call -j app.update openrag \
'{
  "custom_compose_config": {
    "include": [
      "/mnt/cpool/compose/nabla-compose/apps/openrag/compose.yml"
    ]
  }
}'

sudo midclt call -j app.redeploy openrag
```

Do not start another Langflow container inside the OpenRAG application.

Then rerun:

```bash
docker inspect langflow openrag-backend openrag-frontend |
jq '.[] | {
  name: .Name,
  image: .Config.Image,
  health: (.State.Health.Status // "none"),
  flow_mounts: [.Mounts[]? | select(.Destination == "/app/flows")]
}'

docker inspect openrag-backend \
  --format '{{range .Config.Env}}{{println .}}{{end}}' |
grep -E '^(LANGFLOW_URL|OPENSEARCH_NODE_COUNT_CHECK_ENABLED)='

docker inspect openrag-frontend \
  --format '{{range .Config.Env}}{{println .}}{{end}}' |
grep -E '^(LANGFLOW_HOST|LANGFLOW_PORT|LANGFLOW_HEALTH_PATH)='

docker exec openrag-backend getent hosts langflow
docker exec openrag-backend curl -fsS http://langflow:7860/health_check

bash scripts/truenas/audit-app-lifecycle.sh
```

Do not loop `app.redeploy` while TrueNAS is under sustained I/O pressure.
Diagnose the failing dependency first.
