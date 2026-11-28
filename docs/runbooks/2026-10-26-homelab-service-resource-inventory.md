# Référence de ressources par service — RAM, GPU et stockage

**26 octobre 2026 · TrueNAS / workstation · catalogue Backstage v2**

## Observations de l'incident

Le premier relevé TrueNAS donnait environ **2 Gio de MemAvailable
sur 62 Gio**, sans swap, avec PSI `some avg300=23.35` et
`full avg300=19.65`. Le journal noyau entre 21:27 et 22:18
établit plusieurs **global_oom**, ayant tué des processus Java,
Python, Obsidian, mais aussi **deux processus QEMU**. Les VM
Talos/CSI doivent donc faire l'objet d'un contrôle de santé ciblé
avant de poursuivre les redémarrages de services.

`docker stats` à ce moment attribuait **~9,55 Gio à MongoDB**,
mais **~572 Mio à Netdata** et **~129 Mio à l'initializer
DefectDojo**. On ne peut donc pas attribuer les OOM à Netdata ou
DefectDojo sans preuves de tendance ou d'association cgroup.
Une mesure ultérieure montrait ~8,3 Gio disponibles et PSI 10 s
nul, mais ceci ne prouve pas l'absence de nouveaux OOM.

**Actions immédiates** : laisser arrêtés les services non indispensables,
ne pas redémarrer toutes les applications et VM, diagnostiquer les
victimes OOM du journal et surveiller MongoDB/JVM/VM avant toute
migration ou réinitialisation de base.

## Modèle et source de vérité

Les noms des services et leur identité viennent des
`catalog/generated/entities.json` et
`catalog/generated/identity-map.json`, via le label Docker
`com.albandrieu.nabla.entity-ref` ou la correspondance exacte
`apps/<project>/compose.yml#services/<service>`.
Un nom ressemblant à un service n'est **pas** une preuve suffisante.
Les conteneurs ambigus/non indexés restent non attribués.

Les observations sont volontairement distinctes du catalogue
déclaratif : elles sont **horodatées**, propres à un hôte et
**ne doivent pas être commitées dans Git**.

| Signal | Source ponctuelle | Limite |
| --- | --- | --- |
| RAM du conteneur | `docker stats --no-stream` | Échantillon de working set, pas le pic mémoire |
| GPU | `nvidia-smi`, PID → cgroup Docker | GPU sur workstation : relevé workstation obligatoire ; pas de valeur zéro inventée |
| Couche écrivable | `docker ps --size` | N'inclut pas les bind mounts et volumes |
| ZFS datasets | `zfs list -Hp` + `docker inspect .Mounts` | `used` inclut descendants/snapshots ; datasets partagés signalés, **jamais sommés** |
| Identité | label Backstage v2 ou Compose project+service exact | Pas de repli sur un simple nom similaire |
| Disponibilité | **pas** déterminée par les métriques | Absence = `unverified`, non `DOWN` |

C'est une **inspection ponctuelle existante**, pas un daemon de
surveillance supplémentaire : Prometheus/cAdvisor demeure la source
de l'historique CPU/RAM et des courbes sur TrueNAS. Le relevé
GPU NVIDIA par processus exige des droits sur le GPU de l'hôte.

## Collecte TrueNAS

Après intégration des fichiers du dépôt et si Docker répond
sans délai excessif :

```bash
cd /mnt/cpool/compose/nabla-compose

sudo install -d -o root -g root -m 0700 \
  /mnt/cpool/var/nabla/service-resources

sudo python3 scripts/truenas/collect-service-resource-evidence.py \
  --check --host truenas \
  --output "/mnt/cpool/var/nabla/service-resources/resources-$(date -u +%Y%m%dT%H%M%SZ).json"
```

La sortie console est un **résumé** ; le JSON privé complet
(mode `0600`) contient les champs :

- `schema=nabla-service-resources/v1`, `catalog_revision`,
  `observed_at_utc`, `source_host` ;
- `services[].entityRef`, `memory.working_set_bytes` ;
- `gpu.process_memory_bytes` (nullable) ;
- `storage.writable_layer_bytes`, `datasets[].name`,
  `used_bytes_including_children`, `shared_by_services` ;
- les états de disponibilité des métriques, jamais une valeur
  `0` lorsque la source n'a pas répondu.

La collecte utilise Docker Stats, Docker inspect des **montages
uniquement** (pas de `.Config.Env`), ZFS et `nvidia-smi`,
avec limites et délais par commande. Si TrueNAS est encore
en forte pression/OOM, remettre cette opération à plus tard :
la capture doit aider le diagnostic, pas l'aggraver.

## Ajustement des plafonds mémoire (28 novembre 2026)

Le relevé initial du collecteur était ponctuel. La sortie privée de
`--memory-peaks` fournie par l'opérateur le 28/11 (worktree #455,
`c7bad865`) permet de confronter les cibles aux pics cgroup.
**PICS OBSERVÉS / CODED / réception runtime NOT_RUN** : aucune
économie de RAM observée. Les plafonds Docker ne réservent pas la RAM.

| Service | Plafond observé avant application | Cible révisée | Pic maximal acceptable (Mio) |
| --- | ---: | ---: | ---: |
| Nexus | 5 Gio | 4608 Mio | 3072 |
| Sentry Web | 2304 Mio | 2304 Mio | 1536 |
| Sentry Taskworker | 1536 Mio | 1664 Mio | 1109 |
| Langfuse Web | 1792 Mio | 1664 Mio | 1109 |
| Langfuse Worker | 960 Mio | 832 Mio | 554 |
| LanguageTool | 1792 Mio | 1536 Mio | 1024 |
| Loki | 768 Mio | 640 Mio | 426 |
| Dependency-Track API | non plafonné | 4 Gio | 2730 |
| Dependency-Track frontend | non plafonné | 256 Mio | 170 |
| Traefik | 256 Mio | 448 Mio | 298 |
| MinIO | 448 Mio | 704 Mio | 469 |
| Pi-hole | non plafonné | 512 Mio | 341 |
| Dozzle | non plafonné | 256 Mio | 170 |
| n8n | 4 Gio (App native) | 2 Gio (Compose) | 1365 |

Les seuils appliquent le contrat historique `mem_limit >= memory.peak × 1,5`,
arrondi à la baisse pour le pic admissible. Les baisses initiales de Sentry
Web/Taskworker et Langfuse Web dans #455 ne respectaient pas cette règle :
cibles corrigées. Nexus et LanguageTool satisfont le seuil. Nexus et LanguageTool
gardent leurs heaps ; Nexus garde également 2 Gio de mémoire directe,
avec au moins 512 Mio pour le reste. Il s'agit d'un compromis Homelab
hors dimensionnement [Sonatype](https://help.sonatype.com/en/nexus-repository-memory-overview.html),
dont le heap minimal publié est supérieur au heap existant.
Dependency-Track 5.2 fixe aussi le heap à 2560 Mio via
[`EXTRA_JAVA_OPTIONS`](https://github.com/DependencyTrack/dependency-track/blob/5.2.0/apiserver/src/main/docker/Dockerfile)
et doit passer une synchronisation des vulnérabilités et une analyse SBOM
(voir les [besoins amont](https://docs.dependencytrack.org/getting-started/deploy-docker/)).

Avant toute mise en service, mesurer le pic depuis la création du cgroup
sur un cycle de charge représentatif (notamment tâches nocturnes,
ingestions Sentry/Langfuse, règles LanguageTool et cache froid Nexus) :

```bash
sudo env DIAGNOSTIC_FULL_OUTPUT=1 bash scripts/truenas/diagnose-performance.sh --memory-peaks
```

Cette collecte ne lance qu'un inventaire Docker borné puis lit les cgroups
v2. Elle n'effectue ni `docker stats`, ni scan disque, ni redémarrage.
Le pic et la mémoire courante incluent le cache ; `memory.max` est en
octets (ou `max`). Un cgroup indisponible donne `UNVERIFIED` et le code 2.
Un pic récent après redémarrage n'est pas représentatif : attendre un
cycle complet. Si un seuil est dépassé, si les données manquent, ou si
le cgroup a déjà atteint son plafond, conserver l'ancien réglage ou
revoir la cible. Ne pas réduire OpenSearch, Wazuh Indexer, NetBox ou
les autres services sans marge mesurée ; conserver aussi les plafonds
des tâches variables (Docling, ClickHouse, Ollama, etc.).

### Cgroup au plafond et Apps natives

Les pics de Traefik, MinIO et MongoDB atteignent le plafond (arrondi
au Mio supérieur). Ce n'est pas une preuve d'OOM : le pic est censuré
par la limite et peut inclure du cache. Traefik et MinIO ont des cibles
pilotes plus hautes, à déployer séparément **uniquement après** revue
des compteurs `memory.events` (max, oom, oom_kill), de MemAvailable,
PSI et du budget global. MongoDB reste à 1536 Mio : examiner les
événements et le cache WiredTiger avant d'augmenter sa limite
(antécédent de forte consommation). OpenSearch, LiteLLM, ntopng,
Wazuh Indexer, NetBox et Kafka sont aussi proches de leur plafond ;
ne pas augmenter tous les plafonds simultanément sur l'hôte 64 Go.
Si la pression hôte est forte, optimiser le workload d'abord.

Le plafond n8n versionné est une cible du Compose, pas une modification
de l'App native ou une migration des services associés. Vérifier la
provenance effective avant de réconcilier et exécuter des workflows
représentatifs. Les gros plafonds natifs (LocalAI, Immich, PostgreSQL)
et OpenClaw nécessitent une revue de leur propre configuration et des
charges représentatives (modèles, indexation, requêtes, tâches agents).
Ne pas réduire ces plafonds sur un relevé inactif. Scrutiny et son
collecteur ont des limites versionnées mais étaient non plafonnés dans
le relevé : réconcilier la dérive, pas ajouter une deuxième définition.
Ollama conserve 6 Gio : le pic observé justifie l'écart avec le courant.

Après approbation et réconciliation depuis les sources versionnées, un
seul App à la fois : vérifier la santé avant/après, les accès réels
APT/npm/PyPI/Maven pour Nexus, les ingestions et les analyses pour les
autres services. Surveiller la pression mémoire, les événements OOM,
les redémarrages et les pics pendant un cycle complet. En cas de
régression, rétablir le Compose précédent puis réconcilier l'App
concernée ; ne toucher ni aux datasets ni aux autres Apps.
Les limites effectives doivent correspondre aux sources avant de
déclarer `DEPLOYED`. Le rapport brut reste privé.

## GPU de la workstation

Si le GPU est sur `172.17.0.57`, collecter sur **cet hôte** :

```bash
cd ~/w/nabla-compose
python3 scripts/truenas/collect-service-resource-evidence.py \
  --check --host workstation
```

Le GPU non visible sur TrueNAS reste `unverified`, pas `0 Mio`.
Une tâche NVIDIA non attribuable sans ambiguïté à un cgroup
Docker reste également `unverified`. Les données GPU hôte
ne sont pas recopiées artificiellement sur des services TrueNAS.

## Affichage dans le site

La PR du site `feat/homelab-service-resource-snapshots-20261026`
permet, en mode OWNER seulement, d'importer le fichier de
ressources JSON **depuis le navigateur**. Il est stocké
localement, sans envoi au cloud ni accès public. Les cartes
affichent RAM / GPU / couche Docker / datasets ZFS partagés.
Au-delà de 30 minutes, le relevé est présenté comme
**historique**. Une révision différente du catalogue est signalée.

Un flux automatique devra passer par le collecteur LAN
autorisé et un endpoint OWNER authentifié. Aucune donnée
de capacité brute ne doit être exposée à SERVICE/public.

## Tests locaux hors LAN

```bash
python3 -m pytest -q tests/test_service_resource_evidence.py
```

La collecte est strictement en lecture seule. Ne pas lancer
`du` récursif sur le pool pendant une crise mémoire, ni
modifier l'ARC ZFS ou les limites mémoire Docker sans mesure.

## Pression hôte : mémoire, CPU, I/O et ZFS

Un TrueNAS qui répond de nouveau après l'arrêt d'un service (Netdata
le 26/10) montre une corrélation, **pas une preuve** de cause unique.
Mesurer la pression hôte indépendamment des conteneurs, en commençant
par `--skip-docker` si l'hôte gèle :

```bash
cd /mnt/cpool/compose/nabla-compose
python3 scripts/truenas/diagnose-truenas-pressure.py \
  --check --observe-seconds 15 --skip-docker

sudo python3 scripts/truenas/diagnose-truenas-pressure.py \
  --check --observe-seconds 20 --docker-timeout 8 --top 20 \
  --report-dir /mnt/cpool/var/nabla/truenas-pressure
```

Lecture seule de `/proc/meminfo` (MemAvailable), PSI
`/proc/pressure/{cpu,memory,io}`, `/proc/vmstat` (deltas OOM, swap,
major faults, direct reclaim) et `arcstats` ZFS. Un **ARC élevé** n'est
pas à lui seul un manque de mémoire. Un seul `docker stats --no-stream`
borné à 8 s : en cas d'échec, Docker est `UNVERIFIED` mais la pression
hôte reste visible. Le rapport JSON privé (0600 dans un dossier 0700)
ne contient ni environnement, ni commande, ni log.

Le top conteneurs ne donne que des candidats (`high_cpu_snapshot`,
`near_container_memory_limit`,
`large_working_set_not_host_pressure_proof`) : le pourcentage mémoire
Docker est relatif à la limite du **conteneur**, un CPU% peut dépasser
100 %, et un conteneur arrêté n'est plus attribuable.

Ressources hors Docker (VMs Talos `qemu-system-*`, ZFS, processus) :

```bash
sudo bash scripts/truenas/diagnose-performance.sh
ps -eo pid,comm,rss,%cpu --sort=-rss | head -n 25
timeout 15 zpool iostat -v 1 2
sudo journalctl -k -b --since "4 hours ago" --no-pager \
  -g "oom-kill|Out of memory|Killed process|blocked for more than" -n 50
```

| État | Interprétation |
| --- | --- |
| `CRITICAL_PRESSURE` | OOM nouveau ou manque RAM combiné à PSI full |
| `PRESSURE_SIGNAL` | PSI CPU/mémoire/I/O, swap ou reclaim actif ; triage requis |
| `NO_STRONG_CURRENT_SIGNAL` | Aucun fort signal pendant l'échantillonnage, pas une preuve historique |
| `UNVERIFIED` | PSI ou preuve système insuffisants |

Codes de sortie : 0 = aucun signal fort, 1 = pression, 2 = non vérifié.
Une alerte ressource ne signifie pas App DOWN. Ne pas modifier les
limites ARC, Docker ou les services sur la seule base d'un relevé.

## DefectDojo : mémoire et reset de base

**Décision** : réinitialiser la base `defectdojo` **ne libère pas la RAM**
des processus Django, uWSGI et Celery ; le bootstrap qui recrée les
tables peut même l'augmenter temporairement. DefectDojo recommande
environ **8 Go de RAM**, même avec PostgreSQL séparé. Le service a été
relancé le 27/10 **sans reset**. Ordre : pression mémoire → attribution
à DefectDojo → arrêt temporaire si nécessaire → inventaire métier →
éventuel reset séparé, jamais `DROP DATABASE` comme premier diagnostic.
PostgreSQL, Redis et les datasets sont partagés : ne jamais toucher
`cpool/postgres`, la base `postgres`, ses volumes ni les rôles des
autres services.

Preuve mémoire en lecture seule :

```bash
sudo python3 scripts/truenas/diagnose-defectdojo-memory-pressure.py \
  --check --observe-seconds 20
sudo python3 scripts/truenas/diagnose-resource-consumers.py --top 15
```

Le JSON donne `mem_available_*` (MemAvailable, pas la RAM « libre »),
`memory_psi.{some,full}_avg10_pct`, la part récupérable estimée de
l'ARC, `oom_kills_during_observation` (nouveau kill, distinct du
compteur cumulé) et la mémoire des conteneurs DefectDojo. Un
`PRESSURE_LIKELY` exige **MemAvailable bas ET PSI élevé** ;
`OOM_KILL_OBSERVED` est prioritaire ; `INCONCLUSIVE` n'est pas sain.
Ne pas afficher `docker inspect .Config.Env` (mots de passe DefectDojo).

Test de causalité réversible : `midclt call -j app.stop defectdojo`,
nouveau relevé, comparaison, puis `app.start`. Une baisse de pression
rend DefectDojo contributeur plausible, pas une preuve de fuite. Ne pas
redémarrer PostgreSQL, Redis, Traefik, pfSense ou TrueNAS. Le réglage
envisagé après mesure est de réduire `DD_UWSGI_NUM_OF_PROCESSES` et
`DD_UWSGI_NUM_OF_THREADS` (4 et 4 par défaut) en gardant Celery en
`solo` ; pas de nouvelle limite mémoire Docker avant mesure (risque de
boucle OOM).

Avant tout reset, `inspect-defectdojo-db-reset.py --check` (App
arrêtée) compte uniquement les tables métier de la base `defectdojo`
du PostgreSQL partagé, sans DROP/CREATE ni export de données.
`EMPTY_BUSINESS_TABLES` n'est qu'un **candidat**. Un reset exige App
STOPPED, aucun client, aucune ingestion planifiée, un `pg_dump -Fc` de
la seule base `defectdojo` vérifié et une approbation explicite ; il
conserve le rôle, les clés de chiffrement et les secrets Vaultwarden.
Pour un problème de connexion admin, synchroniser plutôt le mot de passe
avec `scripts/truenas/reconcile-defectdojo-admin-password.py`.

## Répartition mesurée le 23 novembre 2026

Sur 62 Gio : conteneurs ≈ 37,5 Gio (Sentry `errors-only` 6,2, gateway OpenClaw 2,5,
Wazuh 2,4, Nexus 2,1, OpenSearch 2,1), 3 VM Talos ≈ 9,5 Gio (H01), noyau ≈ 3,4 Gio.
Pics cgroup nocturnes (01h–06h) : ClickHouse +1 Gio, gateway +0,8, mongo +0,5, docling +0,4.
Contexte et décisions : H10 dans [la roadmap active](../roadmap.md).
