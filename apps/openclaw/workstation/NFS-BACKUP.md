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
