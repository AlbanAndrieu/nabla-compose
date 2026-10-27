# TrueNAS — reprise ciblée Scrutiny / Prometheus et triage app_lifecycle

**Incident : 26 octobre 2026 · source : `/var/log/app_lifecycle.log` fourni par l'opérateur.**

Les erreurs enregistrées dans le fichier **ne sont pas l'état actuel** des
applications. Les deux nouveaux échecs qui ont une cause déterministe sont :

- **Scrutiny**, 20:01:33 et 20:10:16 : le TrueNAS Custom App encore
  enregistré référence `/mnt/cpool/scrutiny/.env.secrets`, absent.
  Pourtant `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets` existe
  (319 octets, `root:root` et mode `0600`).
- **Prometheus**, 20:01:24 : le bind Compose obligatoire pointe vers
  `/mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key`,
  encore absent. Une telle erreur empêche la création du conteneur.
  Le diagnostic des targets peut alors renvoyer `URLError`
  sans qu'aucune cible ne soit réellement évaluée.

## 1. Vérifier les contrats (lecture seule)

```bash
cd /mnt/cpool/compose/nabla-compose

sudo bash scripts/truenas/deploy-scrutiny.sh --check
sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py --check
sudo python3 scripts/truenas/triage-app-lifecycle-log.py --check --since 2026-10-20
```

Le script de triage lit au maximum les derniers 8 Mio du journal.
Il n'imprime jamais les corps de messages ou les variables de secrets.
Il affiche une catégorie par application et le dernier événement,
sans prétendre que le problème est encore actif.

## 2. Corriger Scrutiny (sans changer le jeton)

Le Compose du dépôt utilise **déjà** le fichier canonique.
La définition du Custom App stockée côté TrueNAS est obsolète :
un simple `app.redeploy scrutiny` peut reproduire le problème tant
que sa configuration n'a pas été réécrite.

```bash
cd /mnt/cpool/compose/nabla-compose
sudo env SCRUTINY_CUTOVER_APPROVED=1 \
  bash scripts/truenas/deploy-scrutiny.sh --apply
```

Cette procédure est **mutante** : elle valide InfluxDB et les
SMART devices, rend un Compose avec les devices nécessaires, puis
met à jour le Custom App `scrutiny` et démarre l'App si elle était
STOPPED. Elle conserve le contenu du fichier canonique ; ne pas
utiliser `SCRUTINY_TOKEN_ROTATE=1` ni
`SCRUTINY_RESET_SQLITE=1` pour cet incident de chemin.

Après lancement :

```bash
sudo bash scripts/truenas/diagnose-scrutiny.sh --check
curl --fail --silent --show-error \
  http://172.17.0.24:31054/api/health
```

Si le conteneur devient `unhealthy` **après** la correction du
chemin, alors seulement diagnostiquer l'accès InfluxDB, les droits
sur `/mnt/cpool/scrutiny/config` et la version du token
organisation-scopé `scope=v2`. Un fichier existant de 319 octets
ne prouve pas à lui seul l'authentification InfluxDB.

## 3. Réparer Prometheus avec la clé existante

Le job `fastapi_sample` nécessite un Bearer token ; la configuration
refuse à dessein la création implicite d'un bind-mount vide.

```bash
sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py --check
```

Si la source `/mnt/cpool/secrets/runtime/sample/.env.secrets` est
validée, le `--apply` suivant installe le **même** jeton en
`root:568 0640` et crée, si nécessaire, uniquement le dossier
`/mnt/cpool/prometheus/secrets` en `root:568 0750`.

```bash
sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py \
  --apply --acknowledge I_APPROVE_FASTAPI_SCRAPE_CREDENTIAL_INSTALL
```

Aucune clé aléatoire n'est générée. Si le fichier source manque,
contient un doublon ou n'est pas conforme, le provisionneur bloque ;
ne pas fabriquer un jeton différent de celui chargé par FastAPI.

Vérifier à nouveau :

```bash
sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py --check
sudo midclt call -j app.redeploy prometheus
curl -fsS http://172.17.0.24:9090/-/ready
python3 scripts/prometheus/diagnose-failed-scrapes.py --check --scope remaining
```

`app.redeploy` n'est nécessaire qu'après la disponibilité du
fichier pour reprendre le conteneur. Un 401 de FastAPI
**après** ce changement doit être investigué comme divergence entre
jeton installé, runtime FastAPI et paramètres de scrape ; ne pas
exposer `/metrics` sans authentification.

## 4. Autres événements du journal

Les erreurs du **23 octobre** sur LiteLLM pointent un secret canonique
manquant à cette date ; leur correction exige un contrôle de
présence actuel, pas une création de clé à l'aveugle. L'échec Wazuh
du 3 octobre est un bind de certificats absents ; utiliser le
bootstrap Wazuh dédié après vérification de la persistance actuelle.

Les échecs `healthcheck` de septembre/début octobre (OpenRAG,
Sentry, Karakeep, Langfuse, Paperless, OpenArchiver, Immich, Tracearr)
et les anciens échecs Docker `did not receive an exit event` sont
**historiques**. Pour identifier les problèmes encore actifs :

```bash
sudo midclt call app.query | jq -r '.[] | [.id, .state] | @tsv' \
  | grep -E 'scrutiny|prometheus|litellm|openrag|wazuh|sentry|akvorado' || true

sudo bash scripts/truenas/audit-app-lifecycle.sh
```

Ne pas redéployer toute la flotte d'après le journal. Procéder
par cause racine, à partir de l'état actuel.

## 5. Akvorado et preuve Prometheus recueillies

- Premier relevé 20 s : Inlet métriques présent, deltas Outlet nuls.
  **`UNVERIFIED`**, pas `PASS`.
- Relevé ultérieur 30 s : **2 nouveaux flux / 2 erreurs
  `metadata missing` / 0 lot ClickHouse**, Kafka +1. C'est
  une preuve d'un rejet actif de métadonnées sur les nouveaux flux.
- Prochain contrôle : `bash scripts/truenas/diagnose-akvorado-config.sh --check`.
  Le mapping déclaré `ifIndex=11` ne prouve ni la configuration
  effectivement **chargée en mémoire** par l'Outlet, ni que tous les
  nouveaux flux utilisent cet index. Après réconciliation ciblée
  du Custom App Akvorado, observer les deltas et vérifier les lignes
  SQL dans ClickHouse. Ne pas généraliser `Track by Default` sur
  le Netgate 1100.
