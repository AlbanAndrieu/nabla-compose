# OpenClaw workstation backup

The approved destination is `/media/backup/lab/infra/openclaw`. The NFSv4.2 mountpoint is `/media/backup/lab`, sourced from `nabla:/mnt/cpool/backup/lab`.

Layout: `archives/`, `sqlite/main/`, `sqlite/cron/`, `sqlite/global/`, `sqlite/workboard/`, `recovery/`, `manifests/`.

Use `python3 scripts/workstation/backup-openclaw-nfs.py --dry-run` to check NFS and `python3 scripts/workstation/backup-openclaw-nfs.py` to create native OpenClaw archive and agent/global snapshots plus Workboard online SQLite copy. This requires verifying encryption and access controls before routine use.

The script verifies SHA-256 and creates an exclusive JSON manifest. This is not WORM: actual immutable retention needs enforcement on TrueNAS/ZFS or compatible object storage under separate credentials. OpenClaw native tar.gz is not encrypted and NFS sec=sys does not encrypt traffic. Verify restores to a separate recovery directory. Do not delete original local backups until transferred and verified.

The heartbeat scratch is separate from `workspace/HEARTBEAT.md`. Keep the original scratch only in protected backups; only the reviewed sanitized template belongs to this Git repository.

Deferred security debt: NFS encryption at rest and immutable retention / ZFS snapshots.

## Embedding policy

The 2026-10 embedding migration moved OpenClaw memory search behind the workstation LiteLLM proxy with a dedicated, budgeted `openclaw-embeddings` virtual key stored in a 0600 file and referenced through a SecretRef. The rules it established still apply:

- All embedding requests traverse LiteLLM with scoped keys, per-model budgets, rate limits and cost visibility. Never use `LITELLM_MASTER_KEY` as an OpenClaw runtime key, and never put a key literal in tracked config or a CLI argument.
- Preference order: `text-embedding-3-large`, `text-embedding-ada-002`, Ollama `nomic-embed-text` (local target), and the personal OpenAI API `text-embedding-3-small` strictly last and disabled by default. Do not confuse a ChatGPT subscription with OpenAI API billing.
- **Never configure these as an automatic fallback for one vector index.** Their default dimensions are 3072, 1536 and 768; mixing providers in one index gives invalid similarity results. Each model needs its own index, and switching model means selecting the matching index and query model together, or a reviewed fresh reindex.
- Before any reindex: back up both agents' databases, review cost, and keep a rollback to the original databases. Do not run `memory index --force`, `memory reset` or `--fix` as a diagnostic.

Check alias visibility with the redacted diagnostic (it does not test provider credentials):

```bash
python3 scripts/workstation/audit-openclaw-litellm-models.py --auth master
# Least privilege catalog check (will only show aliases allowed to that key):
python3 scripts/workstation/audit-openclaw-litellm-models.py --auth local
```

The redacted `openclaw-ops.sh --memory-audit` wrapper was retired with the Workstation Gateway (2026-11-11). `openclaw memory status --deep` probes the provider and may print a partially masked credential; never paste its raw output.
