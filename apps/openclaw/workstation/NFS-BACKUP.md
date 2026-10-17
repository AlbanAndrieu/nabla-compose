# OpenClaw workstation backup

The approved destination is `/media/backup/lab/infra/openclaw`. The NFSv4.2 mountpoint is `/media/backup/lab`, sourced from `nabla:/mnt/cpool/backup/lab`.

Layout: `archives/`, `sqlite/main/`, `sqlite/cron/`, `sqlite/global/`, `sqlite/workboard/`, `recovery/`, `manifests/`.

Use `python3 scripts/workstation/backup-openclaw-nfs.py --dry-run` to check NFS and `python3 scripts/workstation/backup-openclaw-nfs.py` to create native OpenClaw archive and agent/global snapshots plus Workboard online SQLite copy. This requires verifying encryption and access controls before routine use.

The script verifies SHA-256 and creates an exclusive JSON manifest. This is not WORM: actual immutable retention needs enforcement on TrueNAS/ZFS or compatible object storage under separate credentials. OpenClaw native tar.gz is not encrypted and NFS sec=sys does not encrypt traffic. Verify restores to a separate recovery directory. Do not delete original local backups until transferred and verified.

The heartbeat scratch is separate from `workspace/HEARTBEAT.md`. Keep the original scratch only in protected backups; only the reviewed sanitized template belongs to this Git repository.

## Memory / LiteLLM incident diagnostic (2026-10-17)

OpenClaw 2026.9.5 uses `memory.search` in its JSON schema, **not** `agents.defaults.memorySearch`. The schema describes `memory.search.provider = "openai-compatible"`, `memory.search.remote.baseUrl`, `memory.search.remote.apiKey`, `memory.search.model`, and `memory.search.fallback`. Verify effective runtime configuration before changing anything; do not paste API keys into issue reports.

Confirmed baseline: `openclaw memory status --deep` showed provider `openai`, model `text-embedding-3-small`, HTTP 401 `invalid_api_key` for both agents; `main` indexed 15/105 files (57 chunks), `cron` 0/63; both dirty with vector search paused, while FTS remains ready. `main` has 57 cached embeddings. The file totals are candidates under each workspace's `memory` source, not a list of all disk files. Dreaming corpus is present, but membership in indexed candidates was not established.

Use `bash scripts/workstation/openclaw-ops.sh --memory-audit` for a **read-only, redacted** status/schema overview, and `--memory` for the existing text status. `openclaw memory status --deep` probes the provider and may print a partially masked credential; never paste its raw output. Do not run `--index`, `--fix`, `memory reset`, or `memory index --force` as a diagnostic.

Budget evidence from the read-only LiteLLM audit: `openclaw-main` spend $10.016404 / $10 weekly (reset 2026-10-19 00:00 UTC); `openclaw` $0.25612 / $2; `openclaw-cron` hashed key ID not supplied. Propose dedicated `openclaw-embeddings` virtual key and separate limited budget, plus a verified LiteLLM embedding model alias. Check dimension compatibility with the existing 768-dimensional vectors before migrating; dimension/model changes can require a reviewed reindex. Never substitute `LITELLM_MASTER_KEY` for a virtual key or print it. Budget changes and indexing require explicit operator approval.


## Provisioning a dedicated embeddings virtual key

Run on the GPU workstation, against its loopback LiteLLM proxy. The tracked TrueNAS proxy configuration declares an `embedding` alias routed upstream and an `embedding-local` alternative; **verify the workstation LiteLLM model catalog** before selecting an alias. The provisioning script does not test embeddings or check vector dimensions.

```bash
python3 scripts/workstation/provision-openclaw-embeddings-litellm-key.py --check
# Only after confirming the alias and reviewing the policy:
python3 scripts/workstation/provision-openclaw-embeddings-litellm-key.py --apply --model embedding
```

`--apply` requires `LITELLM_MASTER_KEY` in the operator shell, sends it **only to** `http://127.0.0.1:4000/key/generate` (or equivalent loopback origin), and requests `key_alias=openclaw-embeddings`, `models=[embedding]`, `max_budget=1` USD, `budget_duration=30d`, `rpm_limit=5`, `tpm_limit=20000`. It creates a new private key file at `~/.local/share/nabla-compose/openclaw-embeddings.key` (0600), never prints the token and refuses to overwrite an existing file. The file is **not** automatically injected into OpenClaw; configure a supported SecretRef only after verifying runtime config and model/dimension compatibility. The master key must not be injected into OpenClaw. This operation is mutating and can create an orphaned virtual key if storage fails; revoke it in LiteLLM if that happens. Do not commit the generated key, run `memory index`, or change model dimensions as part of provisioning.

## Embedding migration staging (2026-10-17)

Operator confirmed workstation LiteLLM alias `embedding` routes to `ollama/nomic-embed-text` at `172.17.0.57:11434`. The dedicated key permits only `embedding`, and its local file has permissions 0600. This is **not** a runtime embedding success or vector-dimension test. Azure aliases `text-embedding-3-large` and `text-embedding-ada-002` are separate and not authorized by this virtual key.

```bash
python3 -m py_compile scripts/workstation/prepare-openclaw-embedding-migration.py
python3 scripts/workstation/prepare-openclaw-embedding-migration.py --check
# Only after reviewing discovered SQLite paths and existing NFS backup:
python3 scripts/workstation/prepare-openclaw-embedding-migration.py --apply
```

`--apply` here means **backup only**: SQLite online backups are written under `~/.local/share/nabla-compose/openclaw-memory-migration/<UTC timestamp>/` with 0700 directories and 0600 files, checked with `PRAGMA integrity_check`. It does not migrate OpenClaw, run embeddings, index, or restart services. Discoverability is deliberately limited to conventional state paths; if the tool finds no SQLite files, do not force anything. Review the OpenClaw runtime paths and extend the script before proceeding. This local backup is not a substitute for verified NFS/offsite and restore procedures. A later separately reviewed change must implement supported secret injection, model test (768 dimensions), model-specific fresh index migration and rollback. Never copy an OpenAI embedding index directly into the Ollama vector space.


## Verified local embeddings and next migration gate (2026-10-17)

Operator successfully executed `test-openclaw-litellm-embedding.py`: the dedicated virtual key authenticated to loopback LiteLLM alias `embedding` and returned **768 numeric dimensions**. This does **not** mean the old OpenAI vectors can be reused; `nomic-embed-text` requires a fresh index. The NFS backup completed successfully with ten verified artifacts and a SHA-256 manifest, including Workboard; isolated restore testing remains pending.

Next gate: inspect the **installed** OpenClaw 2026.9.5 schema and effective configuration for `memory.search.provider=openai-compatible`, `model=embedding`, `remote.baseUrl=http://127.0.0.1:4000/v1`, `remote.apiKey` SecretRef support, and explicit fallback disablement. Do not assume a file-path value is automatically dereferenced as a secret. Never place the virtual key literal in a tracked config or CLI argument. Avoid setting OpenAI fallback. After confirming secret support and an isolated restore, prepare a separately reviewed config cutover and a fresh index for **both** agents, with rollback to the saved original DBs.

Deferred security debt: NFS encryption at rest and immutable retention / ZFS snapshots; these are not blockers for the embedding repair but must remain on the roadmap.


## Temporary large-model evaluation and local independence plan

Operator selected `text-embedding-3-large` **temporarily for evaluation**, retaining `embedding` → `ollama/nomic-embed-text` as the fully local future target. No OpenClaw runtime change or index migration has been applied. The installed schema has been confirmed to expose `memory.search.provider`, `model`, `fallback`, `remote.baseUrl`, and `remote.apiKey`.

Diagnostics:

```bash
python3 scripts/workstation/openclaw-memory-audit.py
python3 scripts/workstation/test-openclaw-litellm-embedding.py --profile local
# Only after creating a separate scoped virtual key for the large model:
python3 scripts/workstation/test-openclaw-litellm-embedding.py --profile large
```

The large profile expects a private `~/.local/share/nabla-compose/openclaw-embeddings-large.key` file (0600), model alias `text-embedding-3-large`, and **3072** dimensions. It does not reuse the local-only key. Check LiteLLM routing, upstream authorization, actual price/budget, and configured output dimensions before provisioning; a deliberately shortened large-model output will fail the current diagnostic. Avoid unrestricted master credentials and unbounded indexing.

Do not index until provider configuration, SecretRef semantics, isolated restoration, expected cost, and both agents' rollback have been reviewed. A future move to nomic requires **another fresh vector index**, not a provider swap over existing vectors. NFS encryption and immutability remain deferred roadmap items.


## Multi-provider fallback policy (2026-10-17)

Requested preference order: `text-embedding-3-large` (primary), `text-embedding-ada-002` (secondary), `nomic-embed-text` (local tertiary). **Do not implement these as an automatic LiteLLM/OpenClaw embedding fallback for a single vector index.** Their default dimensions are 3072, 1536 and 768, respectively; equalizing dimensions where supported still does not equalize vector spaces. Mixing providers within one index would produce invalid or misleading similarity results.

Execution order:
1. Validate a separate scoped/budgeted `text-embedding-3-large` key, model routing and one-shot vector dimension test; no indexing yet.
2. Verify OpenClaw 2026.9.5 runtime SecretRef behavior and isolated backup restore. Disable cross-model automatic fallback for embedding requests. The `memory.search.fallback` schema field must not be assumed to encode an ordered model list.
3. Migrate both agents to a fresh large-model index only after explicit cost review and rollback plan. Preserve original databases.
4. Prepare separately versioned indexes for `ada-002` and `nomic-embed-text` if desired. Switching between them must select the matching index and query model together; never reuse the large-model index.
5. Later: benchmark relevance, prioritize fully local `nomic-embed-text`, then change primary after a controlled reindex.

Current evidence: `main` remains `text-embedding-3-small` at 15/105 files and dirty; `cron` remains `text-embedding-3-small` at 0/63 and dirty. Local alias `embedding` was tested successfully with 768 dimensions. No large-model test or runtime cutover has been confirmed.
