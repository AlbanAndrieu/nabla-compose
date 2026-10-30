# OpenClaw : diagnostic et migration Workstation vers TrueNAS (30/10/2026)

Source de vérité : nabla-compose. État privé : ~/.openclaw. La politique
apps/openclaw/workstation/heartbeat-restoration.policy.json est un manifeste
GitOps, pas un fichier interprété directement par OpenClaw. Ne pas créer de
nouveau checkout ni de lien symbolique dans ~/.openclaw.

## 0 — Worktree isolé sur Workstation

~~~bash
set -Eeuo pipefail
cd ~/w/nabla-compose
git fetch origin master fix/openclaw-diagnostics-fail-closed-20261030
WT="$(mktemp -d /tmp/openclaw-migration.XXXXXX)"
rmdir "$WT"
git -c submodule.recurse=false worktree add --detach "$WT" origin/fix/openclaw-diagnostics-fail-closed-20261030
cd "$WT"
umask 077
~~~

## 1 — Contrats, inventaire et préflight sans mutation

~~~bash
just openclaw-migration-evidence-test
just openclaw-migration-evidence-tests
just openclaw-migration-evidence-inventory
just openclaw-migration-evidence-check
just openclaw-litellm-dual-logs-check
~~~

Les sondes continuent même en cas de statut partiel. Code de sortie 2 =
preuve absente ou diagnostic en échec, jamais conclusion globale DOWN.
Sur TrueNAS, le collecteur utilise SSH 9922 + docker logs sur le conteneur
litellm ; il n'accorde aucun droit Docker. Sans cette permission, état
docker_permission_denied, pas de statut vert inventé.

Tests réseau de processus, non facturables, Workstation :

~~~bash
curl --noproxy '*' -sS --connect-timeout 2 --max-time 6 -o /dev/null -w 'litellm_workstation=%{http_code}\n' http://127.0.0.1:4000/health/liveliness
curl --noproxy '*' -sS --connect-timeout 2 --max-time 6 -o /dev/null -w 'openclaw=%{http_code}\n' http://127.0.0.1:18789/readyz
~~~

## 2 — Vérifier TrueNAS, les modèles et les clés

Workstation, sans transmettre de master key en HTTP LAN :

~~~bash
just openclaw-truenas-model-keys-check
just openclaw-truenas-tunnel-check
# Mutation optionnelle : création d'un SSH forward privé si absent.
just openclaw-truenas-tunnel-ensure
just openclaw-truenas-tunnel-check
# Lectures GET administrateur via le tunnel ; saisie TTY masquée.
just openclaw-truenas-model-keys-tunnel-prompt
~~~

TrueNAS, depuis une console de l'appliance et un checkout synchronisé :

~~~bash
midclt call system.version
cd /mnt/cpool/compose/nabla-compose
just litellm-workstation-upstream-auth-check
just openclaw-truenas-virtual-keys-plan
just openclaw-truenas-virtual-keys-status
just openclaw-truenas-virtual-keys-quota
~~~

Ces commandes ne créent aucune clé. STOP si les modèles gpt-4.1 et
gpt-4.1-mini manquent dans le runtime (ils manquent dans la configuration
Git actuelle). La liste doit contenir leurs véritables upstreams légitimes
ou les agents doivent être explicitement migrés vers un autre modèle
réellement offert (ex. workstation-qwen). Confirmer la DB PostgreSQL
et les budgets avant de créer les clés virtuelles.

## 3 — Heartbeat : sauvegarde et scratch natif

Ne pas recopier le JSON GitOps dans ~/.openclaw et ne pas écraser le
HEARTBEAT.md historique. Le candidat est une checklist :
apps/openclaw/workstation/HEARTBEAT-RESTORED.candidate.md.

~~~bash
just openclaw-runtime-alignment-check
openclaw automations --help
openclaw automations list --all --json > /dev/null
openclaw config validate
~~~

Identifier le job heartbeat réel dans la UI native. L'ancien ID
bb9757db-9559-4960-bb23-9b9770929ff1 est historique et doit être
confirmé, ainsi que sa propriété et son état enabled/disabled.

~~~bash
HB_ID='bb9757db-9559-4960-bb23-9b9770929ff1'
HB_DIR="$HOME/.local/state/nabla-compose/openclaw/heartbeat-migration"
install -d -m 0700 "$HB_DIR"
openclaw automations get "$HB_ID" --json > "$HB_DIR/job-before.json"
openclaw automations scratch "$HB_ID" --json > "$HB_DIR/scratch-before.json"
chmod 0600 "$HB_DIR/"*.json
~~~

Les sauvegardes peuvent contenir du contexte privé : ne jamais les
committer ni les coller dans une conversation. Avant toute application :
attester 429, budget, version runtime, job exact et état de son timer.
Vérifier la version CLI : automations scratch --file et
--expected-revision doivent être supportés.

~~~bash
REV="$(python3 - "$HB_DIR/scratch-before.json" <<'PY'
import json, sys
from pathlib import Path
doc=json.loads(Path(sys.argv[1]).read_text())
revision=doc.get("currentRevision")
if type(revision) is not int or revision < 0:
    raise SystemExit("STOP: scratch revision unverified")
print(revision)
PY
)"
# MUTATION explicite, uniquement après feu vert et job heartbeat identifié.
openclaw automations scratch "$HB_ID" \
  --file apps/openclaw/workstation/HEARTBEAT-RESTORED.candidate.md \
  --expected-revision "$REV" --json > "$HB_DIR/apply-result.json"
chmod 0600 "$HB_DIR/apply-result.json"
~~~

Vérifier la révision et le SHA du nouveau scratch en privé. Si échec,
restaurer l'ancien scratch depuis scratch-before.json dans un fichier
temporaire 0600, puis réappliquer avec la nouvelle expected-revision.
Ne pas utiliser --set avec l'ancien texte privé (visible dans argv).
Ne pas activer le heartbeat tant que cost_budget_verified=false.
Les 14 fonctions historiques restent disabled ; jobs isolés distincts
pour briefing, digest, CalDAV, Gmail, WhatsApp et Obsidian.

## 4 — Cutover des agents, l'un après l'autre

Exiger avant mutation : TrueNAS healthy, DB valide, modèles et
deux clés virtuelles scoped distinctes main/cron confirmées, secrets
préservés dans Vaultwarden et backup des routes OpenClaw.

La commande suivante sur TrueNAS crée/modifie des clés ; NE PAS lancer
avant que le plan et les contrôles de persistance soient validés :

~~~bash
# Sur TrueNAS : MUTATION conditionnelle.
just openclaw-truenas-virtual-keys-apply
just openclaw-truenas-virtual-keys-status
just openclaw-truenas-virtual-keys-quota
~~~

Puis sur Workstation : préparer un patch de config privé avec les
SecretRef des clés appropriées et les routes
litellm-cron / litellm-main -> 172.17.0.24:4000/v1.
Ne pas publier la master key et ne pas remplacer tous les providers.
Valider par openclaw config patch --file PATCH_PRIVE --dry-run puis
appliquer explicitement, cron d'abord, main ensuite, avec rollback
par agent. Ne pas déclencher de génération durant les sondes.

~~~bash
just openclaw-429-triage-no-admin
just openclaw-migration-evidence-check
just openclaw-cron-recovery-plan
just openclaw-litellm-dual-logs-check
~~~

Un unique smoke facturable, uniquement si autorisé, peut ensuite
être exécuté via scripts/workstation/openclaw-ops.sh --smoke-model
(cooldown 24h), après contrôle de son modèle et de sa destination.

## 5 — DONE / STOP

- Scripts et politiques non secrets versionnés dans nabla-compose ;
  aucun blob git-crypt, token, session, sauvegarde dans Git public.
- Gateway versionné Node/systemd, readyz OK, diagnostics sans faux PASS.
- Deux LiteLLM observables avec permissions autorisées.
- TrueNAS : modèles runtime, PostgreSQL, quotas et clés scoped attestés.
- agent:cron:main, digest top=5, heartbeat révision/cadence vérifiés.
- Agents main/cron vraiment routés sur TrueNAS, rollback éprouvé.
- Le proxy Workstation reste disponible comme secours, et comme
  backend GPU optionnel de TrueNAS, avant retrait de l'ancien chemin.

Références : docs/runbooks/openclaw-recovery-gates-20261028.md,
docs/runbooks/openclaw-litellm-429-attribution.md,
docs/runbooks/openclaw-workstation-gitops-migration-20261027.md.

## Choix du transport OpenClaw -> TrueNAS

Le port direct `172.17.0.24:4000` en HTTP transmet les clés virtuelles
en clair sur le LAN. Pour une cible avec chiffrement, préférer le tunnel
SSH vérifié `http://127.0.0.1:14000/v1` (déjà pris en charge par
`just openclaw-truenas-tunnel-ensure`) ou une terminaison HTTPS fiable.
Le résolveur de routes présente le tunnel comme
`truenas_tunnel_candidate` tant que l'origine du processus SSH n'est
pas confirmée séparément. Prévoir la persistance et la supervision du
tunnel **avant** un cutover, sinon un reboot Workstation déconnecterait
les deux agents. Ne pas confondre son absence avec un 429 LiteLLM.
