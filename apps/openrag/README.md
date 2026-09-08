# OpenRAG on TrueNAS

This application intentionally contains only the OpenRAG backend and frontend.
Langflow and OpenSearch are separate repository-managed TrueNAS applications
joined through the external `intranet` Docker network.

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

OpenRAG backend/frontend are pinned to `0.7.1`.

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

## Reconcile the TrueNAS Custom App

If the repository has been updated but the running container still lacks
`LANGFLOW_HOST=langflow`, the TrueNAS app is using a stale stored Compose
snapshot. Restore the repository-backed include:

```bash
cd /mnt/cpool/compose/nabla-compose

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

Then rerun:

```bash
docker inspect openrag-frontend \
  --format '{{range .Config.Env}}{{println .}}{{end}}' |
grep -E '^(LANGFLOW_HOST|LANGFLOW_PORT|LANGFLOW_HEALTH_PATH)='

bash scripts/truenas/audit-app-lifecycle.sh
```

Do not loop `app.redeploy` while TrueNAS is under sustained I/O pressure.
Diagnose the failing dependency first.
