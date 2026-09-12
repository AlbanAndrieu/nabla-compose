# Docling Serve on TrueNAS

This directory owns the repository-managed Docling Serve instance used by OpenRAG document ingestion.

## Runtime contract

- image: `quay.io/docling-project/docling-serve-cpu:v1.32.0` by default;
- TrueNAS host/API port: `172.17.0.24:5001`;
- private Traefik URL: `https://docling.int.albandrieu.com`;
- Docker DNS identity on `intranet`: `docling:5001`;
- readiness: `GET /ready`;
- version: `GET /version`;
- metrics: `GET /metrics`;
- stable conversion API: `/v1/convert/...`.

The service is deliberately private. Do not add Cloudflare public exposure for the `*.int.albandrieu.com` hostname.

## Deploy on TrueNAS

```bash
cd /mnt/cpool/compose/nabla-compose

sudo midclt call -j app.update docling \
  "$(jq -cn --arg include '/mnt/cpool/compose/nabla-compose/apps/docling/compose.yml' \
    '{custom_compose_config:{include:[$include]}}')"

sudo midclt call -j app.redeploy docling
```

The first start can be long because the CPU image and model artifacts are large. Diagnose readiness instead of repeatedly redeploying.

```bash
sudo midclt call app.query '[["id","=","docling"]]' \
  '{"extra":{"retrieve_config":true}}' |
jq '.[0] | {id,state,active_workloads}'

docker ps -a --filter 'name=docling' \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

docker logs --since 15m docling 2>&1 | tail -200

curl -fsS http://172.17.0.24:5001/health
curl -fsS http://172.17.0.24:5001/ready
curl -fsS http://172.17.0.24:5001/version | jq .
curl -fsS http://172.17.0.24:5001/metrics | head
```

## OpenRAG acceptance

OpenRAG should resolve the repository-managed service directly through Docker DNS:

```text
openrag-backend -> http://docling:5001 -> Docling Serve
```

After the OpenRAG Compose definition is reconciled, verify the effective target:

```bash
docker exec openrag-backend sh -lc 'printf "%s\n" "$DOCLING_SERVE_URL"'
docker exec openrag-backend getent hosts docling
docker exec openrag-backend curl -fsS http://docling:5001/ready
```

Then perform one bounded direct conversion before testing OpenRAG ingestion. For example, use a small reviewed HTTP source and the stable v1 API:

```bash
curl -fsS -X POST http://172.17.0.24:5001/v1/convert/source \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{"sources":[{"kind":"http","url":"https://example.com/"}]}' |
jq .
```

Acceptance is not complete until one small document is ingested through OpenRAG, indexed in OpenSearch and retrieved successfully. Only then activate or revalidate the workstation LiteLLM GPU chat/embedding path.

## Rollback

The previous OpenRAG compatibility path used `http://host.docker.internal:5001`. Keep that only as an explicit `DOCLING_SERVE_URL` override if a known-good host-published Docling endpoint is restored. The canonical repository path is `http://docling:5001`.
