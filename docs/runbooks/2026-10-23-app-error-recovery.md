# Réparer les Apps TrueNAS en erreur — séance du 23 octobre 2026

> **Historique — état observé en octobre 2026.** Ce fichier conserve
> ses commandes et preuves à titre de traçabilité ; il n'est pas le point
> d'entrée pour un nouveau diagnostic. Lire d'abord
> [l'acceptation runtime courante](homelab-runtime-acceptance.md) et
> [la roadmap active](../roadmap.md). Aucune commande mutante ci-dessous
> n'est autorisée par cet archivage. La PR #274 est fusionnée.


**Statut documentaire : runbook spécialisé historique.** Pour la séquence opérateur actuelle, les résultats des gates et les points d'entrée, utiliser le [runbook de migration canonique](2026-10-24-homelab-operator-next-commands.md). Conserver ici les détails techniques de récupération propres à cette séance ; les états et PR cités sont des instantanés, non une preuve du runtime actuel.


**Objectif :** remettre LiteLLM puis Scrutiny et OpenRAG en service sans
masquer les causes avec un redéploiement massif. Les diagnostics sont
en lecture seule ; chaque commande de mutation est isolée et soumise à
validation opérateur. Ne jamais committer ni coller les tokens dans un log,
une issue ou dans ChatGPT.

## Ce que prouvent les logs fournis

- 06:41, 06:47, 06:52, 07:17 et **08:32** : LiteLLM `app.up` bloqué
  avant le démarrage par l'absence de
  `/mnt/cpool/secrets/runtime/litellm/.env.secrets`.
- 06:57 et 07:18 : Scrutiny `app.up` cherche encore
  **`/mnt/cpool/scrutiny/.env.secrets`**, ancien chemin, alors que
  `apps/scrutiny/compose.yml` déclare
  `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets`. Le manifeste
  réellement chargé par TrueNAS est probablement ancien : vérifier
  la configuration de l'App, ne pas créer un second secret divergent.
- 07:25 : `openrag-backend` est `unhealthy`. Le journal Compose
  ne fournit pas l'exception de l'application ; inspecter les logs
  localement, la dépendance Langflow/OpenSearch et le fichier
  `/mnt/cpool/openrag/.env.secrets`.
- Les autres erreurs historiques du journal, notamment Sentry,
  Scrutiny avant octobre ou Docker qui refuse de stopper certains
  conteneurs en septembre, **ne démontrent pas** leur état au 23 octobre.

## 0. Corriger le test qualité et obtenir la preuve de configuration

La PR #271 corrige le test `mise.lock` : les sous-tables TOML sont
**littéralement** nommées `platforms.linux-x64` et non
`platforms -> linux-x64`. Ce changement ne modifie pas les sommes
SHA-256 publiées. Tester sur un worktree isolé avant le merge :

```bash
cd /mnt/cpool/compose/nabla-compose
git status --short
git fetch origin feat/fast-batch-talos-k8s-services-20261023
git worktree add --detach /mnt/cpool/compose/nabla-pr271-check FETCH_HEAD
cd /mnt/cpool/compose/nabla-pr271-check
just upgrade-runtime-test
just truenas-ai-recovery-test
```

**Ne pas appliquer une mise à jour TrueNAS à partir de ce worktree** :
l'App peut monter des fichiers du checkout canonique
`/mnt/cpool/compose/nabla-compose`. Une fois les corrections
review/merge, exécuter les commandes sur `master` propre.

## 1. Inventaire d'erreurs en lecture seule

Depuis le checkout canonique TrueNAS :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo midclt call app.query |
  jq '[.[] | {id, state, upgrade_available, image_updates_available}]'
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check litellm
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check scrutiny
sudo bash scripts/truenas/diagnose-stuck-apps.sh --check \
  --app litellm --app scrutiny --app openrag
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check
```

Le nouveau script rapporte uniquement état/conteneur/présence de noms de
clés/permissions. Il **n'imprime jamais les valeurs** ni les logs Docker.
Les erreurs de permissions root ou fichier 0600 sont bloquantes. L'état
d'une App retourné comme `UNVERIFIED` signifie inconnu, pas `RUNNING`.
Tester également les stockages avant toute opération.

## 2. LiteLLM P0 — restaurer le secret canonique

**Ne jamais créer un `.env.secrets` vide** et ne pas placer la master
key dans Git ou dans la configuration Hermes.

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check litellm
command -v bw || echo 'Bitwarden CLI absent : vérifier la configuration opérateur'
bash scripts/truenas/configure-bitwarden-cli-local.sh --check
```

Le manifeste Vaultwarden utilise l'item exact
`nabla/prod/litellm` dans le dossier `TrueNAS`. Préserver
`LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, `LITELLM_IDE_API_KEY`,
`REDIS_URL` et `LANGFUSE_SECRET_KEY`. `ANTHROPIC_API_KEY` est
facultative jusqu'à son provisionnement réel : **ne pas inventer sa
valeur** ; ne pas activer Hermes/Opus cloud en son absence.

Si un ancien secret local valide existe, envisager uniquement après
revue `sudo bash scripts/truenas/bootstrap-repository-env-files.sh
--stage-existing litellm` (sans détruire l'ancien). Sinon, depuis la
session de l'opérateur **non-root** qui a accès à Vaultwarden :

```bash
# Dans un shell privé, après bw login / bw unlock.
# Ne jamais afficher ni partager BW_SESSION.
export BW_SESSION="$(bw unlock --raw)"
python3 scripts/secrets/materialize_runtime.py --app litellm --install
unset BW_SESSION

sudo stat -c '%U:%G %a %s %n' \
  /mnt/cpool/secrets/runtime/litellm/.env.secrets
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check
```

Résultat attendu : propriétaire `root:root`, permissions `600`,
fichier non vide, noms des clés obligatoires disponibles.
Si les contrôles passent, **autoriser explicitement** l'action isolée :

```bash
# Distinguer STOPPED de RUNNING : ne pas tirer de nouvelle image inutilement.
STATE="$(sudo midclt call app.query '[["id","=","litellm"]]' |
  jq -r '.[0].state // "MISSING"')"
case "$STATE" in
  STOPPED) sudo midclt call -j app.start litellm ;;
  RUNNING) sudo midclt call -j app.redeploy litellm ;;
  *) echo "LiteLLM state=$STATE : diagnostiquer avant mutation" >&2 ;;
esac
sudo midclt call app.query '[["id","=","litellm"]]' |
  jq '[.[] | {id,state,active_workloads}]'
sudo docker inspect litellm |
  jq '.[0] | {state: .State.Status, health: .State.Health.Status,
               exitCode: .State.ExitCode, restarts: .RestartCount}'
curl -fsS --connect-timeout 3 --max-time 8 \
  http://127.0.0.1:4000/health/liveliness
```

Si l'App échoue **après** cette étape, lire sur TrueNAS les logs locaux
(`sudo docker logs --tail 100 litellm`), en supprimant tous tokens,
URL privées et fragments de prompts avant partage. Distinguer :
fichier absent, erreur YAML/modèle provider, base PostgreSQL/Redis ou
clé de routage. En particulier ne pas réessayer indéfiniment
`app.redeploy` si les credentials cloud non fournis provoquent une
erreur de validation LiteLLM : corriger le profil ou attendre les clés.

## 3. Scrutiny P1 — corriger token ET ancien chemin déclaré

```bash
sudo bash scripts/truenas/diagnose-influxdb.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check scrutiny
sudo bash scripts/truenas/bootstrap-scrutiny-influxdb.sh --check
sudo bash scripts/truenas/diagnose-scrutiny.sh --check
```

Le secret attendu est `nabla/prod/scrutiny` dans Vaultwarden et
`/mnt/cpool/secrets/runtime/scrutiny/.env.secrets` sur TrueNAS.
Il doit contenir `SCRUTINY_WEB_INFLUXDB_TOKEN` et le marqueur de
portée v2. Si la configuration d'App chargée cherche encore le chemin
`/mnt/cpool/scrutiny/.env.secrets`, **ne pas dupliquer le token**
sous les deux chemins : il faut réconcilier le Custom App Compose.

Deux voies, à sélectionner après diagnostic :
- secret existant et compatible → vérifier l'item Vaultwarden,
  `python3 scripts/secrets/materialize_runtime.py --app scrutiny --install`
  en tant qu'opérateur non-root authentifié ;
- token de portée ancienne ou manquant → revoir
  `bootstrap-scrutiny-influxdb.sh --check` et la procédure de rotation
  `SCRUTINY_TOKEN_ROTATE=1` avec token admin InfluxDB **sans affichage**.
  Ne pas écraser l'ancien token par défaut.

Le déploiement déclaratif est déjà prévu par
`scripts/truenas/deploy-scrutiny.sh`. Il vérifie InfluxDB, les disques
SMART, le fichier canonique, puis met à jour la définition TrueNAS :

```bash
sudo bash scripts/truenas/deploy-scrutiny.sh --check
# Seulement si vérifications et plan de cutover sont approuvés :
# sudo env SCRUTINY_CUTOVER_APPROVED=1 \
#   bash scripts/truenas/deploy-scrutiny.sh --apply
```

Un état TrueNAS `STOPPED` ou `CRASHED` peut exiger une
réconciliation de l'App avant que le helper autorise `--apply` :
**ne pas supprimer l'App ni le dataset** sans inventorier les données.

## 4. OpenRAG P1 — dépendances avant restart

```bash
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
sudo midclt call app.query |
  jq '[.[] | select(.id == "openrag" or .id == "opensearch"
                    or .id == "langflow" or .id == "docling")
          | {id,state,active_workloads}]'
sudo docker inspect openrag-backend |
  jq '.[0] | {state: .State.Status, exitCode: .State.ExitCode,
               health: .State.Health.Status,
               oomKilled: .State.OOMKilled}'
```

Si `openrag-backend` existe, examiner localement
`sudo docker logs --tail 100 openrag-backend` **avec expurgation avant
partage**. Vérifier les accès réseau `opensearch:9200` et
`langflow:7860` depuis le réseau intranet, les identifiants OpenSearch,
le montage en lecture seule `/mnt/cpool/bababou` → `/mnt/bababou`
et le healthcheck `http://127.0.0.1:8000/health`.
Ne pas recréer un index/vector store ni supprimer le dataset.
Une erreur de healthcheck seule ne justifie pas de réinstaller Docling.

## 5. Puis reprise des migrations et upgrades

Seulement lorsque **LiteLLM démarre, Scrutiny est cohérent, les
dépendances OpenRAG sont validées**, exécuter :

```bash
just upgrade-runtime-test
sudo bash scripts/truenas/finish-migrations-20261024.sh --check
# Preview de l'inventaire d'images réellement mises à jour :
sudo python3 scripts/truenas/fast-bulk-redeploy-apps.py \
  --check --scope applications --parallel 4
```

Le script de redéploiement massif est une **opération de refresh d'images
et de restart** ; il ne corrige ni les fichiers de secret manquants,
ni les tags `latest` opaques, ni le catalogue de versions PHP/Python.
La stratégie d'upgrade Talos/K8s parallèle se trouve dans le runbook
`2026-10-23-fast-batch-migration.md`, à exécuter séparément
depuis la workstation.

En cas de nouvel échec d'App, relever seulement :
nom d'App, état TrueNAS, statut santé, code sortie, horodatage, type
d'erreur expurgé. Mettre à jour le diagnostic avant un nouveau restart.


## Addendum — diagnostic fonctionnel et sorties compactes (23 octobre, soir)

Les nouveaux journaux permettent un tri **sur les symptômes actuels**, sans
transformer les 13 Apps volontairement STOPPED en incidents :

| Service | Runtime observé | Cause / preuve manquante |
| --- | --- | --- |
| Gatus | STOPPED, conteneur restarting (centaines de relances) | `config/config.yml: permission denied` ; vérifier le GID apps 568 **dans le conteneur** ET le fichier `0640` / dossier traversable |
| LiteLLM | conteneur running mais Docker `unhealthy` | `/health/liveliness` HTTP répond ; inspecter le vrai échec de healthcheck Docker, ne pas conclure à une indisponibilité complète sur le seul état TrueNAS |
| OpenRAG | App DEPLOYING | backend running/**healthy**, frontend **created** ; le backend n'est plus le bloqueur constaté, vérifier le frontend et le `depends_on` avant tout restart |
| Scrutiny | App STOPPED ; token InfluxDB v2 valide | InfluxDB `2.9.1` running/healthy HTTP 200 ; la configuration déployée fait encore référence à l'ancien chemin env |
| Sentry | App DEPLOYING, web healthy | consommateurs Kafka/Snuba unhealthy ; messages `SESSTMOUT` et changement d'assignation, diagnostic Kafka avant toute reprise massive |
| FastAPI Sample | HTTP healthy, observer RBAC PASS | `build_revision=null` et Prometheus/Gatus shadow-only ; image runtime désormais comparée à l'image choisie, sans fausse preuve SHA |

Sur TrueNAS, après intégration du code de la PR #271 dans le checkout
canonique, utiliser les **vues courtes, sans logs bruts ni secrets** :

```bash
cd /mnt/cpool/compose/nabla-compose
just truenas-readiness-check
sudo python3 scripts/truenas/diagnose-service-readiness.py \
  --check --strict --service gatus --service litellm --service openrag
sudo bash scripts/truenas/diagnose-stuck-apps.sh --check
sudo bash scripts/truenas/finish-migrations-20261024.sh --check \
  --section services --color auto --icons auto
```

Les modes `--json` (rapport structuré) et `--color never --icons never`
facilitent l'archivage. Le mode `--strict` émet un code retour non-zéro
pour BLOCKED, DEGRADED ou UNKNOWN ; WARN ne suffit pas à déclarer l'App
totalement opérationnelle.

### Gatus — réparer la configuration sans toucher SQLite

```bash
sudo bash scripts/truenas/repair-gatus-config-access.sh --check
sudo bash scripts/truenas/deploy-gatus.sh --check
```

La commande `repair-gatus-config-access.sh --apply` est **limitée**
à `apps/gatus/config` : groupe `apps`, dossier `0750`, fichier `0640`.
Si `docker inspect gatus` n'inclut pas le GID 568, il faut d'abord faire
passer la **définition déployée** à la version Compose du dépôt ; le script
`deploy-gatus.sh --apply` réalise cette réconciliation et la réparation
conditionnelle, après validation opérateur. Ne jamais utiliser `chmod -R
777` ni modifier `/mnt/cpool/gatus/gatus.db`. Une fois l'API en ligne,
vérifier `/api/v1/endpoints/statuses` et la présence des moniteurs,
pas seulement le HTTP 200.

### LiteLLM — fichier déplacé et healthcheck Docker

Le fichier source `.env` était un **mélange de secrets et paramètres**.
Le déplacement manuel de `/mnt/cpool/secrets/runtime/litellm/.env` vers
`.env.secrets` a permis le chargement Compose, mais ne prouve ni
l'alignement avec l'item Vaultwarden `nabla/prod/litellm`, ni la
matérialisation attendue de `.env.compose`. Éviter de recopier
aveuglément ces valeurs ou d'afficher le contenu. Rapprocher uniquement
les **noms de clés**, modes et source d'autorité puis traiter la séparation
déclarative ; aucune copie automatique de valeurs entre dossiers.
La clé Anthropic non encore fournie reste optionnelle.

Une réponse `"I'm alive!"` ne suffit pas si Docker signale `unhealthy`.
Lire uniquement les catégories expurgées via
`diagnose-service-readiness.py --service litellm`, ou examiner en privé
`docker inspect litellm` (section Health uniquement). L'application doit
ensuite être testée avec un modèle local **autorisé**, via la clé proxy
de l'opérateur ; ne pas exposer la clé dans un `curl` collé au chat.

### OpenRAG, Sentry et InfluxDB : vérification des dépendances

Pour OpenRAG, la clé OpenSearch est déjà cohérente et le backend s'exécute
sans OOM. Le frontend resté CREATED doit faire l'objet d'une reprise
de son cycle Compose/TrueNAS **après** validation des services `langflow`
et `opensearch`. L'absence de Docling est un blocage fonctionnel pour
l'ingestion, pas nécessairement un échec du healthcheck du frontend.

Pour Sentry, distinguer la disponibilité du web de la santé des consommateurs.
Les messages `SESSTMOUT` demandent d'inspecter la stabilité du broker Kafka,
des groupes de consommation, des topics et des sessions avant tout
`app.redeploy`. Ne pas réinitialiser Kafka, ClickHouse ni les offsets.

InfluxDB v2.9.1 est healthy, mais son **scraper configuré** essaie
`172.17.0.24:30115/metrics` et reçoit `connection refused` :
la base est prête, le job de scraping ne fonctionne pas. La définition
Compose actuelle expose la base sur `127.0.0.1:31055` ; le dépôt contient
aussi d'anciens endpoints `:30115` dans `config/telegraf.conf`.
**Ne pas remplacer aveuglément** `/metrics` par `/health` ni transférer
un endpoint host-only vers un conteneur : identifier la source du scraper
et l'exporter attendu, puis supprimer/mettre à jour ce seul job si obsolète.

### Fetch GitHub bloqué depuis TrueNAS

Le code corrigé du test `mise.lock` est dans la PR, pas dans l'ancien
checkout ayant encore `talos["platforms"][platform]`. Si
`git fetch` ne peut pas joindre github.com:443, vérifier d'abord
`getent ahostsv4 github.com` puis `curl -4 -I --connect-timeout 5
--max-time 12 https://github.com`. Ne pas faire de `git reset --hard`
pour contourner le problème ni exécuter un script PR sous `master`
sans revue. Laisser les migrations --apply désactivées tant que
les nouveaux tests locaux ne peuvent pas être exécutés.



### Confirmations du 23 octobre, 19h — tests et résolution Gatus

- `just truenas-readiness-test` : **32 tests réussis en 0,15 s** depuis
  le checkout opérateur, aucun GitHub Actions. Le script de readiness
  indique HEALTHY=2 (LiteLLM, InfluxDB), WARN=1 (Sample), DEGRADED=1
  (Sentry), BLOCKED=4 (Gatus, OpenRAG, Scrutiny, Prometheus).
- `repair-gatus-config-access.sh --check` révèle exactement
  `config_dir gid=568 mode=750; config_file gid=568 mode=600`.
  Docker compte 766 redémarrages Gatus, `exit=2` et erreurs
  `permission denied`. Le stockage SQLite `gatus.db` existe et
  **doit conserver son identité**.
- **Correction opérateur immédiate** (sur checkout actuel) :
  `sudo bash scripts/truenas/repair-gatus-config-access.sh --apply`
  puis `--check`. Cela ne change que la configuration générée (640),
  pas les données, pas le réseau, pas les secrets. Observer ensuite
  `docker inspect gatus` et `midclt app.query`. Si l'App reste
  STOPPED, `sudo midclt call -j app.start gatus` est un choix explicite.
- **Correctif dans la PR #271** : `deploy-gatus.sh --apply` vérifie et
  répare maintenant les permissions **avant** `app.update/redeploy`,
  puis préfère `app.start` si l'App réconciliée est STOPPED. Le
  `--check` affiche la cause de permissions en premier. Toute mutation
  reste explicite ; le script n'altère pas `gatus.db`.
- **Prometheus** : App RUNNING mais conteneur `restarting` et API
  :9090 indisponible. Le nouveau `diagnose-prometheus-targets.sh
  --check` s'arrête rapidement dans cet état et classe les erreurs
  des 80 dernières lignes (permission, config, stockage, OOM) sans
  afficher les logs. **Cause précise encore non prouvée**.
- **GitHub** : `getent ahostsv4 github.com` résout et
  `curl -4 -I https://github.com` retourne HTTP/2 200 : l'accès
  HTTPS depuis TrueNAS est revenu pour ce test. Retenter un
  `git fetch` sur le repo **sans forcer un reset** ; cela ne prouve
  pas à soi seul l'authentification du remote Git.


### Contrôles post-réparation Gatus et diagnostic Prometheus (23 octobre)

Le retour opérateur confirme désormais **Gatus RUNNING** après correction du
fichier généré en GID 568 et mode 0640, avec base SQLite conservée. Cela
**ne confirme pas encore** que tous les moniteurs sont présents ou à jour.
Exécuter en lecture seule :

```bash
sudo bash scripts/truenas/diagnose-gatus.sh --check
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
```

Le diagnostic Gatus résume exclusivement le **dernier résultat** de chaque
moniteur (`monitors/up/down/pending/unknown`), sans afficher les noms, URL,
tokens ni réponses. Les cibles DOWN sont un **WARN de monitoring** et
n'indiquent pas à elles seules un incident du service Gatus. Une liste vide
ou un JSON de format inattendu bloque la confirmation de couverture.
Rapprocher ensuite le nombre observé de l'inventaire déclaratif.

Pour Prometheus, si le conteneur reste `restarting`, le diagnostic affiche
maintenant le code de sortie, `OOMKilled`, le compteur de redémarrages et les
métadonnées Unix des chemins configuration/TSDB, uniquement lorsqu'elles sont
disponibles. Il conserve la classification expurgée des dernières erreurs.
**Ne pas utiliser** `docker inspect --format '{{json .State}}'` dans un
rapport partageable : les journaux Health peuvent contenir des informations
sensibles. La cause précise n'est pas encore attestée. Conserver
`/mnt/cpool/prometheus/data` et éviter `app.redeploy` avant diagnostic.


### Confirmations opérateur : readiness et remédiation Prometheus (23/10)

Dernière exécution sur TrueNAS : `upgrade-runtime-test` **68/68 PASS** ;
`truenas-readiness-test` 42 PASS / 1 FAIL à cause du mock Docker
`inspect --format` ne reconnaissant plus que le premier format ;
`truenas-readiness-check` détecte **Prometheus restarting exit=2 (855
restarts), config POSIX non lisible par UID/GID 568**, OpenRAG frontend
CREATED, Scrutiny STOPPED, Sentry consumers unhealthy, et FastAPI SHA
non attesté. C'est une photographie datée, **pas une vérification live**.

Gatus est RUNNING et répond HTTP 200 sur
`/api/v1/endpoints/statuses`. Le diagnostic indépendant confirme
**85 moniteurs (59 UP, 26 DOWN)**, zéro pending/unknown.
La sonde readiness limitait historiquement la réponse JSON à 64 KiB,
ce qui produisait un faux UNKNOWN. Elle accepte maintenant au plus
4 MiB et rend un WARN de couverture pour les moniteurs DOWN, **sans
confondre la disponibilité de Gatus avec celle des cibles**. Les noms,
URLs et détails des moniteurs ne sont pas publiés.

La configuration Prometheus est un fichier en `uid=1000,gid=568,
mode=0600`, tandis que le Compose exécute le processus en `568:568`.
Le stockage TSDB est un **répertoire séparé** `/mnt/cpool/prometheus/data`
(group 568, mode 0770) ; aucune réparation TSDB n'est justifiée par ces
preuves. Le montage réel doit être vérifié avant toute mutation :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/repair-prometheus-config-access.sh --check

# Une fois le montage /etc/prometheus et l'utilisateur 568:568 confirmés,
# et seulement si --check signale l'absence de lecture de groupe :
sudo bash scripts/truenas/repair-prometheus-config-access.sh --apply

# Sans relancer manuellement tous les conteneurs :
sudo bash scripts/truenas/repair-prometheus-config-access.sh --check
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
just truenas-readiness-check
```

Le script `--apply` n'altère que
`apps/prometheus/prometheus.yml` : `chgrp 568`, `chmod 0640`,
avec garde sur le montage et l'UID/GID en cours. Il ne redémarre rien
et ne touche ni WAL, ni blocs TSDB, ni offsets ni rétention.
Le conteneur en boucle de redémarrage peut repartir automatiquement ;
si la permission reste refusée, contrôler les ACL ZFS et les dossiers
traversés, **sans remplacer les ACL en masse**. Contrôler ensuite
`/-/ready`, PromQL et les targets.

Quality gate locale après synchronisation **sans rebase de worktree sale**
et sans déclenchement de CI payante :

```bash
just truenas-readiness-test
python3 -m pytest -q tests/test_prometheus_config_access_repair.py \
  tests/test_gatus_api_diagnostic.py
just upgrade-runtime-test
```


### Suivi du 23 octobre : Prometheus toujours restarting après chmod 0640

Retour opérateur : le fichier `apps/prometheus/prometheus.yml` est maintenant
`uid=1000 gid=568 mode=0640`, mais Prometheus reste `restarting`, exit 2,
884 redémarrages. Les dernières lignes de logs indiquent toujours
`permission denied` sur `prometheus.yml`; la TSDB
`/mnt/cpool/prometheus/data` est restée en `568:568 mode=0770`.
Aucune suppression de WAL/TSDB ni relance massive n'est indiquée.

Le précontrôle `repair-prometheus-config-access.sh --check` vérifie désormais
aussi la lecture **effective** du fichier sur le système hôte en UID/GID
`568:568` via `setpriv` (si disponible), sans lire ni afficher son contenu.
Si cet accès échoue, examiner les ACL ZFS et l'accès aux répertoires parents.
S'il réussit mais que Docker échoue encore, examiner le bind mount
`/etc/prometheus`, les erreurs de démarrage récentes et les différences
d'accès au conteneur plutôt que refaire `chmod`.

```bash
sudo bash scripts/truenas/repair-prometheus-config-access.sh --check
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
# Métadonnées uniquement, jamais .State.Health.Log :
sudo docker inspect prometheus --format \
  'user={{.Config.User}} state={{.State.Status}} restarts={{.RestartCount}}'
sudo docker inspect prometheus --format \
  '{{range .Mounts}}{{if eq .Destination "/etc/prometheus"}}{{println .Source .Destination .RW}}{{end}}{{end}}'
```

Les neuf échecs sur 67 tests concernent les stubs Docker/cURL/getent
créés sous `/tmp/pytest-...` : un `/tmp` monté en `noexec` est plausible,
mais non confirmé. Les mocks ont été rendus exécutables **via Bash**,
indépendamment des droits d'exécution de `/tmp`, et cette régression est
ajoutée à la gate locale. Pour identifier cette cause :

```bash
findmnt -no OPTIONS --target /tmp
just truenas-readiness-test
just upgrade-runtime-test
```

Gatus RUNNING / API 200, 85 moniteurs, 59 UP et 26 DOWN : traiter ces
cibles séparément, sans redémarrer Gatus.

### 23 octobre — résolution ciblée de deux règles Prometheus illisibles

Dernière preuve opérateur : Prometheus `restarting` / exit=2 /
958 redémarrages. Le bind `/etc/prometheus` correspond au dossier GitOps,
l'identité Docker est `568:568`, `prometheus.yml` est lisible sur l'hôte,
et Docker n'annonce pas de user namespace. **15 fichiers YAML de règles**
ont été inspectés, **2 refusent la lecture** sous `setpriv 568:568`.
Le dossier des règles est traversable. Les logs récents donnent
`config=0 rules=74 storage=0`. L'ancienne catégorie
`root_cause=prometheus_config_permission_denied` issue de la fenêtre
historique est désormais remplacée par une priorité donnée aux
**règles illisibles prouvées sur l'hôte**.

Un nouvel outil opère à l'échelle **du fichier de règle** et
préserve les autres règles, leurs contenus, l'owner, le YAML principal,
la TSDB, le WAL et tout le runtime Docker.

Préflight en lecture seule (retour non nul tant que les règles sont
illisibles) :

```bash
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check
```

Il doit afficher `rules_total=15`, `dirs=1`, `unreadable=2` :
chaque entrée défaillante possède seulement un index, un UID, un GID,
un mode POSIX et un type, **jamais le nom ni le contenu du fichier**.
La comparaison du groupe `apps=568`, de l'identité Docker
`568:568`, de la source du bind et l'interdiction des symlinks
sont bloquantes.

Si exactement deux fichiers restent illisibles, le propriétaire du
homelab peut approuver **cette correction limitée uniquement** :

```bash
sudo bash scripts/truenas/repair-prometheus-rules-access.sh \
  --apply --expected-unreadable 2 \
  --acknowledge I_ACCEPT_PROMETHEUS_RULES_PERMISSION_REPAIR
```

`--apply` utilise `chgrp 568` et `chmod 0640` **seulement sur les
fichiers refusant la lecture**, avec vérification d'inode, puis
`setpriv` et test de lecture effectif après chaque changement.
Il ne redémarre aucun conteneur. Si l'ACL ZFS refuse encore,
le script s'arrête sans élargir les permissions ni réécrire l'ACL.

Validation après correction :

```bash
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
just truenas-readiness-check
```

Les conditions de sortie sont `unreadable=0`, Docker
`prometheus=running`, `/-/ready` HTTP 200 et API/targets Prometheus
interrogeables. Si la politique de redémarrage Docker ne relance pas le
processus malgré les règles lisibles, diagnostiquer son état **avant**
de décider une unique reprise contrôlée. Ne pas effacer
`/mnt/cpool/prometheus/data` et ne pas démarrer de vague de migration
globale dans cet état.

Tests prévus en local, sans GitHub Actions :

```bash
just truenas-prometheus-rules-test
just truenas-readiness-test
```
