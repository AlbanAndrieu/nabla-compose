# Docling / OpenRAG post-reboot deployment

This runbook covers the next OpenRAG ingestion step after the accepted TrueNAS
reboot and CSI baseline. OpenRAG backend/frontend and the shared Langflow runtime
are already restored; document ingestion remains intentionally open until a
repository-managed Docling Serve instance is deployed and validated.

## Reviewed baseline

Use a pinned CPU image on TrueNAS first:

```text
ghcr.io/docling-project/docling-serve-cpu:v1.31.0
```

The CPU image avoids coupling document ingestion to the workstation GPU. The
workstation remains the preferred high-performance inference path for
LiteLLM/chat/embeddings. Revisit a CUDA Docling deployment only after the CPU
path is functionally accepted and there is measured evidence that document
conversion is the bottleneck.

Docling Serve exposes the following acceptance endpoints on port `5001`:

- `/health` for liveness;
- `/ready` for readiness after model loading;
- `/metrics` for Prometheus metrics;
- `/version` for the effective Docling component versions;
- `/v1/...` for the stable conversion API.

The target topology is:

```text
OpenRAG backend
  -> http://docling:5001
       -> Docling Serve CPU on TrueNAS
       -> /ready
       -> /metrics <- Prometheus

OpenRAG backend / shared Langflow
  -> workstation LiteLLM http://172.17.0.57:4000/v1
       -> GPU chat + embedding aliases
```

## Repository implementation

The final repository-managed deployment must:

1. add `apps/docling/compose.yml` as the canonical TrueNAS Custom App source;
2. pin `docling-serve-cpu` rather than use `latest`;
3. expose `172.17.0.24:5001` only for LAN/operator diagnostics;
4. join the external `intranet` network so OpenRAG can use Docker DNS
   `docling:5001`;
5. declare `x-nabla` runtime, monitoring and dependency metadata;
6. use `http://172.17.0.24:5001/ready` as the direct readiness target;
7. expose `/metrics` to the existing Prometheus service;
8. add the corresponding Prometheus scrape job with a stable `service=docling`
   label;
9. change OpenRAG's default `DOCLING_SERVE_URL` from
   `http://host.docker.internal:5001` to `http://docling:5001` only once the
   repository-managed service exists;
10. add an explicit OpenRAG `dependsOn` topology relation to Docling without
    introducing cross-App Compose `depends_on` coupling;
11. regenerate `catalog/service-topology.json`, `catalog/services.json`, Homarr,
    Gatus and AutoKuma consumers before publishing;
12. run `bash scripts/agent-quality-gate.sh --fix` and then the strict check-only
    gate before pushing.

Keep the current `host.docker.internal` route as rollback compatibility until
Docling is accepted.

## TrueNAS preflight

Before creating the repository-managed Custom App, confirm port ownership and
remove ambiguity with any stopped native application:

```bash
sudo ss -lntp | grep ':5001 ' || true

sudo midclt call app.query |
jq -r '.[] | select((.id // "") | test("docling"; "i")) |
  [.id,.state,.human_version] | @tsv'

docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}' |
grep -i docling || true
```

Do not reuse an opaque native App data path as the new canonical deployment.
Docling conversion output is not the OpenRAG source of truth; OpenSearch and the
OpenRAG document/index workflow remain authoritative for accepted ingestion.

## Docling acceptance

After the repository-managed Docling service is deployed, require all of these
checks to pass before changing OpenRAG:

```bash
curl -fsS http://172.17.0.24:5001/health | jq .
curl -fsS http://172.17.0.24:5001/ready | jq .
curl -fsS http://172.17.0.24:5001/version | jq .

curl -fsS http://172.17.0.24:5001/metrics |
head -40
```

Require Prometheus to see Docling as UP:

```bash
curl -fsS http://172.17.0.24:9090/api/v1/targets |
jq -r '
  .data.activeTargets[]
  | select(.labels.job=="docling")
  | [.labels.job,.health,.scrapeUrl,.lastError]
  | @tsv
'
```

Run one bounded direct conversion before testing OpenRAG ingestion. Use a small,
non-sensitive local fixture and the stable v1 API; do not start with a large PDF
or remote URL that mixes Docling validation with Internet reachability.

## OpenRAG cutover

Only after Docling readiness and direct conversion are green:

1. set the OpenRAG backend default to `DOCLING_SERVE_URL=http://docling:5001`;
2. keep the backend and Docling on `intranet`;
3. redeploy OpenRAG once, without repeatedly cycling Langflow/OpenSearch;
4. verify the effective URL inside `openrag-backend`;
5. verify Docling `/ready` from inside the backend;
6. ingest one small controlled document;
7. prove the OpenRAG knowledge item reaches its terminal successful state;
8. prove the resulting document/chunks are queryable in OpenSearch;
9. run one RAG query whose answer cites/retrieves that document;
10. remove the test document and verify the expected OpenRAG/OpenSearch cleanup
    path rather than deleting indices manually.

Useful connectivity checks:

```bash
docker exec openrag-backend getent hosts docling

docker exec openrag-backend sh -lc '
  printf "DOCLING_SERVE_URL=%s\n" "${DOCLING_SERVE_URL:-unset}"
  curl -fsS --max-time 10 "${DOCLING_SERVE_URL%/}/ready"
'

curl -fsS http://172.17.0.24:31060/health/collective_health |
jq .

docker exec openrag-backend \
  curl -fsS http://127.0.0.1:8000/search/health
```

## LiteLLM after Docling

Do not mix Docling recovery with model-provider changes. Once one document is
successfully ingested and retrieved, continue the already prepared workstation
LiteLLM path:

```bash
docker exec openrag-backend \
  python /app/config/bootstrap_litellm.py
```

The preflight must prove the reused `LITELLM_IDE_API_KEY`, chat alias, embedding
alias, real embedding vector and tool-capable chat request. Only then apply:

```bash
docker exec openrag-backend \
  python /app/config/bootstrap_litellm.py --apply
```

The preferred path remains:

```text
OpenRAG / global Langflow
  -> OpenAI-compatible wire protocol
  -> workstation LiteLLM 172.17.0.57:4000/v1
  -> GPU-backed qwen + embedding aliases
```

## Rollback

If Docling itself is unhealthy, keep OpenRAG core running and mark ingestion as
unavailable rather than degrading the whole application.

If the OpenRAG cutover fails:

1. restore `DOCLING_SERVE_URL=http://host.docker.internal:5001` only when a
   known-good host Docling instance still exists;
2. otherwise keep Docling ingestion disabled/unavailable while preserving
   OpenRAG/OpenSearch data;
3. do not delete OpenSearch indices as a recovery shortcut;
4. do not rotate OpenRAG/Langflow/LiteLLM secrets;
5. retain Docling logs plus the failed bounded-ingestion evidence.

## Acceptance definition

Docling/OpenRAG is complete only when all of the following are true:

- Docling `/health` and `/ready` are HTTP 200;
- Prometheus reports the `docling` job UP;
- direct bounded conversion succeeds;
- OpenRAG backend reaches Docling through Docker DNS;
- one bounded document reaches successful ingestion;
- the resulting content is queryable in OpenSearch;
- one RAG query retrieves the ingested content;
- workstation LiteLLM chat and embedding preflight remains green;
- rollback does not require deleting OpenSearch data or rotating unrelated
  secrets.
