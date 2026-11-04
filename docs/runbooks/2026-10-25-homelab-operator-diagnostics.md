# Homelab — diagnostics opérateur spécialisés

**Mis à jour : 25 octobre 2026.** L'ancien inventaire de commandes
datées est conservé dans
[archive](../archive/2026-10-24/2026-10-24-homelab-operator-next-commands.md).
Cette page complète le [runbook d'acceptation canonique](homelab-runtime-acceptance.md) pour les sondes individuelles en lecture seule.
Aucune commande ici ne démarre, redéploie ou efface un service.

## 1. Services observabilité (TrueNAS)

```bash
sudo python3 scripts/truenas/diagnose-service-bundle.py --check --section observability
# Pour le résultat détaillé de chaque vérification :
python3 scripts/prometheus/diagnose-failed-scrapes.py --check
python3 scripts/truenas/diagnose-gatus-monitors.py --check
sudo bash scripts/truenas/diagnose-observability-post-repair.sh --check
sudo bash scripts/truenas/diagnose-postgres-exporter.sh
python3 scripts/prometheus/audit-telemetry-coverage.py \
  --prometheus-url http://172.17.0.24:9090
```

Le diagnostic Gatus compare chaque sonde déclarée à sa dernière
observation LAN. Il classe les résultats manquants, expirés et ambigus comme
`unverified`. Un HTTP 401/403 peut indiquer une protection Access ou
une condition de sonde inadaptée : **ne pas rendre les endpoints publics
ni affaiblir les conditions**. L'opérateur doit examiner les détails
depuis le tableau Gatus privé. Les services volontairement arrêtés doivent
être classés par intention d'exploitation, pas forcés au vert.

La procédure globale peut être lancée par le script
`scripts/truenas/diagnose-service-bundle.py --check --section observability`
après revue du HEAD ; une panne n'interrompt pas les autres vérifications.

### Diagnostic de performance rapide (4 novembre 2026)

Le script `diagnose-performance.sh` conserve le comportement **complet par
défaut** (`--full` ou sans argument). Un mode `--quick` évite les scans
coûteux lors des incidents de pression mémoire ou I/O :

```bash
# Observation rapide, lecture seule :
sudo bash scripts/truenas/diagnose-performance.sh --quick

# Diagnostic initial historique, sans réduction de périmètre :
sudo bash scripts/truenas/diagnose-performance.sh --full
```

En mode rapide : échantillon `vmstat` instantané, absence de `docker stats`,
`docker system df` et inspection détaillée des conteneurs ; pas de
`zpool iostat` ni d'inventaire intégral des snapshots ZFS ; lecture limitée
aux 500 dernières entrées du journal du noyau. `midclt app.query` reste
collecté une seule fois mais reçoit un timeout de dix secondes.
Les vérifications omises sont **SKIPPED** dans la sortie, jamais saines par
défaut ; le diagnostic complet reste requis pour confirmer leurs résultats.

Le diagnostic FastAPI consolidé utilise désormais
`scripts/lib/bounded_subprocess.py` : lecture incrémentale de stdout, mémoire
bornée à **32 Kio** pour chaque processus enfant et délai global monotone.
En cas de dépassement, le processus et ses descendants dans son groupe
isolé sont interrompus ; stderr n'est jamais collecté. La fonction conserve
le contrat historique `ok/nonzero/missing/timeout/invalid/unavailable`.

Tests de sécurité hors réseau : `tests/test_truenas_quick_performance.py`
et `tests/test_fastapi_bounded_subprocess.py`. Mesurer les gains réels sur
TrueNAS séparément, sans déclencher de CI distante ni imposer le mode rapide.

### Performance des diagnostics (3 novembre 2026)

Les contrôles restent **séquentiels par défaut** (`--jobs 1`) pour limiter
l'impact sur une machine TrueNAS sous pression mémoire/I/O. L'option
explicite `--jobs 2` exécute au plus **deux contrôles indépendants à la
fois**. Les résultats restent dans l'ordre déclaré, avec le même contrat
`PASS/FAIL/UNVERIFIED/NOT_RUN`, les mêmes timeouts individuels et aucune
capture des sorties privées :

```bash
python3 scripts/truenas/diagnose-service-bundle.py --plan \
  --section observability --jobs 2
# À lancer sur TrueNAS uniquement lorsque les ressources sont suffisantes :
sudo python3 scripts/truenas/diagnose-service-bundle.py --check \
  --section observability --jobs 2
```

Ce mode optimise le **temps écoulé** (I/O et attentes réseau) et non le nombre
de sondes ni la consommation totale. Ne pas augmenter la concurrence au-delà
de deux ; revenir à `--jobs 1` si l'ARC, la mémoire ou la PSI I/O sont
dégradés. Il n'existe aucune accélération garantie sur une machine saturée.

Autre réduction de travail redondant : `diagnose-performance.sh` récupère
`midclt call app.query` **une seule fois** pour les deux tableaux d'apps
et ne recherche qu'une fois le PID `containerd`.

**Contrat des verdicts (novembre 2026).** Le coordinateur ne lit jamais les
sorties des processus enfants et ne peut donc **pas** déduire un `DENIED`
à partir du seul code de sortie. Les vérifications renvoient un `verdict`
(`PASS`, `FAIL`, `UNVERIFIED`, `NOT_RUN`), un `reason` borné, et
`evidence_scope=probe_only`. Le verdict `FAIL` est réservé à une sonde
dont le contrat `exit 1` a été validé (moniteurs Gatus ou métriques
PostgreSQL exporter). Un code 1 de Prometheus, OpenRAG ou des scripts
agrégés reste `UNVERIFIED` : il peut correspondre à un manque de preuve,
un blocage d'authentification ou un précontrôle incomplet. Une expiration de
délai (`timeout`) reste également `UNVERIFIED`, jamais une panne
confirmée. Les états `failed` historiques sont des échecs de **sonde**,
pas une preuve que l'application est DOWN. Le champ global
`availability=UNVERIFIED` le rend explicite.

Le rapport JSON fournit aussi `summary` avec des compteurs bornés
pour `PASS`, `FAIL`, `DENIED`, `UNVERIFIED` et `NOT_RUN`.
Ces compteurs sont calculés exclusivement à partir des états et verdicts de
**diagnostic**, sans lire ni reproduire les sorties des enfants. Si un état
d'exécution contredit un verdict (par exemple `failed` avec `PASS`), l'état
prévaut pour empêcher un faux succès. Une catégorie ou une entrée malformée
est comptabilisée `UNVERIFIED`, pas transformée en panne.
Le coordinateur ne peut pas établir `DENIED` uniquement à partir d'un
code de retour ; le compteur existe pour l'homogénéité des contrats.

Codes de retour : `0` si tous les contrôles sont confirmés, `1` si
au moins un échec de sonde est établi, `2` sinon si une preuve manque.
La validation en lecture seule est possible hors TrueNAS mais les
exécutables absents sont `NOT_RUN` ; ne pas en déduire que le service est
indisponible. Pour les critères de clôture, consulter
[runbook observabilité](2026-10-24-prometheus-pyroscope-dns-dot-recovery.md).

Le triage postmigration utilise également les compteurs expurgés
`verdict_counts` du diagnostic Gatus : `DENIED` seul produit
`gatus_access_denied_not_service_down` plutôt que
`observed_monitors_down`. Si l'exécuteur historique marque la phase
`FAIL` mais que seule une autorisation 401/403, l'absence d'échantillons
Gatus ou une API Prometheus inaccessible est établie, le bilan de triage
compte cette phase en **`unverified` plutôt qu'en `failed`**. Le code de
sortie est alors `2`, non `1`, en l'absence d'autre échec confirmé.
Les anciens rapports sans ces compteurs gardent leur interprétation
historique, sans preuve d'indisponibilité applicative.

Tests locaux (sans interroger les services) :

```bash
python3 -m pytest -q tests/test_service_diagnostic_bundle.py tests/test_postmigration_report_triage.py tests/test_truenas_performance_diagnostic_contract.py
```

## 2. pfSense / DNS (diagnostic depuis un hôte autorisé)

```bash
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check
bash scripts/pfsense/diagnose-memory-pressure.sh --check
```

L'absence d'argument `--check` n'autorise **aucune** mutation.
Ne pas multiplier les scrapes pfSense, reboots, mises à jour Snort
ou reconstructions pfBlockerNG pendant le diagnostic.
Voir [runbook pfSense](2026-10-24-pfsense-unbound-pfblocker-whatsapp.md).

## 3. Services applicatifs (TrueNAS)

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh \
  --check --section critical
sudo bash scripts/truenas/diagnose-openrag-startup.sh --check
sudo bash scripts/truenas/diagnose-sentry.sh --check
```

Ces commandes sont indépendantes. Les sorties brutes potentiellement
sensibles restent sur l'hôte ; ne pas les copier dans une PR.
Pour les procédures individuelles, utiliser les
[runbooks référencés](README.md).

## 4. Contrat de sécurité et qualité

- Toutes les opérations runtime de cette page sont en **lecture seule**.
- Une absence d'observation reste `UNKNOWN/NOT_RUN`, jamais `UP`.
- L'agent ne déclenche aucune CI GitHub et ne modifie pas l'état de la
  quality gate du dépôt. La gate complète est **NOT_RUN** pour cette PR
  conformément à l'instruction opérateur ; les tests ciblés peuvent
  être exécutés localement ultérieurement.
- Conserver les modifications `n8n` et `sentry` du checkout opérateur :
  ne pas faire `git reset --hard` ou `git clean -fd`.


## Relevé réel Gatus / postmigration — 25 octobre 2026

**Preuve transmise par l'opérateur, depuis TrueNAS** (révision du checkout
non fournie) : Gatus `85 déclarées / 85 runtime / 85 mappées`,
`61 UP / 24 DOWN / 0 UNVERIFIED`. Aucune dérive de cardinalité.
Les 24 DOWN sont des échecs réellement observés ; cela ne démontre
pas que 24 applications sont indisponibles. Les niveaux TCP, application
et cible de sonde doivent être distingués.

| Famille | Moniteurs DOWN | Lecture opérateur |
| --- | --- | --- |
| HTTP TCP refusé (3) | `docling:5001` (`/ready`), `joplin:22300` (`/api/ping`), `scrutiny:31054` (`/api/health`) | Vérifier conteneur, binding et port ; ne pas corriger HTTP tant que TCP refuse |
| Résolution DNS (1) | `homeassistant` via `homeassistant.albanandrieu.com` (HTTPS) | Tester la résolution depuis le réseau de Gatus et le DNS privé ; ne pas déclarer le service arrêté |
| TCP réseau Docker interne (1) | `docker` → `docker-socket-proxy:2375` | Comparer les réseaux Docker de `gatus` et `docker-socket-proxy` ; **ne jamais publier le port 2375 sur WAN** |
| Exporters TCP (5) | `haproxy-exporter:9101`, `opensearch-exporter:9114`, `opensearch-security-exporter:9115`, `postgres-exporter:9187`, `sybase-exporter:9113` | Distinguer exporter absent, cible Prometheus DOWN et santé réelle du service exporté |
| Autres TCP hôte (14) | `dependency-track:31084`, `dependency-track-api:31083`, `dockhand:3050`, `doco-cd:9120`, `neo4j-security:31086`, `netbox:31082`, `nginx-proxy-manager:30021`, `npmplus:30360`, `plumber:31070`, `plumber-api:31071`, `scanopy:60072`, `sonarqube:9001`, `traefik-ddns-updater:8000`, `wordpress:8088` | Condition TCP non satisfaite : vérifier déploiement attendu, état du conteneur, port exposé et firewall avant toute modification |

**Postmigration opérateur :** `PASS=0 FAIL=4 WARN=0 SKIP=0`
sur `postmigration-catalog`, `postmigration-service-readiness`,
`postmigration-gatus`, `postmigration-prometheus`. Un échec du
catalogue peut être lié aux artefacts générés, mais **sa cause est encore
inconnue**. Les journaux du rapport ne sont pas accessibles dans la PR.

**APISIX :** `WARN=1` en section optionnelle `apisix`. Ce seul
résultat ne prouve ni déploiement, ni échec de route, ni indisponibilité
applicative ; conserver `UNVERIFIED` avant un smoke autorisé.

### Identifier les quatre causes sans divulguer les journaux

Après récupération de la branche contenant ce diagnostic, utiliser le
rapport privé TrueNAS existant. Ce script ne contacte ni LAN ni Docker.

```bash
sudo python3 scripts/truenas/triage-postmigration-report.py --check \
  --session /mnt/cpool/var/nabla/migration-20261024/session-gXRf82tS

sudo python3 scripts/truenas/triage-postmigration-report.py --check \
  --session /mnt/cpool/var/nabla/migration-20261024/session-GMLt5rTO
```

Sortie : classes fixes (`generated_catalog_drift`,
`catalog_check_failed`, `runtime_or_healthcheck_failed`,
`observed_monitors_down`, `prometheus_scrape_degraded`,
`optional_gateway_unverified`, etc.), et compteurs Gatus bornés.
Les erreurs non reconnues restent génériques ; aucune cause n'est inventée.
Une capture incomplète ou sans son log ne peut pas être entièrement PASS.
Ne pas partager les fichiers `*.log` ou `summary.tsv` bruts.

### Correctif du classificateur Prometheus

Le script `diagnose-prometheus-targets.sh` imprime toujours le titre
`=== Prometheus config drift ===`. L'ancien analyseur classait ce titre
comme une erreur réelle, même lorsque le fichier monté correspondait.
Le nouveau classificateur ne retient une dérive de configuration que sur
un message d'échec explicite (désaccord d'empreinte, `promtool`
en échec, permission refusée). Un échec de scrape est signalé
séparément, avec `target_up`, `target_not_up` et des `signals`
de catégories fixes.

Dans la sortie readiness, le texte `no Docker healthcheck` ne constitue
pas un healthcheck en échec. L'analyseur renvoie les services concernés
uniquement s'ils figurent dans l'allowlist du diagnostic. Ne pas corriger
les fichiers ou changer les permissions Prometheus sur la seule base
de l'ancienne catégorie `prometheus_config_or_rules`.

### Vérifications complémentaires ciblées, lecture seule

```bash
# Depuis TrueNAS, distinguer conteneur arrêté et port non publié.
sudo docker ps -a --format 'table {{.Names}}\t{{.State}}\t{{.Ports}}'
sudo ss -ltn

# Réseau interne du proxy Docker : métadonnées seulement, jamais la clé ni la Socket API.
sudo docker inspect gatus docker-socket-proxy \
  --format '{{.Name}} {{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}'

# Vérification Prometheus en lecture seule, sans afficher les URLs de scrape.
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
```

La présence d'un port en écoute ne valide pas l'authentification ou
l'application. **Ne pas créer/recréer 24 conteneurs pour obtenir du vert** :
réconcilier d'abord le catalogue avec les services intentionnellement
déployés, puis confirmer les sondes nécessaires. Séparer les correctifs
Compose (cibles/ports) de ceux du runtime (service réellement arrêté).


### Nouveau relevé postmigration — classification affinée

Le second relevé opérateur du 25 octobre identifie :
- Catalogue : `generated_catalog_drift` et `stale_artifact_count=3`. Le générateur
  versionné produit `entities.json`, `homelab.cdx.json` et
  `identity-map.json`. Confirmer les chemins autorisés présents dans
  `stale_artifacts` avant toute régénération.
- Readiness : `gatus=WARN`, `scrutiny=BLOCKED`, `sample=WARN`.
  `service_reasons` classe les notes existantes sans publier leur texte.
  Une sonde Gatus DOWN n'est pas une preuve de panne du processus Gatus ;
  le warning FastAPI peut seulement signifier une provenance Git absente.
- Prometheus : `target_up=21`, `target_not_up=7`, signal
  `scrape_targets_degraded`. `failed_jobs` reprend les seuls noms
  versionnés du catalogue, leurs compteurs et leurs catégories d'erreur.
  La liste des sept jobs reste à confirmer dans le rapport privé.
- APISIX : `optional_gateway_unverified`, sans déploiement prouvé.

Sans nouvelle connexion réseau, relire les deux sessions existantes
depuis une copie de la branche #280 :

```bash
sudo python3 scripts/truenas/triage-postmigration-report.py --check \
  --session /mnt/cpool/var/nabla/migration-20261024/session-gXRf82tS

sudo python3 scripts/truenas/triage-postmigration-report.py --check \
  --session /mnt/cpool/var/nabla/migration-20261024/session-GMLt5rTO
```

Ces commandes sont **read-only**. Elles peuvent retourner `1` ou `2`
tant que la panne est confirmée ou qu'une observation manque.
Les informations `stale_artifacts`, `service_reasons` et `failed_jobs`
ne sont présentes que si le journal privé contient une preuve analysable.
Ne pas publier les journaux privés ou les sorties brutes Prometheus.

Pour contrôler les jobs Prometheus en direct depuis un hôte autorisé,
le classificateur déjà présent suffit :

```bash
python3 scripts/prometheus/diagnose-failed-scrapes.py --check --scope remaining
```

Cette commande ne donne aucune autorisation de déployer un exporter
ou de modifier le scrape config. Comparer les sept jobs attendus avec
les sept DOWN réels avant de proposer une correction.

Pour les trois artefacts, une régénération éventuelle doit rester
dans un worktree isolé et faire l'objet d'un diff revu ; aucun
générateur n'a été exécuté en mode écriture sur TrueNAS.
