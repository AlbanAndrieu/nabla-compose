# OpenRAG on TrueNAS

This application intentionally contains only the OpenRAG backend and frontend.
It does **not** deploy a private `openrag-langflow` service. OpenRAG consumes
the single global repository-managed Langflow service named `langflow`, plus
the shared OpenSearch service, through the external `intranet` Docker network.

The global service still uses the upstream OpenRAG-compatible Langflow image
`langflowai/openrag-langflow:0.7.1`. That image name is an implementation
detail: the runtime service/container and Docker DNS identity are both
`langflow`.

## Migration canonique du secret — PR #280 (25 octobre 2026)

La définition Compose de la PR référence désormais
`/mnt/cpool/secrets/runtime/openrag/.env.secrets`. Le validateur
Backstage exige ce chemin. Avant de réconcilier l'App TrueNAS,
vérifier que le fichier canonique existe, appartient à root,
a un mode privé et conserve le **même** `OPENSEARCH_PASSWORD`.

Sur TrueNAS, exécuter séparément :

```bash
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check openrag
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
```

La PR ajoute `diagnose-ai-secret-recovery.py --scope openrag` afin
d'exclure les échecs des services Scrutiny et LiteLLM de cette gate.
Le contrôle ne charge ni n'affiche les valeurs des clés.
**Aucun changement de Compose Git n'actualise automatiquement une
Custom App TrueNAS.** Après vérification du Compose stocké, demander une
réconciliation OpenRAG *unique* et son smoke backend/frontend.
Ne pas exécuter l'ancien `reconcile-openrag-opensearch-secret.sh --apply` ;
il est volontairement interdit.

Voir la [reprise ciblée](../../docs/runbooks/2026-10-25-critical-acceptance-followup.md).

## Reprise prioritaire OpenRAG (24 octobre 2026)

**Dernière preuve réelle TrueNAS :** `openrag=STOPPED`, les conteneurs
`openrag-backend` et `openrag-frontend` sont absents. Les conteneurs
partagés `langflow` et `opensearch` sont `running+healthy`. Docling est
absent. Le diagnostic `diagnose-stuck-apps` a signalé une App
`intentional-stopped` différée, **sans établir à lui seul que cette App
est OpenRAG**. Un arrêt `STOPPED` n'est pas un état `DEPLOYING`.

Avant toute approbation d'un démarrage, exécuter les préflights en lecture
seule **depuis un worktree revu** contenant la PR #274 :

```bash
sudo bash scripts/truenas/diagnose-openrag-startup.sh --check
sudo bash scripts/truenas/diagnose-openrag-dependencies.sh --check
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
```

**Hôte d'exécution :** ces scripts interrogent le middleware local
`midclt`. Les exécuter dans le shell de **TrueNAS** et non dans le
terminal Linux de la workstation. Le résultat
`host_context=NOT_TRUENAS_OR_MIDCLT_NOT_IN_PATH` signifie
`NOT_RUN`, et non une panne OpenRAG. Ne pas essayer d'installer `midclt`
sur la workstation.

Le nouveau préflight `diagnose-openrag-startup.sh` vérifie uniquement :

- l'état du cycle de vie TrueNAS (`STOPPED` exige une décision explicite) ;
- lorsque l'App est `RUNNING`, l'état Docker `running+healthy` des deux
  composants `openrag-backend` et `openrag-frontend` (métadonnées uniquement ;
  aucun log ni secret ; `starting`/`unhealthy`/absent bloque l'acceptation) ;
- les clés `OPENSEARCH_PASSWORD`, `LANGFLOW_KEY`,
  `LITELLM_IDE_API_KEY` et `OPENRAG_ENCRYPTION_KEY` dans le fichier
  privé `/mnt/cpool/openrag/.env.secrets` (présence, sans valeurs) ;
- le mode du fichier de secret (0600/0400) et son propriétaire root ;
- le mountpoint et l'état ZFS `cpool/bababou`, sans parcourir les données ;
- la readiness du Langflow partagé ;
- la connectivité HTTP LiteLLM de la workstation **sans clé**
  (HTTP 401/403 valide seulement le transport, pas l'authentification) ;
- la readiness Docling **séparément**, nécessaire à l'ingestion mais non
  au simple démarrage du backend/frontend.

Le comparateur OpenSearch ci-dessus établit séparément la concordance
de mot de passe sans le divulguer. Le script `--check` ne lance ni
`app.start`, ni `app.update`, ni `app.redeploy` ; il n'initialise pas
d'index, ne régénère pas de clé et ne change aucune permission.

Un résultat `READY_FOR_OPERATOR_REVIEW` ne constitue **pas** une
autorisation implicite de démarrage ni une preuve de fonctionnement
OpenRAG : vérifier ensuite les jobs TrueNAS, la définition Compose
stockée et obtenir l'accord opérateur avant la moindre mutation.
L'ingestion privée doit rester désactivée jusqu'à validation Docling,
embeddings LiteLLM et index isolé sur un document **synthétique**.

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

## Shared OpenSearch credential preflight

The OpenRAG 0.7.1 backend requires `OPENSEARCH_PASSWORD` in addition to the
host, port and username. Before restarting a backend stuck on
`No connections were configured`, compare its secret with the active
OpenSearch authority without printing either value:

```bash
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
```

The comparator now checks the canonical materializations
`/mnt/cpool/secrets/runtime/opensearch/.env` and
`/mnt/cpool/secrets/runtime/opensearch/.env.secrets`, alongside the
legacy `apps/opensearch/.env` if it still exists. It reports only the
number of candidate files, whether the keys match, and whether it could
verify the authority. It does **not** attest that a running container uses
one of these candidates.

If no trusted source exists, or the values differ, stop. Inspect the
Vaultwarden `nabla/prod/opensearch` item and the saved TrueNAS Custom App
configuration privately. The old `--apply` operation is **disabled**:
never rewrite `OPENSEARCH_PASSWORD` or restart OpenSearch as a side
effect of a diagnostic. Stage and review the canonical materialization
under the migration workflow; keep the current working service unchanged
until the owner approves a cutover and a rollback.

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


## Shared embedding contract with OpenClaw (planned; not deployed)

OpenRAG **already** uses `OPENRAG_LITELLM_EMBEDDING_MODEL=embedding` through the
OpenAI-wire-compatible `openai` provider. This is the same **model alias** being
prepared for OpenClaw `main` and `cron`. Do not create a second independent
OpenRAG embedding model or a second Langflow stack.

### Routing and identity

```text
OpenClaw main + cron -- per-application embeddings virtual key --┐
                                                                 ├--> LiteLLM stable alias "embedding"
OpenRAG + shared Langflow -- OpenRAG-scoped virtual key ----------┘          |
                                                    primary: workstation LiteLLM
                                                    standby: TrueNAS LiteLLM/Ollama
```

The **fallback policy** is shared, **credentials are not**. Use scoped LiteLLM
virtual keys for OpenClaw and OpenRAG respectively, with model allowlist
`embedding`, per-consumer budget and rate limits; never copy the OpenClaw
private key from the workstation into TrueNAS or give either service the
LiteLLM master key. The existing `LITELLM_IDE_API_KEY` is used by OpenRAG
for *both chat and embeddings* in release 0.7.1; **do not replace it with an
embedding-only key** until the provider configuration supports independent
chat/embedding credentials, or a dedicated least-privilege routing proxy is
validated. The current runtime configuration is not yet isolated by purpose.

### Fallback, availability, consistency (fail closed)

1. Keep the existing `embedding` alias stable at each application's
   configured LiteLLM endpoint. Primary: workstation `172.17.0.57:4000/v1`.
   A TrueNAS endpoint is a candidate only after it is reachable from the
   OpenRAG backend and shared Langflow and presents the expected alias.
2. Validate both endpoints separately with real embedding requests. Record
   actual upstream deployment/model identifier, model revision/digest,
   normalization and preprocessing parameters, output dimension and, when
   supported, a deterministic sentinel-vector comparison. Dimensions alone
   (including 768) **do not** prove vector-space equivalence.
3. Permit automatic upstream failover only between proven equivalent instances
   of the **same embedding model/version/configuration** and while identical
   query and document embedding semantics are retained. Test with indexed
   retrieval before enablement. Retry/timeouts must be bounded and must not
   introduce a cloud-model provider silently.
4. If fallback points to a **different** model (for example TrueNAS
   `nomic-embed-text` versus a non-identical workstation model), fail closed:
   do not query or append to the original OpenSearch vector index. Either
   restore primary or deliberately re-embed into an isolated/versioned index
   and switch collection/query routing as one reviewed operation.
5. Chat-model fallbacks are separately controlled; they must never change
   the embedding alias or vector space. On backend failure, report embedding
   retrieval/indexing **degraded/unavailable**, not a healthy silent fallback.
6. Trace model alias, effective upstream (with no credential), failover reason,
   latency and errors through LiteLLM/Langfuse/Prometheus where available.
   Remove or redact document bodies, query PII and auth tokens from telemetry.

### Acceptance before activation

- [ ] Verify workstation `embedding` upstream and TrueNAS standby model
      identity, dimensionality, vector equivalence and deterministic test
      fixtures with no user documents or personal data.
- [ ] Validate failover with forced primary unavailability and recovery,
      bounded retry, no unapproved SaaS egress, no mixed-space OpenSearch index.
- [ ] Validate an indexed OpenRAG test document and query return expected
      retrieval results before/after failover, plus a separate OpenClaw
      `main`/`cron` smoke using the same embedding-space identity.
- [ ] Introduce an OpenRAG-scoped key when release compatibility allows;
      enforce model allowlists and budgets without breaking chat `qwen`.
- [ ] Confirm OpenRAG, Langflow and OpenClaw exhibit the same explicit
      unavailable/degraded semantics when no compatible embedding backend
      remains. Keep a tested rollback and no automatic reindex.
- [ ] Ensure no actual consumer configuration or index is changed until
      runtime endpoint reachability and isolation are verified.

See `docs/runbooks/openclaw-embedding-secret-remediation.md` for the
OpenClaw SecretRef work. This section describes a **target design**; it
does not claim the shared fallback is currently enabled.
