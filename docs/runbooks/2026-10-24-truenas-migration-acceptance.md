# TrueNAS / Homelab — reprise des migrations et validations du 24 octobre 2026

**Statut : plan opérateur temporaire, PAS un déploiement automatique.**
Source : `scripts/truenas/finish-migrations-20261024.sh` (PR #270).
Exécuter sur TrueNAS **seulement depuis la copie Git déclarative dont la
révision et les chemins ont été vérifiés**. Ne pas redémarrer TrueNAS/pfSense,
réinitialiser Docker/ZFS/CSI, supprimer les datasets ou réimporter des secrets
pendant cette reprise.

## 0. Préparer le code et les garde-fous

L'App TrueNAS peut monter des fichiers du checkout canonique
`/mnt/cpool/compose/nabla-compose`. **Ne pas remplacer silencieusement ce
checkout par une branche PR** : cela peut modifier immédiatement un bind
mount utilisé par une App en cours d'exécution.

- Tant que la PR #270 est Draft, récupérer les sources via un **worktree
  isolé et en lecture seule pour les commandes `--check` uniquement** :

```bash
cd /mnt/cpool/compose/nabla-compose
git status --short
git fetch origin feat/hermes-anthropic-opus-fallback-20261023
git worktree add --detach /mnt/cpool/compose/nabla-migration-check-20261024 FETCH_HEAD
cd /mnt/cpool/compose/nabla-migration-check-20261024
git rev-parse HEAD
bash -n scripts/truenas/finish-migrations-20261024.sh
python3 -m pytest -q tests/test_finish_migrations_20261024.py
sudo bash scripts/truenas/finish-migrations-20261024.sh --check
```

Les artefacts déclaratifs du worktree de contrôle doivent être comparés au
catalogue du checkout réellement déployé avant de faire un `--apply`.
**Ne pas appliquer depuis le worktree isolé** : plusieurs scripts de migration
s'appuient sur le chemin canonique du dépôt pour leurs fichiers Compose.

- Après revue/merge de la PR et lorsque la fenêtre opérateur est acceptée,
  actualiser le checkout canonique par `git pull --ff-only` **uniquement si
  `git status --short` est propre et le HEAD est attendu**, puis relancer
  les mêmes contrôles depuis ce checkout. Ne jamais utiliser `git reset
  --hard` pour forcer cette migration.

- Les résultats sont consignés dans
  `/mnt/cpool/var/nabla/migration-20261024/session-*/` (mode 0700 ; logs
  0600). Ils peuvent révéler des métadonnées sensibles : ne pas les
  coller dans un ticket ou dans ce chat sans revue/redaction.

## 1. Inventaire et préflight — lecture seule

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/finish-migrations-20261024.sh --check
# Plus rapide pour investiguer, sans reproduire la totalité :
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section migrations
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section catalog
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section services
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section ai
```

Les sections suivantes appellent les scripts existants :

| Section | Vérification |
| --- | --- |
| platform | santé générale, orphelins Docker, Pi-hole DNS sync, PostgreSQL/données partagées |
| migrations | manifeste et runtime secrets, Sentry système/migrator, OpenRAG/OpenSearch, préflight DefectDojo, OpenWebUI PRA |
| catalog | trois plans **indépendants** core/Gatus/deferred et leurs `planHash`, blocages crosswalk et secrets |
| services | Gatus, Sentry, DefectDojo, Cyberbro, Prometheus, états TrueNAS |
| ai | diagnostic Hermes natif et présence/permissions des clés cloud LiteLLM |
| talos | diagnostics cluster et CSI NFS **uniquement si** `kubectl` et `talosctl` sont accessibles à l'opérateur |

Un `FAIL` signifie **non validé**, pas forcément service indisponible.
Les clés Anthropic peuvent manquer normalement : **ne pas redéployer
LiteLLM ni Hermes** ; laisser cette gate bloquante jusqu'à réception des
secrets, contrôles de confidentialité, quotas et compatibilité modèle.
`SKIP` ne signifie **jamais PASS**.

## 2. Migrations ciblées avec approbation explicite

Effectuer les réparations seulement si leur préflight le justifie, après
inspection des logs privés et sauvegarde/rollback applicatif vérifiés.
Chaque commande refuse l'absence d'acquittement explicite :

```bash
# Une seule opération à la fois, suivie de son propre --check.
sudo bash scripts/truenas/finish-migrations-20261024.sh \
  --apply-step sentry-system --acknowledge I_ACCEPT_REVIEWED_RUNTIME_MIGRATION
sudo bash scripts/truenas/finish-migrations-20261024.sh \
  --apply-step sentry-migrator --acknowledge I_ACCEPT_REVIEWED_RUNTIME_MIGRATION
sudo bash scripts/truenas/finish-migrations-20261024.sh \
  --apply-step openrag-secret --acknowledge I_ACCEPT_REVIEWED_RUNTIME_MIGRATION
sudo bash scripts/truenas/finish-migrations-20261024.sh \
  --apply-step gatus-config --acknowledge I_ACCEPT_REVIEWED_RUNTIME_MIGRATION
```

Un `--check` qui échoue bloque l'`--apply-step`. Si cet échec est un
**drift explicitement attendu**, on peut réexécuter **une seule** commande,
après lecture du log privé et validation de la correction, avec
`--allow-reviewed-drift`. Le rapport porte alors `WARN`, jamais un
faux `PASS`. Aucune étape ne copie ni affiche directement les secrets.

Les autres migrations demandent une action opérateur indépendante, non
orchestrée en masse :

- **Secrets Vaultwarden** : vérifier `config/secrets/manifest.json` et
  `scripts/secrets/render_from_bitwarden.py --help` ; matérialiser un
  service à la fois en root/0600, utiliser
  `scripts/secrets/materialize_runtime.py --help` et contrôler l'intégrité
  avant rechargement. Ne pas recopier une clé dans Git ou les logs.
- **DefectDojo** :
  `sudo bash scripts/truenas/preflight-defectdojo.sh` et
  `sudo bash scripts/truenas/diagnose-defectdojo.sh --check`. Vérifier
  base, workers, certificat, accès privé et rapports ; aucune ouverture WAN.
- **Docling / OpenRAG** : commencer par
  `sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check docling`,
  `sudo bash scripts/truenas/diagnose-openwebui-backup-pra.sh --check` et le
  runbook `docs/runbooks/openrag-babou-ingestion-diagnostics.md`.
  **Ne pas appeler `deploy-docling.sh` automatiquement : il applique réellement
  une modification, sans `--check` propre.** Vérifier le dataset
  `cpool/bababou` (cible `/mnt/bababou`) en lecture seule d'abord.
- **Hermes/Anthropic** :
  `sudo python3 scripts/truenas/check-litellm-hermes-credentials.py --check`.
  Tant que `ANTHROPIC_API_KEY` n'est pas fournie et que les quatre modèles,
  les budgets et le logging ne sont pas validés, garder la bascule bloquée.
  Le profil expérimental `poc/hermes` n'est pas l'App native installée.

## 3. Redémarrer uniquement une vague approuvée

**Aucune vague n'est lancée par `--check`.** Le plan et son empreinte sont
spécifiques à l'état live TrueNAS **et** à la vague choisie. La commande
sous-jacente est `restart-catalog-v2-apps.py`, qui reprend un snapshot
frais sous verrou exclusif et vérifie l'empreinte avant mutation.

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh --plan-wave core
# Lire le JSON privé catalog-core.json et vérifier :
# selectedWaveReady=true, coreDependencyBlockers=[], blockedCoreApps=[],
# missingRunningSecrets=[], unverifiedRunningSecrets=[].
# Le core redémarre séquentiellement des Apps déjà RUNNING :
# planifier explicitement la fenêtre d'indisponibilité.

# Remplacer les 64 caractères ci-dessous par le planHash du plan VIVANT
# tout juste contrôlé : ne PAS copier le hash d'un autre wave.
HASH='<planHash-core-de-64-caracteres>'
sudo bash scripts/truenas/finish-migrations-20261024.sh --apply-wave core \
  --expected-plan-hash "${HASH}" \
  --acknowledge I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART

# Gatus en transaction distincte, uniquement après stabilisation du core.
sudo bash scripts/truenas/finish-migrations-20261024.sh --plan-wave gatus
# Puis --apply-wave gatus + SON empreinte fraîche et le même acquittement.

# Dernière vague, applications facultatives STOPPED explicitement listées.
sudo bash scripts/truenas/finish-migrations-20261024.sh --plan-wave deferred
# Inspecter deferredDependencyBlockers, deferredStartOrder et les secrets.
# Puis --apply-wave deferred + SON empreinte fraîche et l'acquittement.
```

Si le plan change (hash), **arrêter l'exécution**, recalculer, revoir et
ré-approuver. Ne pas lancer plusieurs vagues en parallèle, ne pas redémarrer
le host TrueNAS, ne pas réinitialiser Docker et ne pas monter les Apps
facultatives `STOPPED` par défaut. Un échec de healthcheck doit interrompre
la suite ; préserver le journal `catalog-v2-*.jsonl`.

## 4. Acceptation post-migration

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh --check
sudo bash scripts/truenas/check-homelab-services.sh --deep
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
sudo bash scripts/truenas/diagnose-sentry.sh --check
sudo bash scripts/truenas/diagnose-defectdojo.sh --check
sudo bash scripts/truenas/diagnose-hermes-agent.sh --check
```

Sur une **workstation autorisée** disposant de `mise`/kubectl/talosctl et
de sa kubeconfig (pas en tant que root sans nécessité) :

```bash
cd ~/w/nabla-compose
mise exec -- bash scripts/talos/validate-cluster.sh
mise exec -- bash scripts/talos/smoke-truenas-csi-nfs.sh --check
```

Le smoke CSI `--apply` crée volontairement des Pods/PVC éphémères et
contrôle le reclaim sur TrueNAS : ne l'exécuter que depuis un environnement
opérateur possédant **kubectl et les APIs TrueNAS/ZFS** appropriées, avec
autorisation spécifique. Le wrapper inclut un `--apply-csi-smoke` séparé ;
il n'est jamais appelé par les contrôles par défaut.

Critères de clôture : services prioritaires réellement `RUNNING`, leurs
healthchecks et probes fonctionnels, Gatus/Prometheus observés, migrations
Sentry et secrets acceptées, aucune dépendance core bloquée, CSI validé si
testé, RPO OpenWebUI documenté. Inscrire tout FAIL/SKIP restant dans la
roadmap avant fermeture, conserver une preuve expurgée, puis retirer le
**script temporaire** dans une PR distincte après acceptation opérateur.
