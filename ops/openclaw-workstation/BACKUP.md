# OpenClaw workstation — GitOps configuration and safe backup

## Evidence and ownership (2026-10-17)

The private repository `AlbanAndrieu/nabla` already tracks
`env/home/dotfiles/.openclaw/workspace/HEARTBEAT.md` and other OpenClaw
files (`openclaw.json`, agent/workspace material, `.env`,
`gateway.systemd.env`, `exec-approvals.json`). The operator confirms that `.env` and `gateway.systemd.env` are encrypted in `nabla`.
Keep these and all potentially personal `USER.md`, `SOUL.md`, identities and
related dotfiles in private `nabla`; **do not migrate or delete them**.
Encryption of two files has been reported, but has not been independently
verified here. Review encryption boundaries and history locally without
printing values.
An attempted remote content read of the old HEARTBEAT.md failed decoding;
therefore its byte-for-byte contents have NOT been migrated or validated.

Canonical **reviewed, non-secret** workstation heartbeat policy belongs here
under `ops/openclaw-workstation/HEARTBEAT.md`. The Compose service at
`apps/openclaw/compose.yml` may be a different runtime: **do not mount or
apply workstation heartbeat policies to TrueNAS by accident**.

The actual workstation file is `~/.openclaw/workspace/HEARTBEAT.md`.
The original operator-observed 59-line file includes a multi-service morning
briefing, calendars, inbox and WhatsApp; it is inappropriate for an unbounded
30-minute heartbeat. The cron workspace file is separately comment-only.
The 100 sampled main heartbeats all failed and `openclaw-main` exhausted
its 10 USD / 7d LiteLLM budget. A causal per-request spend breakdown remains
outstanding.

## Backup tiers

| Tier | Contents | Destination | Policy |
| --- | --- | --- | --- |
| A: reviewed Git configuration | Minimal `HEARTBEAT.md`, sanitized templates, runbooks, deterministic scripts | `nabla-compose/ops/openclaw-workstation/` | Versioned; PR reviewed; no secrets or personal content |
| B: owner-controlled private Git dotfiles | Encrypted `.env`, encrypted `gateway.systemd.env`, personal `USER.md`/`SOUL.md`, identity, agent and configuration templates | Private `AlbanAndrieu/nabla` | **Retain, do not migrate or delete**; verify protection before changing |
| D: live runtime backup | Active per-agent `openclaw-agent.sqlite`, sessions, memory database, credentials and workspace runtime | Verified encrypted OpenClaw archive/SQLite snapshot or Restic | Do not copy live SQLite/WAL raw into Git; restore drill required |
| C: baseline infrastructure | Compose service definitions and non-secret policies | `nabla-compose/apps/openclaw/` | Existing Git workflow |

Git is **not** a replacement for a restorable runtime backup. Commit history
retains removed secrets. Review already tracked `.env` and
`gateway.systemd.env` in `nabla` for exposures locally with a scanner;
if any secrets were committed, rotate them and plan history remediation.
Do not echo their values or mirror them into this repository.

## Workstation dry-run and deployment (opt-in, no gateway restart)

From the `nabla-compose` checkout:

```bash
python3 scripts/workstation/openclaw-heartbeat-gitops.py --check
python3 scripts/workstation/openclaw-heartbeat-gitops.py --backup
# Explicit, opt-in: backs up current heartbeat before replacing it.
python3 scripts/workstation/openclaw-heartbeat-gitops.py --apply
python3 scripts/workstation/openclaw-heartbeat-gitops.py --check
```

`--check` compares SHA-256 of source and destination; no content printed.
`--backup` creates a private local 0600 copy, excluding Git; `--apply`
requires a prior backup, refuses symlinks, and uses atomic replacement.
Source is an intentionally comment-only heartbeat. This is a **config
deployment**, not a snapshot of agent session state. Existing failed
jobs may persist because of memory/agent-runner problems; compare run counts
and LiteLLM spending after approval, without manual billable probes.

## Recovery

The backup script prints the backup file path (not contents). Recover a
specific saved copy using a reviewed local `install -m 600` operation; do
not automatically select the latest file if there are multiple candidates.
Record checksum and permission checks. A complete recovery additionally
requires tested encrypted runtime backup, credentials in Vaultwarden and
restoration of the gateway service.

## Roadmap acceptance

1. Preserve `nabla` as owner of private/encrypted dotfiles and personal agent instructions.
   Audit encryption and history only; rotate credentials **if exposure is confirmed**.
   Do not retire personal dotfiles or rewrite repository history by default.
2. Verify installed OpenClaw version respects comment-only heartbeat skip
   semantics (without generating paid calls); assess whether native heartbeat
   should instead be explicitly disabled and replaced with deterministic
   monitoring.
3. Run targeted hermetic tests and local-first quality gate, then operator
   approves `--apply`; do not change LiteLLM budgets.
4. Check `openclaw backup --help` and `openclaw backup sqlite --help` on installed
   OpenClaw 2026.9.5. If available, use consistent verified per-agent SQLite
   snapshots (including `cron`) and a full encrypted state/workspace archive;
   otherwise use SQLite online backup API with WAL consistency, never `cp` of
   a live database. Add scoped Restic storage, retention and scratch restore.
5. Monitor 429, request tokens/cost per virtual key, heartbeat failures
   and 401 memory embedding separately. Do not claim success based solely
   on file match.

## Current heartbeat evidence (2026-10-17)

The operator validated 8 targeted pytest tests and SHA-256 parity after `--apply`.
However latest 3 heartbeat runs still failed (`agent-runner-failure`, approximately
279–284 seconds), and application logs in the last 30 minutes report budget 429,
context pressure, timeouts and embedding 401. These diagnostics are aggregated,
not per-request cost attribution. Administrative LiteLLM audit was skipped because
its master key was absent from the script environment; do not expose that key or
bypass budgets. OpenClaw documentation distinguishes `workspace/HEARTBEAT.md`
from per-monitor cron scratch and documents a `reason=empty-heartbeat-file` skip.
Identify the *active* scratch and verify skip events before calling this fixed.
Do not perform billable manual probes.


## 2026-10-25 — Préserver l'ancienne checklist et publier un briefing isolé

L'opérateur détient encore un fichier local
`~/.openclaw/workspace/HEARTBEAT.md.before-fix` contenant l'ancien
modèle « Morning Briefing – Self-Healing Home Server » (météo, disque,
RAM, CPU, services, calendriers, Gmail, WhatsApp, alertes et tâches).
**Ne pas effacer ni écraser cette sauvegarde.**

**Décision :** ne pas réintroduire ces sondes coûteuses dans la boucle
native `main` de 30 minutes. Le fichier
`ops/openclaw-workstation/HEARTBEAT.md` reste volontairement
comment-only pour laisser OpenClaw ignorer les tours vides.
Le briefing complet et révisé est versionné séparément dans
`ops/openclaw-workstation/MORNING_BRIEFING.md` :
- tous les états dynamiques restent `Non vérifié` sans preuve ;
- seules des preuves autorisées Gatus/Prometheus/FastAPI sont utilisées ;
- les conversations exclues restent dans une configuration privée ;
- les jetons verrouillés restent verrouillés, sans reconnexion automatique ;
- le briefing peut être lancé explicitement ou par une automation
  isolée, jamais par le heartbeat non borné.

**Depuis Workstation uniquement :**

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-morning-briefing-test
just openclaw-morning-briefing-check
just openclaw-morning-briefing-apply
just openclaw-morning-briefing-check
```

`apply` conserve une sauvegarde privée de l'ancien `HEARTBEAT.md`
sous `~/.openclaw/backups/heartbeat-gitops/`, installe le nouveau
`MORNING_BRIEFING.md` dans le workspace en mode 0600 et sauvegarde
une version préexistante de ce dernier. Le script refuse les symlinks
et les changements concurrents. La sauvegarde
`HEARTBEAT.md.before-fix` reste intacte.

Ne pas créer un `cron` depuis un `tasks:` dans le fichier : les
versions récentes d'OpenClaw orientent les tâches récurrentes vers
leur scheduler natif, dont la syntaxe doit être vérifiée sur la
version installée après `openclaw update`.

### Interaction avec les embeddings

La mise à jour d'un fichier `HEARTBEAT.md` ou
`MORNING_BRIEFING.md` n'implique **pas** la reconstruction des
embeddings `main`/`cron` dans le moteur mémoire standard, qui
indexe plutôt `MEMORY.md`, `USER.md` et `memory/*.md`.
Toutefois, `openclaw update` peut introduire une migration du
moteur mémoire et reconstruire un index lors de la prochaine
recherche/synchronisation ; distinguer cette migration d'un incident
de transport LiteLLM.

Contrôles après mise à jour (Workstation) :
```bash
openclaw --version
bash scripts/workstation/openclaw-ops.sh --memory
python3 scripts/workstation/check-openclaw-litellm-memory-config.py --audit
```

Ne pas exécuter `memory index --force` ni modifier le modèle
d'embedding (dimension 768) pour résoudre le seul 429 de chat.
La preuve d'index sain datée du 23 octobre reste historique :
un `openclaw update` impose une nouvelle vérification.

Documentation :
- https://docs.openclaw.ai/heartbeat
- https://docs.openclaw.ai/cron-vs-heartbeat
- https://docs.openclaw.ai/concepts/memory-search
