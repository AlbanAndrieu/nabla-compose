# Observabilité TrueNAS — diagnostic et reprise contrôlée

**Fiche spécialisée (25 octobre 2026).** Le runbook principal reste [l'acceptation runtime](homelab-runtime-acceptance.md).
Incident du 24 octobre :
[reprise observabilité TrueNAS](../incidents/2026-10-24-truenas-observability-recovery.md).
Les procédures mutantes sont **manuelles**, jamais exécutées par un
diagnostic. Le détail DNS appartient au
[runbook pfSense](../pfsense-diagnose-recover.md).

## État de référence prouvé

| Composant | Dernière observation fournie | Interprétation |
| --- | --- | --- |
| Prometheus | Docker running, HTTP `/-/ready` 200 ; 15/15 règles lisibles | Service rétabli |
| Pyroscope | Docker running, HTTP `/metrics` 200 | Réinitialisation terminée, conserver le backup |
| Akvorado inlet/outlet | Deux scrapes 1/1, métriques présentes | Scrapes UP ; flux SQL non attestés |
| Gatus, Redis exporter, CrowdSec, pfSense exporter | Scrapes UP | Vérifier fraîcheur à chaque nouvel incident |
| FastAPI staging `:8091/metrics` | HTTP 401 | Authentification manquante, **pas** une panne HTTP générale |
| PostgreSQL exporter `:9187` | TCP refusé, conteneur et secret absents | Exporter à provisionner, pas PostgreSQL lui-même |
| FastAPI Cloud `/api/health-board` | HTTP 403 depuis le vérificateur | Snapshot non accessible ; Akvorado cloud inconnu |

Ces constats sont datés. Ne pas les présenter comme états live actuels.

## Pack de diagnostic LAN — rapport unique Prometheus + Akvorado

`scripts/truenas/collect-observability-evidence.py` regroupe les jobs
Prometheus (`--scope remaining`, `baseline` ou `all`) et compare deux
relevés Akvorado sur une fenêtre bornée, dans un seul JSON expurgé.
Il n'exécute **aucune réparation ni redémarrage** et n'utilise que
Python standard (ni `bw`, ni `python-dotenv`, ni certificat Cloudflare).

Depuis le shell TrueNAS (checkout canonique), rapport privé sous
`/mnt/cpool/var/nabla/observability` :

```bash
cd /mnt/cpool/compose/nabla-compose
just observability-evidence-lan
```

Depuis la workstation LAN, sans `sudo` ni sauvegarde, pour distinguer
un défaut de chemin LAN d'un problème serveur :

```bash
cd ~/w/nabla-compose
python3 scripts/truenas/collect-observability-evidence.py --check \
  --scope all --observe-seconds 20
```

Contrat de test hors LAN : `just observability-evidence-test`.

Le collecteur utilise les URLs fixes `172.17.0.24:9090`, `:31057`,
`:31058`, sans proxy ni redirection, un timeout de 5 s, au plus 1 Mio de
JSON Prometheus et 2 Mio par endpoint Akvorado, une observation de
1 à 60 s. Avec `--report-dir`, le rapport est écrit en mode `0600` dans
un dossier `0700` appartenant à l'opérateur ; un mode non conforme ou un
lien symbolique fait échouer la sauvegarde sans modifier le dossier.
Le JSON ne contient ni `lastError` brut, ni labels, ni URL de scrape,
ni credential, ni adresse de flux :

- **Prometheus** : par job `scrape_up`, `scrape_down`, `scrape_partial`,
  `scrape_unverified` ou `no_active_target`, nombre de cibles et domaines
  `auth/http/tcp/dns/tls/timeout/network/unverified` ;
- **Akvorado Inlet** : présence d'au moins un compteur reconnu ;
- **Akvorado Outlet** : deltas de flux reçus, erreurs `metadata missing`,
  Kafka et lots ClickHouse ; un ancien compteur non nul ne prouve pas
  qu'une erreur persiste ;
- **SQL** : toujours `NOT_VERIFIED`.

| Code | Verdict | Conduite |
| --- | --- | --- |
| `0` | `PASS` | Réservé à une preuve complète (non atteignable : les lignes SQL ne sont pas validées) |
| `1` | `FAIL` | Au moins un scrape explicitement DOWN/partiel ou un rejet actif de métadonnées |
| `2` | `UNVERIFIED` | Observations absentes, incomplètes ou non concluantes ; ne pas déclarer un service DOWN |

Sans erreur avérée, le code habituel est donc `2`. Le code de sortie
peut être non nul **tout en ayant créé le rapport** : le lire avant
de conclure. Un FAIL de scrape indique un défaut de collecte, pas
forcément une application DOWN. Akvorado
`NEW_INSERT_BATCHES_ROWS_UNVERIFIED` prouve uniquement une variation
des compteurs de lots ; le SQL ClickHouse doit être confirmé
séparément avec un compte lecture seule. Conserver les JSON expurgés
**hors Git** avec leurs horodatages ; ne jamais transmettre de secrets
ni de sorties `docker inspect` intégrales, et ne pas appeler pfSense
ni forcer de mises à jour DNSBL/Snort.

**Détails ciblés facultatifs (lecture seule) :**

```bash
# prometheus.status=FAIL
python3 scripts/prometheus/diagnose-failed-scrapes.py --check --scope remaining
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
# akvorado.observation=BLOCKED_METADATA_MISSING, PARTIAL_METADATA_REJECTIONS
# ou METADATA_REJECTIONS_INSERTS_UNVERIFIED
sudo bash scripts/truenas/diagnose-akvorado-config.sh --check
python3 scripts/truenas/check-akvorado-metadata-config.py --check
python3 scripts/truenas/diagnose-akvorado-flow.py --strict --fail-on-blocked --observe-seconds 30
# progression des lots uniquement
python3 scripts/truenas/diagnose-akvorado-flow.py --strict --require-inserts --observe-seconds 30
```

`check-akvorado-metadata-config.py` nécessite `PyYAML` et valide
uniquement la configuration déclarative : le mapping de l'exporter
pfSense `172.17.0.1/32`, `ifIndex=11`. Un hash de configuration
identique côté Orchestrator **n'atteste pas** que l'Outlet utilise ce
mapping en mémoire ; classer les rejets selon l'exporter réellement
reçu, les ifIndex et le chargement runtime. Ne pas élargir la collecte
pflow sur le Netgate 1100 pour déclencher artificiellement un flux.
`--require-inserts` confirme au mieux une **activité de lots**, pas
des insertions SQL datées. Les commandes réseau supposent l'accès
LAN ; ne pas interpréter un timeout externe comme un incident des
Apps. Pour une réception SQL, utiliser un compte ClickHouse
**read-only** limité à `akvorado`, découvrir le schéma effectif et
comparer de nouvelles lignes par une requête `SELECT` bornée, sans
créer ni effacer de données.

## Diagnostic unique, lecture seule

Sur **TrueNAS**, dans le checkout Compose :

```bash
python3 scripts/prometheus/diagnose-failed-scrapes.py --check
sudo bash scripts/truenas/diagnose-observability-post-repair.sh --check
sudo bash scripts/truenas/diagnose-postgres-exporter.sh
```

Lancer le point d'entrée consolidé décrit dans
[commandes opérateur spécialisées](2026-10-25-homelab-operator-diagnostics.md)
pour agréger la classification des états. Ne pas afficher de DSN, clés,
logs bruts, headers Authorization ni chemins privés. Éviter les
scrapes manuels supplémentaires vers pfSense.

### H-05 — erreurs de scrape et statut non vérifié (code du 26 octobre)

Le classificateur `scripts/prometheus/diagnose-failed-scrapes.py`
ne transforme plus `health=unknown`, vide ou inattendu en `DOWN`.
Il publie `scrape_unverified` et `targets_unverified`, ainsi que
des domaines redigés `auth`, `http`, `tcp`, `dns`, `tls`,
`timeout`, `network` ou `unverified`. Le code HTTP 401/403
signifie **problème d'autorisation du scrape**, pas arrêt du
service applicatif. `no_active_target` signifie un job absent
des cibles actives, pas une cible DOWN.

Le diagnostic reste fixé à l'API Prometheus du LAN ; aucun
`lastError`, label, chemin privé ou token n'est imprimé.
Ces catégories sont des **preuves de collecte**, pas de
disponibilité métier ni une autorisation de modifier les secrets.
Le relevé historique `21/28 UP` n'est pas actualisé faute de LAN.

### H-06 — compteurs Akvorado invalides

`scripts/truenas/diagnose-akvorado-flow.py` refuse désormais
les compteurs négatifs ou non finis (`1e999` par exemple) comme
preuve de lots ClickHouse. Les fenêtres concernées sont classées
`COUNTER_INVALID_INCONCLUSIVE` ; le contrôle
`--fail-on-blocked` échoue fermement et la procédure
`--require-inserts` ne peut pas conclure à une insertion sur
ces entrées invalides. Les métadonnées NetFlow, les ifIndex
réellement reçus et la présence de lignes SQL récentes restent
**NOT_VERIFIED**. Les tests synthétiques n'impliquent pas
un redémarrage Akvorado, Kafka ou ClickHouse.

### Prometheus / Pyroscope

Si Prometheus redémarre :
`sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check`
permet de compter les règles illisibles. **Ne pas** réexécuter `--apply`
si la sortie est `unreadable=0`. Un `restart_count` ancien ou un log
d'échec historique n'est pas un incident actif.

Un état `app.query RUNNING` ne garantit pas que le processus écoute
ni que Docker publie réellement `:9090`. Si `/-/ready` renvoie
`connection refused`, contrôler **sans redeploy ni secret** :

```bash
sudo docker inspect prometheus --format \
  'state={{.State.Status}} restarting={{.State.Restarting}} restarts={{.RestartCount}} exit={{.State.ExitCode}}'
sudo ss -lnt '( sport = :9090 )'
curl --noproxy '*' -sS --connect-timeout 2 --max-time 5 \
  http://127.0.0.1:9090/-/ready
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
```

Si le conteneur redémarre, lire les catégories `permission denied`,
`rules`, `TSDB/WAL`, `parse error` du diagnostic. Un démarrage refusé
sur un bind source manquant (`app_lifecycle.log`) n'est pas un échec
d'autorisation de scrape. Ne pas supprimer le TSDB ni élargir les
permissions des secrets pour rendre la sonde verte.

Pyroscope possède une sauvegarde de l'ancien état :
`/mnt/cpool/pyroscope/data/.metastore-backup-20261024T210505Z`.
Ne pas exécuter un second reset automatique. Vérifier `running` et
HTTP 200 avant toute décision de suppression manuelle de la sauvegarde.
Aucune suppression TSDB Prometheus, WAL ou backup Pyroscope n'est
justifiée par les dernières preuves.

### Exporter PostgreSQL

Le [Compose](../../apps/postgres-exporter/compose.yml) utilise un secret
`/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets`
avec `env_file.format: raw`, `required: true` et listener
`172.17.0.24:9187`.

- **Avant le déploiement** : vérifier Docker Compose ≥ 2.30, créer un
  rôle `pg_monitor` non superuser et un secret `DATA_SOURCE_NAME`
  dédié via le flux Vaultwarden → `install-runtime-secret.sh`.
- **Après déploiement autorisé** : vérifier HTTP `/metrics` et
  `up{job="postgres_exporter"}=1` **et** `pg_up=1`.
- Ne jamais réutiliser les secrets PostgreSQL applicatifs ou
  imprimer le DSN. Absence de secret = blocage du déploiement.

### FastAPI /metrics et cloud

`/metrics` de FastAPI TrueNAS exige la clé dédiée
`METRICS_SCRAPE_KEY` ([FastAPI #376](https://github.com/AlbanAndrieu/fastapi-sample/pull/376)) :
un HTTP 401 sans jeton est attendu. Le job `fastapi_sample` envoie
`authorization.type: Bearer` avec `authorization.credentials_file`.
Ne pas rendre `/metrics` public.

| Usage | Chemin TrueNAS | Protection |
| --- | --- | --- |
| Source FastAPI | `/mnt/cpool/secrets/runtime/sample/.env.secrets` | root, `0600`/`0640`, jamais exporté |
| Secret Prometheus | `/mnt/cpool/prometheus/secrets/fastapi-sample-metrics.key` | `root:568`, `0640` (dossier `root:568 0750`) |
| Vue conteneur Prometheus | `/run/secrets/fastapi-sample-metrics.key` | Bind read-only, UID/GID `568:568`, jamais créé implicitement |

`scripts/truenas/reconcile-fastapi-metrics-credential.py` copie
**une seule** ligne `METRICS_SCRAPE_KEY=<64 caractères hexadécimaux>`
(256 bits, `secrets.token_hex(32)`), éventuellement entre guillemets,
et aucune autre variable. Il refuse doublons, symlinks, hardlinks,
source non root ou trop permissive et valeur non conforme.
`--check` est toujours **read-only** et renvoie un `state` et un
`next_check` à vocabulaire fermé :

| État | Contrôle sans secret |
| --- | --- |
| `source_file_missing` | Fichier invisible depuis TrueNAS : vérifier le chemin, le montage et l'hôte d'exécution |
| `source_owner_not_root` / `source_permissions_insecure` | Contrôler propriétaire et droits (ni monde, ni écriture groupe) |
| `source_symlink_refused` | Vérifier la chaîne de matérialisation |
| `source_key_missing` / `source_key_duplicated` | Une seule déclaration exacte `METRICS_SCRAPE_KEY`, vérifiée dans l'éditeur privé |
| `source_key_format_invalid` | Valeur non conforme : 64 caractères hexadécimaux |
| `source_read_unavailable` | Lecture sécurisée impossible |
| `credential_not_installed` / `destination_directory_unavailable` | Source validée : installer le secret Prometheus avec approbation |
| `credential_ready` | Fichiers corrects ; **ne prouve ni** le jeton chargé par FastAPI, ni le scrape |

Exécuter sur l'hôte TrueNAS (SSH `albandrieu@172.17.0.24`, port
`9922`), jamais sur le système de fichiers de la workstation. Ne pas
inférer présence de clé, panne ZFS ou erreur de droits à partir de
relevés non simultanés : regrouper `hostname`, `sudo stat -c
'type=%F uid=%u gid=%g mode=%a links=%h size=%s'` sur la source et
`--check` dans la même session, sans afficher le contenu.

Provisionnement ou rotation, une opération par étape :

1. `sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py --check`
   doit être sorti des états `source_*`. Sinon, ne pas utiliser
   `--apply`, ne pas recréer FastAPI ni Prometheus.
2. Après approbation explicite :

   ```bash
   sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py \
     --apply --acknowledge I_APPROVE_FASTAPI_SCRAPE_CREDENTIAL_INSTALL
   ```

   Crée au besoin le seul dossier `/mnt/cpool/prometheus/secrets`
   (sans parents ni lien symbolique), puis installe la clé. Relancer
   `--check` : `credential_ready`. Ne pas réexécuter `--apply` ni
   renouveler la clé ensuite.
3. Vérifier que l'environnement **actif** de FastAPI contient une
   variable non vide, sans l'afficher :

   ```bash
   sudo docker exec fastapi-sample python3 -c \
     'import os; print("METRICS_RUNTIME_PRESENT=" + str(bool(os.environ.get("METRICS_SCRAPE_KEY"))).lower())'
   ```

   `true` prouve la présence, pas l'égalité. Un conteneur créé avant la
   mise à jour de `.env.secrets` doit être recréé par le mécanisme
   TrueNAS, sans redémarrage automatique.
4. `promtool check config apps/prometheus/prometheus.yml` (hôte outillé
   ou image Prometheus installée).
5. `app.redeploy prometheus` : un reload de `prometheus.yml` ne peut
   pas ajouter le bind. Le recréer seulement si le montage est absent
   du conteneur **effectivement lancé**.
6. Acceptation : `python3 scripts/prometheus/diagnose-failed-scrapes.py
   --check --scope remaining` donne `fastapi_sample: state=scrape_up
   targets_up=1`.

Diagnostic borné sous pression mémoire, sur TrueNAS :
`sudo python3 scripts/truenas/diagnose-fastapi-stack.py --check --scope prometheus`
(métadonnées Docker, codes et compteurs seulement, sans labels,
`lastError` ni environnement). Une readiness Prometheus HTTP 200 avec
une API `/api/v1/targets` en timeout oriente vers la pression
mémoire/CPU/TSDB, pas vers les clés. Un `http_401` après montage signifie un jeton refusé
(FastAPI démarré avant la mise à jour de `.env.secrets`), pas un
fichier absent.

Règles de sécurité et de retour arrière :

- **aucun** secret dans GitHub, journaux, arguments, commentaires de
  PR ou variables `NEXT_PUBLIC_*` ; jamais `cat`, `grep` sur la
  valeur, `set -x` ni capture de terminal ;
- ne pas réutiliser `DIAGNOSTICS_ACCESS_KEY` ni affaiblir le contrôle
  d'accès de `/metrics` ; pas de copie vers FastAPI Cloud ou
  `nabla-site-alban` ;
- si le jeton est refusé, vérifier la correspondance coffre/montages
  sans afficher les valeurs ; revenir à la configuration précédente
  uniquement selon le runbook de déploiement, en préservant le secret
  privé.

Un HTTP 403 sur le snapshot FastAPI Cloud est un problème d'autorisation
distinct. Consulter le
[runbook FastAPI 403](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/runbooks/fastapi-cloud-owner-access-403.md).
Ne pas désactiver Cloudflare Access ou les contrôles de source IP.

## DNS-over-TLS : projet, non appliqué

pfSense/Unbound `172.17.0.1` reste l'autorité locale de
`int.albandrieu.com`. Le plan est de chiffrer progressivement les
requêtes **sortantes** d'Unbound vers deux résolveurs Quad9 via
TCP/853 avec validation de certificat. Le DNS client → pfSense
est distinct et peut rester UDP/TCP 53 sur le LAN.
Aucun DoT ne doit être considéré déployé sans preuve réseau côté pfSense.
Sauvegarder avant modification et ne pas surcharger le Netgate 1100.

## Retrait d'incident

Les tests locaux valident le code, pas les services déployés.
Un état docker `running` seul ne prouve ni la disponibilité HTTP,
ni la fonction métier. Documenter séparément : source d'observation,
horodatage, URL/path testé, résultat et décision de rollback.

Conditions de clôture :

- **Prometheus** : classifier chaque cible d'après les dernières
  preuves, corriger seulement l'exporter ou l'autorisation concernée,
  puis observer le scrape à nouveau.
- **Akvorado** : hausse des flux récents sans nouveaux rejets de
  métadonnées, lots confirmés puis **lignes SQL récentes** vues avec
  une identité de consultation. Sans flux durant la fenêtre, l'état
  reste `UNVERIFIED`.
- Ne jamais présenter un `docker running`, un HTTP 200 de métriques,
  un PASS de code ou un lot ClickHouse comme une disponibilité métier
  complète.
