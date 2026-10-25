# TrueNAS / Homelab — reprise des migrations et validations du 24 octobre 2026

> **Historique — état observé en octobre 2026.** Ce fichier conserve
> ses commandes et preuves à titre de traçabilité ; il n'est pas le point
> d'entrée pour un nouveau diagnostic. Lire d'abord
> [l'acceptation runtime courante](homelab-runtime-acceptance.md) et
> [la roadmap active](../roadmap.md). Aucune commande mutante ci-dessous
> n'est autorisée par cet archivage. La PR #274 est fusionnée.


**Statut documentaire : runbook spécialisé historique.** Pour la séquence opérateur actuelle, les résultats des gates et les points d'entrée, utiliser le [runbook de migration canonique](2026-10-24-homelab-operator-next-commands.md). Conserver ici les détails techniques de récupération propres à cette séance ; les états et PR cités sont des instantanés, non une preuve du runtime actuel.


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
  Le service `apps/hermes` (profil `hermes`, statut `planned`) remplace
  l'App native `hermes-agent`, à retirer manuellement (voir
  `apps/hermes/README.md`).

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


## Suivi opérateur du 23 octobre — quality gates et reprise Prometheus/OpenRAG

**Preuves exécutées par l'opérateur sur TrueNAS** : la gate de readiness
renvoie **72 passed**, celle des versions supportées **68 passed**.
Ces preuves valident les scripts et mocks du checkout testé, **pas** le
retour à la santé des Apps et pas l'ensemble du cluster Kubernetes.

### 1. Prometheus — redémarrages après réparation POSIX

Les permissions du fichier YAML sont passées à **uid 1000, gid 568,
mode 0640**. Le test effectif sous **UID:GID 568:568** avec
`setpriv ... /usr/bin/test -r` réussit sur l'hôte.
Mais le conteneur était encore `restarting` (exit 2, 884 restarts)
lors du dernier diagnostic live. Ne pas réappliquer le chmod,
effacer la TSDB ni redéployer toute la fondation.

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/repair-prometheus-config-access.sh --check
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
```

La seconde commande compare maintenant **la source montée sur
`/etc/prometheus`** au dossier source attendu, vérifie l'identité
`568:568`, classe l'accès effectif hôte et analyse séparément les logs
depuis le **ctime** du YAML (afin de ne pas attribuer des erreurs
antérieures à la réparation). Les chemins sources, secrets et logs bruts
ne sont pas imprimés.

**Condition de sortie** : Docker `running`, `/-/ready` HTTP 200,
PromQL `count(up)` exécutable, targets vérifiables. En cas de
`config_bind=mismatch`, confronter les sources de la TrueNAS Custom App
avant une éventuelle **réconciliation unique, revue et approuvée** ;
aucun automatisme ne la lance.

### 2. OpenRAG — frontend CREATED / Langflow partagé

La définition `apps/openrag/compose.yml` conditionne le démarrage du
frontend à `openrag-backend: service_healthy`. Il faut donc séparer
les états Docker backend/frontend de ceux de `langflow`, `opensearch`
et de l'optionnel `docling`.

```bash
just truenas-openrag-dependencies-check
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check
```

Aucune clé, ni mot de passe, ni document
`cpool/bababou` ne doit être affiché. Ne pas indexer à nouveau ni
redéployer OpenRAG tant que les dépendances et la définition TrueNAS
effective ne sont pas confirmées.

**Condition de sortie** : backend **et** frontend
`running+healthy`, Langflow et OpenSearch fonctionnels, puis tests
de recherche/ingestion Bababou et Docling réalisés séparément.

### 3. Ordre des migrations après récupération

1. Stabiliser Prometheus puis OpenRAG sans casser Gatus (85 moniteurs :
   59 UP, 26 DOWN lors du dernier contrôle), LiteLLM et InfluxDB.
2. Réconcilier **Scrutiny STOPPED** avec le chemin secret canonique
   `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets`, après
   `sudo bash scripts/truenas/deploy-scrutiny.sh --check` et vérification
   du token InfluxDB 2.9.1 ; préserver ses données existantes.
3. Examiner Sentry (web healthy mais consumers unhealthy), sans
   réinitialiser Kafka, offsets Snuba ou ClickHouse.
4. Exécuter `sudo bash scripts/truenas/finish-migrations-20261024.sh
   --check --section migrations`, puis `--section services`, `--section ai`
   et `--plan-wave core` **sans appliquer**.
5. Ne passer aux rafraîchissements d'images par lots et aux upgrades
   Talos/K8s qu'une fois toutes les gates fonctionnelles requises
   vertes et les risques d'indisponibilité explicitement acceptés.
   Aucun `--apply` n'est autorisé par ce constat seul.

**DefectDojo** : l'inventaire live PostgreSQL/Django rapporte uniquement
`admin` ; le bootstrap GitOps/Vaultwarden `nabla` ne correspond
pas à l'identité existante. Consulter
`docs/runbooks/defectdojo-admin-access-recovery.md` avant toute rotation.


## État observé à 20:58 le 23 octobre — relance ciblée

Les quality gates opérateur **postérieures aux nouveaux scripts** ont passé
sans GitHub Actions : 78 tests de readiness, 6 tests du diagnostic
OpenRAG, 37 tests de planification rapide.

### Prometheus : lire le blocage réel avant de réparer

État live observé : `restarting`, exit=2, 925 restarts,
`config_bind=match`, `container_identity=expected_568:568`,
`effective_host_config_read=ok`. **41 erreurs de permission** sont
apparues depuis la modification de `prometheus.yml`. Le compteur
`config=41 rules=41` était issu de catégories qui pouvaient se recouvrir :
il ne prouve pas à lui seul que le YAML principal et les règles sont
deux causes indépendantes.

Le diagnostic renforcé distingue maintenant :
- `rule_tree_access: files/denied/dirs/untraversable`, accès hôte
  effectif des fichiers YAML et dossiers sous `apps/prometheus/rules`;
- `since_config_change: config/rules/storage`, erreurs après le dernier
  changement de métadonnées du fichier principal, sans afficher les logs ;
- `docker_userns` et `daemon_userns` pour évaluer un mapping UID
  différent du contexte de test hôte.

```bash
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
```

Si les règles sont refusées en UID 568, ne corriger que les fichiers
identifiés par revue privée des ACL et de leur provenance. Si l'hôte
les autorise mais Docker refuse encore, ne pas conclure à une panne
TSDB : comparer user namespaces, politiques MAC/AppArmor/SELinux et
filesystem réellement visible au processus. Aucun `chmod -R`,
reset WAL, suppression de bloc ni `app.redeploy` automatique.

### OpenRAG : absence de nom canonique ≠ absence d'App

Le contrôle initial signalait :
`openrag-backend=missing`, `openrag-frontend=missing`,
`opensearch=missing`, alors que `langflow=running healthy`.
Le contrôle vérifie maintenant d'abord les noms canoniques puis les
labels Compose `com.docker.compose.project=ix-openrag` /
`com.docker.compose.service=openrag-backend|openrag-frontend` et
équivalents OpenSearch, ainsi que l'état middleware `app.query`.
Il refuse les correspondances ambiguës plutôt que de choisir au hasard.

```bash
just truenas-openrag-dependencies-check
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
```

Si aucun conteneur OpenRAG n'est présent même par ses labels, vérifier
les jobs/l'état `app.query`, le contenu Compose stocké dans TrueNAS et
la présence des dépendances. **Ne pas redéployer** tant que ces preuves
ne justifient pas une opération limitée. Préserver
`/mnt/cpool/bababou`, l'index OpenSearch et les clés OpenRAG.

### Migrations : résultats exacts du préflight

`migrations` : PASS=6 FAIL=3 — échecs
`live-language-patches`, `secrets-runtime`,
`openwebui-pra`.

`ai` : PASS=1 FAIL=3 — échecs
`openrag-dependencies`, `hermes-native`,
`ai-runtime-recovery`.

Les journaux d'acceptation restent privés, dans les dossiers de session
que le script annonce. Le libellé `see private report` ne démontre
aucune cause particulière : examiner localement les fichiers de
chaque gate avant une remédiation. **Ne pas utiliser `--allow-reviewed-drift`
pour contourner un défaut inexpliqué**, ni lancer les vagues Talos,
CSI ou bulk TrueNAS avant stabilisation du socle.

### DefectDojo

La tentative `python manage.py changepassword admin` s'est arrêtée
sur `CommandError: aborted` ; il n'y a pas de preuve de rotation.
La reprendre uniquement dans un vrai terminal interactif autorisé,
en saisissant et confirmant le mot de passe sans l'imprimer.
Ne pas relancer l'initializer ni modifier la base PostgreSQL.
