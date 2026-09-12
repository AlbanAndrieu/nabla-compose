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

Langflow exposes two materially different health endpoints:

- `/health` is process liveness and can succeed before Langflow is usable;
- `/health_check` is readiness and verifies both the database and chat/cache
  service. OpenRAG deliberately uses this stronger endpoint.

The Docker healthcheck probes readiness every 10 seconds, allows a 180-second
first-start grace window for SQLite/schema initialization, and still fails
closed if readiness never succeeds.

While TrueNAS reports `DEPLOYING`, distinguish the two states directly:

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  http://172.17.0.24:7860/health

curl -sS -w '\nHTTP %{http_code}\n' \
  http://172.17.0.24:7860/health_check |
jq . 2>/dev/null || true

docker inspect langflow |
jq '.[0].State.Health | {
  Status,
  FailingStreak,
  Log: (.Log[-5:] // [])
}'

docker logs --since 10m langflow 2>&1 |
tail -200
```

A readiness failure should be diagnosed as `db` versus `chat` before
restarting repeatedly.

Without those values the frontend can be reachable on TCP/31060 while its own
collective health remains degraded.

### Authentication to the global Langflow API

The global Langflow runtime has interactive authentication enabled. OpenRAG
must use a dedicated Langflow API key rather than copy the Langflow
administrator password into the OpenRAG secret file.

Store only the API key in:

```text
/mnt/cpool/openrag/.env.secrets
```

as:

```dotenv
LANGFLOW_KEY=<dedicated OpenRAG Langflow API key>
```

Use the repository bootstrap after global Langflow readiness is green:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-openrag-langflow-key.sh
```

The helper is idempotent: an existing valid key is retained. It authenticates
to the local global Langflow instance, creates and validates a dedicated
`openrag-global` API key only when needed, and writes the resulting
`LANGFLOW_KEY` to the root-owned mode-`0600` OpenRAG secret file without
printing it. Use `--rotate` only when an existing key is known to be invalid:

```bash
sudo bash scripts/truenas/bootstrap-openrag-langflow-key.sh --rotate
```

Check presence without printing the key:

```bash
sudo grep -q '^LANGFLOW_KEY=.' /mnt/cpool/openrag/.env.secrets &&
  echo 'LANGFLOW_KEY configured' ||
  echo 'LANGFLOW_KEY missing'
```

After redeploy, validate the key from inside the backend without exposing it:

```bash
docker exec openrag-backend sh -lc '
  test -n "${LANGFLOW_KEY:-}" &&
    curl -fsS --max-time 8 \
      -H "x-api-key: ${LANGFLOW_KEY}" \
      http://langflow:7860/api/v1/users/whoami >/dev/null
'
```

Do not duplicate `LANGFLOW_SUPERUSER_PASSWORD` into the OpenRAG secrets.

## Workstation LiteLLM GPU provider

OpenRAG currently uses the more capable LiteLLM proxy on the workstation
directly, without adding the TrueNAS LiteLLM proxy as an extra hop:

```text
OpenRAG 0.7.1 backend / shared Langflow
  -> provider = openai (OpenAI wire protocol only)
  -> OPENAI_BASE_URL=http://172.17.0.57:4000/v1
       -> workstation LiteLLM
            -> GPU-backed qwen / embedding aliases
```

OpenRAG 0.7.1 predates the generic `openai_like` provider. Its bundled
Langflow 1.11.2 already supports `OPENAI_BASE_URL`, so the compatible path is
to use the built-in `openai` provider as an OpenAI-protocol adapter and point
that adapter at LiteLLM. No OpenAI SaaS request is intended by this setup.

The repository defaults are:

```text
chat model alias:      qwen
embedding model alias: embedding
API base:              http://172.17.0.57:4000/v1
provider:              openai
```

`apps/openrag/compose.yml` and the shared
`apps/langflow/compose.yml` both set the same `OPENAI_BASE_URL`. The
workstation API key is not interpolated by Compose.

Reuse the existing `LITELLM_IDE_API_KEY`. Store it only in the OpenRAG
runtime secret file together with the existing stable OpenRAG encryption key:

```dotenv
LITELLM_IDE_API_KEY=<existing key>
OPENRAG_ENCRYPTION_KEY=<existing stable OpenRAG encryption key>
```

Both belong in `/mnt/cpool/openrag/.env.secrets`, mode `0600`. Check
presence without printing either secret:

```bash
sudo grep -q '^LITELLM_IDE_API_KEY=.' /mnt/cpool/openrag/.env.secrets &&
  echo 'LITELLM_IDE_API_KEY configured'

sudo grep -q '^OPENRAG_ENCRYPTION_KEY=.' /mnt/cpool/openrag/.env.secrets &&
  echo 'OPENRAG_ENCRYPTION_KEY configured'
```

Override the non-secret endpoint/model aliases only when the workstation
publishes different names:

```dotenv
OPENRAG_LITELLM_API_BASE=http://172.17.0.57:4000/v1
OPENRAG_LITELLM_CHAT_MODEL=qwen
OPENRAG_LITELLM_EMBEDDING_MODEL=embedding
```

After redeploying the shared Langflow and OpenRAG Compose definitions, run the
read-only preflight first:

```bash
docker exec openrag-backend \
  python /app/config/bootstrap_litellm.py
```

The preflight fails closed unless the workstation:

- accepts `LITELLM_IDE_API_KEY`;
- publishes both requested aliases through `/v1/models`;
- returns a real vector through `/v1/embeddings`;
- accepts a chat request carrying an OpenAI tool definition.

It does not change OpenRAG configuration.

Only after that succeeds, activate the workstation path:

```bash
docker exec openrag-backend \
  python /app/config/bootstrap_litellm.py --apply
```

`--apply` refuses to run without `OPENRAG_ENCRYPTION_KEY`. It stores the
reused LiteLLM key through OpenRAG's encrypted provider configuration, selects
`provider=openai`, `qwen` and `embedding`, then reapplies those settings
and the `OPENAI_API_KEY` global variable to the shared Langflow runtime.

### OpenRAG 0.7.1 compatibility caveat

OpenRAG 0.7.1 still hard-codes `https://api.openai.com/v1` in parts of its
provider validation/model-discovery code. Therefore those specific discovery
checks can report an OpenAI-provider failure even while the actual
OpenAI-compatible runtime path is correctly using the workstation LiteLLM.

For this pinned release, treat the repository preflight plus a real OpenRAG
chat/embedding smoke as the authority for this route. A later synchronized
OpenRAG backend/frontend/Langflow upgrade should move this configuration to the
native generic `openai_like` provider once that support is available in a
stable release.

### Optional TrueNAS LiteLLM second hop

The TrueNAS LiteLLM instance is also prepared as an optional proxy for other
consumers:

```text
consumer
  -> TrueNAS LiteLLM :4000
       -> model "embedding"
            -> workstation LiteLLM :4000/v1 / model "embedding"

future chat proxy
  -> TrueNAS LiteLLM :4000
       -> model "workstation-qwen"
            -> workstation LiteLLM :4000/v1 / model "qwen"

rollback
  -> TrueNAS LiteLLM :4000
       -> model "embedding-local"
            -> TrueNAS Ollama / nomic-embed-text
```

Its `.env` must expose the same `LITELLM_IDE_API_KEY`; the non-secret
`LITELLM_WORKSTATION_API_BASE` defaults to
`http://172.17.0.57:4000/v1`. Keeping `embedding-local` as a separate alias
prevents accidental load balancing between workstation GPU inference and the
TrueNAS-local rollback path.

Validate the TrueNAS proxy after its redeploy:

```bash
curl -fsS http://172.17.0.24:4000/v1/embeddings \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"embedding","input":"truenas proxy probe"}' |
jq '.data[0].embedding | length'
```

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

OpenRAG document ingestion requires Docling. The repository-managed Docling service now lives in `apps/docling/compose.yml`.

OpenRAG 0.7.1 defaults to:

```text
DOCLING_SERVE_URL=http://docling:5001
```

The Compose file maps `host.docker.internal` to the Docker host gateway on
Linux, matching upstream behavior. This only provides routing; a Docling
service still has to listen on the configured endpoint.

Check it without printing secrets:

```bash
docker exec openrag-backend sh -lc '
  url="${DOCLING_SERVE_URL:-http://docling:5001}"
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

sudo bash scripts/truenas/bootstrap-openrag-langflow-key.sh

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
