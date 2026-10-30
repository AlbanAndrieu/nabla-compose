# OpenClaw — diagnostic multi-hôte et GitOps cron (30 octobre 2026)

## Objectif et état

PR #295. `nabla-compose` reste la source de vérité **non secrète** ;
le Gateway OpenClaw et sa base d'état SQLite restent privés sur la
Workstation. La configuration versionnée n'est pas chargée magiquement
au démarrage : un opérateur exécute `plan` puis `apply` **une seule
fois par changement validé**. Pas de `git checkout` dans
`~/.openclaw`, pas de symlink, pas d'édition manuelle de SQLite.

Éléments observés le 30 octobre :
- OpenClaw **Workstation** : Gateway et Node PASS, readiness HTTP 200 ;
- **TrueNAS** : ne pas tester un Gateway OpenClaw local ; LiteLLM répond
  200 sur son inventaire authentifié, deux clés existantes ;
- modèles TrueNAS **sans** `gpt-4.1`/`gpt-4.1-mini` ; pas de cutover
  vers ces modèles avant choix du backend `workstation-qwen` ;
- job `daily-tech-news-digest` : `ITEMS_PER_SECTION=3-5` incompatible
  avec le paramètre entier `--top`, cible `5` ;
- agent `cron` présent, session `agent:cron:main` absente ;
- heartbeat actuel = `skipped_empty`, aucune inférence confirmée.

## Hôte automatiquement identifié

Le script `openclaw-host-context.py` examine en premier
`midclt call system.version` ; si TrueNAS est confirmé, il **n'exécute
pas** les contrôles de Gateway, sessions, digest et tunnel Workstation.
Sur Linux non-TrueNAS, il exige une configuration `~/.openclaw`
et une unité systemd OpenClaw chargée. Si les preuves manquent :
`host_context=unknown`, avertissement jaune et refus des probes runtime.

```bash
cd ~/w/nabla-compose
just openclaw-host-context
just openclaw-host-context-test
just openclaw-migration-evidence-test
just openclaw-migration-evidence-check
```

Le rapport est compact : ✅ succès, ⚠️ preuve manquante, synthèse
avec le nombre de probes. `NO_COLOR=1` retire les codes ANSI ; le
mode détaillé `OPENCLAW_DIAG_VERBOSE=1 just
openclaw-migration-evidence-check` montre les sorties des
diagnostics existants **et doit rester privé**. Ne pas coller les logs
bruts ou les valeurs de secrets dans un ticket public.

Depuis TrueNAS, la collecte LiteLLM peut lire le conteneur **local**
avec l'option sudo déjà autorisée :

```bash
just openclaw-litellm-dual-logs-check-sudo
```

Elle indique les logs Workstation comme non collectés et **ne prétend
pas** `coverage=both`. Pour les deux sources, lancer la même commande
sur Workstation, qui utilise un SSH vers TrueNAS (host key vérifiée),
pas vers elle-même. `sudo -n` est explicite, jamais automatique ;
aucun groupe Docker ou ACL n'est modifié.

## GitOps : corriger le digest sans créer un deuxième cron

### Source

- `ops/openclaw-workstation/cron/daily-tech-news-digest.policy.json` :
  identité attendue, planification indicative, budget et séparation
  des permissions de livraison ;
- `ops/openclaw-workstation/cron/daily-tech-news-digest.message.md` :
  **message public complet**, sans identifiants ni destinataires, avec
  `- ITEMS_PER_SECTION = 5` et `--top 5` ;
- `scripts/workstation/reconcile-openclaw-digest-cron.py` :
  lecture native du job par ID, calcul de drift, sauvegarde privée,
  modification CLI native et vérification de résultat.

Seul `payload.message` est ciblé. Pour l'application, le message
runtime doit encore correspondre au contrat installé
`references/digest-prompt.md` avec exactement une occurrence
`ITEMS_PER_SECTION = 3-5`. Si sa structure a changé ou contient
d'autres personnalisations non prévues, **STOP et revue privée dans
la Control UI** plutôt qu'un écrasement automatique.
Le script refuse un mauvais nom,
un mauvais ID, un payload non conforme, une modification concurrente
constatée ou une source avec secret détectable. Il préserve
`schedule`, `delivery`, `agentId`, `sessionTarget`,
`enabled` et les autres champs du payload. **Aucune création
d'automation** ni invocation de modèle.

### 1 — Tests et plan en lecture seule (Workstation)

```bash
just openclaw-digest-gitops-test
just openclaw-digest-gitops-plan
```

La sortie affiche uniquement deux SHA-256, jamais le prompt privé :

```text
cron_gitops=existing_job_only
runtime_message_sha256=<hash>
desired_message_sha256=<hash>
cron_gitops=drift
```

Vérifier la modification fonctionnelle du **message cible versionné**
avant l'application. Les données de livraison et les URL privées ne
doivent pas être ajoutées au fichier Git.

### 2 — Apply explicite, sur Workstation uniquement

```bash
# Remplacer par la valeur runtime_message_sha256 reçue du plan.
just openclaw-digest-gitops-apply <hash-64-caracteres>
just openclaw-digest-gitops-check
just openclaw-digest-top-check
```

L'apply requiert le hash précédent, refuse un message modifié depuis
l'inspection et sauvegarde la définition antérieure en `0600` sous
`~/.local/state/nabla-compose/openclaw/digest-gitops/`. Les
destinataires privés existants sont conservés par l'API de patch,
pas sérialisés dans Git. L'argument `--message` de la CLI contient
**uniquement le message public versionné**, jamais l'ancien prompt
privé ; il peut donc apparaître temporairement dans la liste de
processus sans révéler de secret.

⚠️ La commande native `automations edit` ne fournit pas de contrôle
CAS sur la totalité du job comparable à `scratch
--expected-revision`. Le script relit le job avant l'édition,
vérifie après et bloque en cas de dérive observée, mais une course
millisecondes reste théoriquement possible. Si cela importe, geler les
modifications de l'automation pendant le cutover.

Pour le rollback, utiliser la Control UI avec la sauvegarde privée,
**pas** `--message "<ancien prompt privé>"` en argv ou Git.
Après restauration, relancer plan/check et vérifier le
hash message de référence.

### 3 — Vérification runtime

```bash
just openclaw-digest-top-check
just openclaw-cron-recovery-plan
just openclaw-cron-parent-check
```

Le digest `--top` valide ne prouve pas encore une génération réussie.
La session `agent:cron:main` est un problème **distinct** :
elle ne doit pas être créée automatiquement par un reconciler cron.
Ne faire un tour de test explicite qu'après vérification des clés,
du modèle et du coût éventuel. Les 100 exécutions ignorées du
heartbeat ne sont pas des pannes et ne doivent pas être « réparées »
en réactivant tous les anciens jobs.

## Git dirty : commit du submodule et gitlink dans le bon ordre

`? n8n` et `? sentry` sont des changements locaux à inspecter ;
ne pas les supprimer ni les ajouter automatiquement. Pour
` M fastapi-sample` :

```bash
git -C fastapi-sample status --short
git -C fastapi-sample diff --stat
git -C fastapi-sample diff --cached --stat
```

Si les modifications source **dans le submodule** sont voulues :

```bash
git -C fastapi-sample add -- <fichiers-validés>
git -C fastapi-sample diff --cached --check
git -C fastapi-sample commit -m "fix: changements validés [skip ci]"
git add -- fastapi-sample
git diff --cached --submodule=log
git commit -m "chore(submodules): record fastapi-sample pointer [skip ci]"
```

Si le submodule ne doit pas changer, ne pas créer de commit :
résoudre les changements internes dans son propre dépôt d'abord.
Lancer ensuite `update-application-submodules.sh --check` puis
`--update` seulement quand les gitlinks et worktrees sont propres.
Un `git add -- fastapi-sample` seul n'enregistre **pas** des
modifications non committées à l'intérieur du submodule.

## Infrastructure as Code OpenClaw — règles

1. **Déclaratif Git** : nom, ID stable, message, intention de cadence,
   budget, modèle, tests. Aucun secret ou cible privée dans Git public.
2. **Diff avant mutation** : identification ID/nom, comparaison par hash
   et plan documenté. Ne pas récréer un job déjà présent.
3. **Écriture via CLI/RPC native** : la DB SQLite n'est jamais un backend
   IaC ; la migration des anciens jobs est faite une seule fois, puis
   les mises à jour passent par `automations edit`.
4. **Snapshots et rollback** : sauvegarde privée chiffrable, permissions
   0600, conservation de l'ancien prompt uniquement hors Git.
5. **Gates de runtime** : droits, readiness, budget, modèles, 429,
   dépendances et mise en place contrôlée de l'activation.
6. **Déploiement manuel local-first** : les commits Git [skip ci]
   ne changent pas le runtime OpenClaw tant qu'un opérateur n'a pas
   appliqué une nouvelle version approuvée.

Références upstream :
https://docs.openclaw.ai/cli/cron
https://docs.openclaw.ai/automation/cron-jobs/how-it-works
https://docs.openclaw.ai/automation/cron-jobs/payloads
