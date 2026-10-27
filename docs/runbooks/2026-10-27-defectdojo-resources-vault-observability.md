# 27 octobre 2026 — Ressources RUNNING, DefectDojo DEPLOYING, Vaultwarden et H-05/H-06

## Réception actualisée — preuves opérateur du 27/10 (18:47–18:53 UTC)

Ces résultats **supplantent l'ancien état `DEPLOYING`** pour DefectDojo.
Ils restent des preuves ponctuelles, pas des SLA.

### DefectDojo restauré sans réinitialisation de base

- Avant reprise : aucun job TrueNAS `app.*` DefectDojo `RUNNING`/`WAITING` ;
  initializer `exited(0)`, quatre dépendants `created`.
- Reprise manuelle ciblée : `docker start defectdojo-uwsgi`,
  `docker start defectdojo`, puis `docker start` des deux Celery ;
  **aucun `app.redeploy` ni `DROP DATABASE`**.
- `python manage.py changepassword admin` : **mot de passe changé avec succès**
  dans Django (la commande mutante a bien changé le hash, indépendamment
  du champ `database_modified=false` émis par le diagnostic read-only).
- Diagnostic après reprise : `app_state=RUNNING`, `origin_http=200`,
  initializer `exited(0)`, uWSGI/Nginx/Celery Worker/Celery Beat
  `running`, aucun `OOMKilled` signalé pour ces conteneurs.
  Ce résultat ne valide **ni un login Web authentifié**, ni un E2E Celery,
  ni la persistance du démarrage après le prochain cycle TrueNAS.
- La première requête HTTP après `docker start defectdojo` renvoyait
  `curl (7)`/`000` ; la sonde suivante a répondu 200. La disponibilité
  a donc été observée **après** les démarrages, sans attribuer la cause
  de cette transition à un composant particulier.

**Correctif code sur PR #289 :** `diagnose-defectdojo-deploying.py`
requiert désormais initializer `exited(0)`, quatre dépendants `running`,
HTTP accepté, et `app_state=RUNNING` avant de considérer le **transport**
prêt ; `admin_login=NOT_VERIFIED` demeure explicite.
Les tests ciblés sont versionnés ; **exécution locale au HEAD à confirmer**.
Critère de clôture : `stack_transport_state=READY_FOR_AUTH_CHECK`,
login Web validé, mot de passe effectif cohérent avec
`.env.secrets`/Vaultwarden, puis stabilité après cycle TrueNAS contrôlé.

### Inventaire RUNNING (capture 18:49:37 UTC)

- `resources-20261027T184909Z.json` : **143** conteneurs RUNNING,
  **91 mappés** au catalogue, **52 non mappés**, `inventory_complete=true`.
- `services_count=151` ; GPU `unavailable` sur TrueNAS, pas 0 MiB.
- Rapport privé local sous `/mnt/cpool/var/nabla/service-resources/`.
  **Ne pas committer le JSON** ; ne pas présenter les 151 entités
  comme autant de services RUNNING.
- Cette capture précède le démarrage manuel des quatre dépendants
  DefectDojo : **refaire l'inventaire après stabilisation**, sans
  soustraire mécaniquement les comptes des deux captures.

### Mémoire et services arrêtés

Avant le redémarrage ciblé, `free -h` indique environ **61 Gio**
de RAM totale, **7,3 Gio disponibles** et aucun swap configuré.
L'opérateur indique avoir arrêté **Netdata et Graylog** puis observé
une stabilisation de la mémoire. Il n'existe pas de preuve causale de
leur contribution individuelle aux pics passés.
Pour établir la tendance sans réactiver ces services :

```bash
sudo python3 scripts/truenas/diagnose-truenas-pressure.py \
  --check --observe-seconds 20 --skip-docker
```

Évaluer PSI mémoire/I/O, variation de `MemAvailable`,
`oom_kill` et direct reclaim. Ne pas modifier l'ARC ZFS,
réactiver Netdata/Graylog ni imposer de limite mémoire sur cette seule
observation.

### H-05 Prometheus et H-06 Akvorado (18:47:38 UTC)

- `diagnose-fastapi-prometheus-runtime.py --check` :
  Prometheus `running`, `/-/ready=200`, API targets `200`,
  clé FastAPI présente et montage secret présent/lisible.
  `scrape_accepted=false` dans ce préflight signifie
  **non vérifié par ce script**, pas échec authentifié.
- Relevé de **huit jobs nommés** : **3 scrape_up**
  (`docling`, `fastapi_sample`, `pfsense_exporter`) ;
  **5 scrape_down** : `haproxy`, `opensearch`,
  `opensearch-security`, `postgres_exporter` = `tcp_refused` ;
  `litellm_hermes` = `http_401`.
  Aucun statut global du reste du parc Prometheus ne peut être
  inféré de ces huit jobs.
- Akvorado sur 20 s : **6 nouveaux flux**,
  `metadata_missing +6`, `metadata_provider_errors +12`,
  `clickhouse_batches +0`, `kafka_messages +1` ;
  `akvorado_sql_rows=NOT_VERIFIED`.
  L'ingestion ClickHouse n'est **pas acceptée**.
- Ordre de diagnostic : classer la disponibilité réelle des quatre
  exporters TCP, corriger séparément l'auth du job `litellm_hermes`,
  puis vérifier les métadonnées d'interface Akvorado et démontrer
  les nouveaux inserts ClickHouse. **Pas de redéploiement général.**

### Vaultwarden / sources de vérité : encore à réconcilier

- `code`, `openrag` : `VAULT_ITEM_MISSING` selon **le cache
  local de la CLI Bitwarden**, pas une preuve d'absence côté serveur.
- `defectdojo` : cinq secrets applicatifs `MATCH`,
  `DD_ADMIN_USER=DRIFT`, `DD_ADMIN_PASSWORD=UNVERIFIED`
  (`VAULT_FIELD_MISSING_OR_EMPTY`) dans le cache CLI.
- Après le changement interactif Django, **la parité avec le runtime
  `.env.secrets` n'est pas connue**. Le mot de passe Django n'est pas
  relu depuis l'environnement au login.
- En session privée et déverrouillée (sans afficher de secret) :

```bash
bw sync
sudo python3 scripts/truenas/reconcile-defectdojo-admin-password.py --check
VENV_PYTHON="$HOME/.cache/nabla-compose/dev-venv/bin/python"
for app in code openrag defectdojo; do
  "$VENV_PYTHON" scripts/secrets/compare_vaultwarden_runtime_readonly.py \
    --check --app "$app"
done
```

Un état `PASSWORD_MISMATCH` impose de choisir **une seule valeur**
entre mot de passe Django nouvellement établi et secret runtime,
puis de réconcilier Vaultwarden. Ne pas faire un `--apply`
automatique qui écraserait le mot de passe fraîchement choisi.
Pour `code`/`openrag` toujours manquants après `bw sync`,
inspecter le dossier et le nom d'item déclarés dans
`config/secrets/manifest.json` avant toute création/duplication.

## Statut de collecte du catalogue

Le référentiel Backstage v2 versionné comporte **154 entités**, dont
**151 Component/Resource** et **141 mappings Compose**. Ces objets sont
*déclaratifs* ; ils ne constituent pas des mesures runtime.

Le collecteur `scripts/truenas/collect-service-resource-evidence.py`
produit désormais un JSON privé `nabla-service-resources/v1`, enrichi
des métriques CPU, RAM, mémoire GPU lorsqu'attribuable, couche écrivable
Docker et datasets ZFS. Il inspecte **Docker ps RUNNING uniquement**.
La clé `coverage` compte les conteneurs détectés, associés ou non
au catalogue et indique si l'inventaire était borné. La liste
`unmapped_running_containers` donne les noms et mesures disponibles
des conteneurs sans correspondance certaine. Aucun conteneur
introuvable n'est qualifié de `DOWN` ; l'absence n'est pas une valeur 0.

**Réception opérateur du 27 octobre (capture du 26 octobre 23:37 UTC)** :
`resources-20261026T233659Z.json` créé dans
`/mnt/cpool/var/nabla/service-resources` ; Docker **144 RUNNING**,
**92 mappés**, **52 non mappés**, `inventory_complete=true`,
**151 entités de service** dans le rapport, GPU indisponible sur
TrueNAS. Cela **prouve la collecte de l'inventaire runtime**, pas
que chaque mesure CPU/RAM/ZFS a été reçue pour chacun des 144
conteneurs. L'agent GitHub ne peut pas lire ce JSON local.

Pour les 52 conteneurs non mappés, la prochaine version du relevé
inclut `compose_project`, `compose_service` et
`mapping_issue` (identités contrôlées et expurgées),
afin de corriger les mappings exacts au lieu d'inférer un service
depuis son nom. Le rapport existant contient au minimum les noms
et consommations CPU/RAM disponibles. Il ne faut ni écrire
des chiffres imaginaires dans
`catalog/generated/entities.json` ni commiter un relevé périmé ou
privé dans Git. L'opérateur générera un instantané `0600`
pour import dans les cartes OWNER de nabla-site-alban PR #262.

```bash
cd /mnt/cpool/compose/nabla-compose
sudo install -d -o root -g root -m 0700 /mnt/cpool/var/nabla/service-resources
sudo python3 scripts/truenas/collect-service-resource-evidence.py \
  --check --host truenas \
  --output "/mnt/cpool/var/nabla/service-resources/resources-$(date -u +%Y%m%dT%H%M%SZ).json"
```

Pour comparer une VM/hôte GPU différent, exécuter le collecteur
sur cet hôte : l'absence de NVIDIA sur TrueNAS ne signifie pas
`0 MiB GPU`. Le stockage ZFS partagé est présenté comme
un dataset partagé et jamais comme une consommation exclusive.

## P0 — DefectDojo DEPLOYING et deux URLs indisponibles

**Preuve récente opérateur :** Custom App `defectdojo` en
`DEPLOYING`; `http://172.17.0.24:31085/` **et**
`https://defectdojo.int.albandrieu.com/` inaccessibles.

Le DNS privé avait été validé précédemment, mais ne prouve
aucune disponibilité actuelle du port. Le Compose impose
`defectdojo-uwsgi depends_on defectdojo-initializer:
service_completed_successfully`. Si l'initializer reste
en cours d'exécution ou sort avec erreur, le backend Django,
puis le frontend Nginx, peuvent rester absents.
La pression mémoire/OOM connue est un autre risque :
ne pas la masquer par des redeploys répétitifs.

```bash
cd /mnt/cpool/compose/nabla-compose
sudo python3 scripts/truenas/diagnose-defectdojo-deploying.py --check
sudo python3 scripts/truenas/diagnose-defectdojo-deploying.py \
  --check --include-log-classes
sudo bash scripts/truenas/preflight-defectdojo.sh
```

Le premier contrôle lit uniquement `midclt app.query`,
l'état/exit-code/OOM/health des cinq conteneurs attendus,
et l'état HTTP local. Le second examine une fenêtre de logs
bornée **sans afficher les logs**, et retourne seulement des
classes telles que `database_connection`,
`migration_or_initializer`, `filesystem_permission`
ou `memory_kill`.

**Décision selon la preuve :**
- `initializer_running` : attendre/diagnostiquer cette étape,
  sans toucher à Traefik ou au compte admin.
- `initializer_failed` : vérifier connexion PostgreSQL,
  migrations et permissions ; ne pas `DROP` la base.
- `OOMKilled=true` : stabiliser RAM, JVM, Docker et VM.
- initializer `exited(0)` puis uWSGI absent : regarder la
  dépendance Compose et les conteneurs.
- uWSGI + Nginx `running` mais HTTP absent : seulement
  alors examiner le bind :31085, les réseaux et Traefik.
- `DJANGO_UNAVAILABLE` sur le helper admin est attendu si
  uWSGI n'est pas prêt ; ne pas tenter une rotation du mot de passe
  avant le retour du backend.

## DefectDojo — analyse des logs initializer reçus

La capture d'initializer fournie le 27 octobre montre :

- 21:04 CET : `172.17.0.24:5432` accessible ;
- 21:07 CET : test de base PostgreSQL réussi ;
- 22:25 CET : triggers d'audit `pghistory` activés et
  migrations Django indiquées comme déjà appliquées ;
- `Admin user already exists; skipping first-boot setup` ;
- dernière ligne fournie :
  `Initializing non-standard permissions`.

**Ni code de sortie 0 ni erreur explicite** ne figurent dans
cette capture. Le délai important ne prouve pas un blocage
permanent : vérifier l'état Docker actuel de
`defectdojo-initializer` et, si toujours actif, la présence
d'une attente PostgreSQL. **Aucun DROP DATABASE** ni
rotation des mots de passe n'est justifié par ces logs.

```bash
sudo python3 scripts/truenas/diagnose-defectdojo-deploying.py \
  --check --include-log-classes
sudo python3 scripts/truenas/diagnose-defectdojo-postgres-waits.py --check
```

Le diagnostic SQL ne restitue que des catégories
`state/wait_event_type/wait_event`, le nombre de sessions et
d'attentes et leur durée. Il ne divulgue aucune requête SQL
ni identifiant. En cas de `LOCK_WAIT_OBSERVED`, examiner
la session bloquante **avant** un redémarrage de DefectDojo.

## Vaultwarden — preuves distinctes du déploiement

`config/secrets/manifest.json` définit les objets
`nabla/prod/code`, `nabla/prod/openrag`,
`nabla/prod/defectdojo`. Une édition manuelle d'env runtime
n'implique aucune mise à jour du coffre.

Depuis une session **non-root** avec `BW_SESSION` déjà
déverrouillée, et avec un `sudo -n cat` autorisé pour lire
le fichier runtime root-only :

```bash
VENV_PYTHON="$HOME/.cache/nabla-compose/dev-venv/bin/python"
for app in code openrag defectdojo; do
  "$VENV_PYTHON" scripts/secrets/compare_vaultwarden_runtime_readonly.py \
    --check --app "$app"
done
```

Le script ne divulgue aucun secret ; il compare précisément
chaque champ de manifest avec les valeurs `.env.secrets`
avec `hmac.compare_digest` et retourne `MATCH`, `DRIFT`
ou `UNVERIFIED`. Il **ne synchronise pas** Vaultwarden :
c'est la **cache de la CLI `bw`**, pas une preuve temps réel du
serveur. Aucun `bw edit`, rotation, installation ni
`materialize_runtime --install` n'est exécuté. Un coffre
verrouillé ou `sudo -n` indisponible produit `UNVERIFIED`.

### Résultat Vaultwarden du 27 octobre

L'inventaire CLI **avant mise à jour du classificateur** retournait :
`code=VAULT_ITEM_NOT_UNIQUE`,
`openrag=VAULT_ITEM_NOT_UNIQUE` ; cette catégorie
regroupait objets manquants **et** doublons. Le code distingue
maintenant `VAULT_ITEM_MISSING`,
`VAULT_ITEM_IN_OTHER_FOLDER` et
`VAULT_ITEM_DUPLICATED_*` via une seconde recherche sans
filtre de dossier, toujours sans afficher les objets.

Pour `defectdojo`, cinq secrets applicatifs sont `MATCH`.
`DD_ADMIN_USER=DRIFT` et
`DD_ADMIN_PASSWORD=UNVERIFIED` : le résultat ne révèle
aucun mot de passe. La nouvelle colonne
`unverified_reasons` distingue une valeur absente/vidée
dans l'objet Vaultwarden d'une clé runtime absente/vidée.
Le hash Django reste indépendant et le login n'est pas
opérationnel tant qu'uWSGI n'est pas prêt.

```bash
# Après la fin du build FastAPI en cours, sous l'utilisateur BW déverrouillé.
bw sync
VENV_PYTHON="$HOME/.cache/nabla-compose/dev-venv/bin/python"
for app in code openrag defectdojo; do
  "$VENV_PYTHON" scripts/secrets/compare_vaultwarden_runtime_readonly.py \
    --check --app "$app"
done
```

`bw sync` actualise la **cache locale CLI** ; il ne modifie
pas les objets distants. Ne jamais copier de secret dans un ticket
ou régénérer les clés Django/AES256 pendant l'initialisation.

## Prometheus / Akvorado — collecte H-05 / H-06

Depuis TrueNAS, la vérification readiness et le rapport
consolidé sont **indépendants** :

```bash
sudo python3 scripts/truenas/diagnose-fastapi-prometheus-runtime.py --check
bash scripts/truenas/observe-prometheus-akvorado-lan.sh --observe-seconds 20
```

Le dernier état rapporté par l'opérateur était
`Prometheus 21/28 targets UP` et une API ayant déjà refusé
des connexions ; cela ne prouve pas son état présent.
Pour Akvorado, la configuration Orchestrator montée correspond
au YAML Git, mais les derniers flux observés comportaient
des erreurs de métadonnées `ifIndex` et aucune insertion SQL
confirmée. Le rapport sépare :

- HTTP readiness/targets Prometheus ;
- Inlet/Outlet NetFlow, rejets actifs
  `metadata missing` et nouveaux lots ClickHouse ;
- preuve de lignes SQL `NOT_VERIFIED` (indépendante des compteurs).

En cas de rejets persistants :

```bash
sudo bash scripts/truenas/diagnose-akvorado-config.sh --check
python3 scripts/truenas/check-akvorado-metadata-config.py --check
python3 scripts/truenas/diagnose-akvorado-flow.py \
  --strict --fail-on-blocked --observe-seconds 30
```

Pas de flux artificiel pfSense, de changement de secrets ni de
redeploy généralisé sur la seule base d'un compteur historique.

## Acceptation

- Rapport privé et horodaté portant CPU/RAM/ZFS pour les
  workloads RUNNING, plus liste explicite des non-mappés.
- DefectDojo `RUNNING` et HTML HTTP local rétabli avant
  diagnostic de l'authentification admin et de Traefik.
- Vaultwarden parité contrôlée, dérives isolées et corrigées
  avec source de vérité confirmée.
- Prometheus targets actuelles visibles, Akvorado sans rejets
  actifs puis preuve de lignes SQL persistées.
- Les changements ont été commités sans lancer de quality gate,
  conformément au souhait opérateur ; runtime **NON VALIDÉ**.
