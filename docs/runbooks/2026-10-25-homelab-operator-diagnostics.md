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
Pour les critères de clôture, consulter
[runbook observabilité](2026-10-24-prometheus-pyroscope-dns-dot-recovery.md).

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
non fournie) : Gatus \`85 déclarées / 85 runtime / 85 mappées\`,
\`61 UP / 24 DOWN / 0 UNVERIFIED\`. Aucune dérive de cardinalité.
Les 24 DOWN sont des échecs réellement observés ; cela ne démontre
pas que 24 applications sont indisponibles. Les niveaux TCP, application
et cible de sonde doivent être distingués.

| Famille | Moniteurs DOWN | Lecture opérateur |
| --- | --- | --- |
| HTTP TCP refusé (3) | \`docling:5001\` (\`/ready\`), \`joplin:22300\` (\`/api/ping\`), \`scrutiny:31054\` (\`/api/health\`) | Vérifier conteneur, binding et port ; ne pas corriger HTTP tant que TCP refuse |
| Résolution DNS (1) | \`homeassistant\` via \`homeassistant.albanandrieu.com\` (HTTPS) | Tester la résolution depuis le réseau de Gatus et le DNS privé ; ne pas déclarer le service arrêté |
| TCP réseau Docker interne (1) | \`docker\` → \`docker-socket-proxy:2375\` | Comparer les réseaux Docker de \`gatus\` et \`docker-socket-proxy\` ; **ne jamais publier le port 2375 sur WAN** |
| Exporters TCP (5) | \`haproxy-exporter:9101\`, \`opensearch-exporter:9114\`, \`opensearch-security-exporter:9115\`, \`postgres-exporter:9187\`, \`sybase-exporter:9113\` | Distinguer exporter absent, cible Prometheus DOWN et santé réelle du service exporté |
| Autres TCP hôte (14) | \`dependency-track:31084\`, \`dependency-track-api:31083\`, \`dockhand:3050\`, \`doco-cd:9120\`, \`neo4j-security:31086\`, \`netbox:31082\`, \`nginx-proxy-manager:30021\`, \`npmplus:30360\`, \`plumber:31070\`, \`plumber-api:31071\`, \`scanopy:60072\`, \`sonarqube:9001\`, \`traefik-ddns-updater:8000\`, \`wordpress:8088\` | Condition TCP non satisfaite : vérifier déploiement attendu, état du conteneur, port exposé et firewall avant toute modification |

**Postmigration opérateur :** \`PASS=0 FAIL=4 WARN=0 SKIP=0\`
sur \`postmigration-catalog\`, \`postmigration-service-readiness\`,
\`postmigration-gatus\`, \`postmigration-prometheus\`. Un échec du
catalogue peut être lié aux artefacts générés, mais **sa cause est encore
inconnue**. Les journaux du rapport ne sont pas accessibles dans la PR.

**APISIX :** \`WARN=1\` en section optionnelle \`apisix\`. Ce seul
résultat ne prouve ni déploiement, ni échec de route, ni indisponibilité
applicative ; conserver \`UNVERIFIED\` avant un smoke autorisé.

### Identifier les quatre causes sans divulguer les journaux

Après récupération de la branche contenant ce diagnostic, utiliser le
rapport privé TrueNAS existant. Ce script ne contacte ni LAN ni Docker.

\`\`\`bash
sudo python3 scripts/truenas/triage-postmigration-report.py --check \
  --session /mnt/cpool/var/nabla/migration-20261024/session-gXRf82tS

sudo python3 scripts/truenas/triage-postmigration-report.py --check \
  --session /mnt/cpool/var/nabla/migration-20261024/session-GMLt5rTO
\`\`\`

Sortie : classes fixes (\`generated_catalog_drift\`,
\`catalog_check_failed\`, \`runtime_or_healthcheck_failed\`,
\`observed_monitors_down\`, \`prometheus_scrape_degraded\`,
\`optional_gateway_unverified\`, etc.), et compteurs Gatus bornés.
Les erreurs non reconnues restent génériques ; aucune cause n'est inventée.
Une capture incomplète ou sans son log ne peut pas être entièrement PASS.
Ne pas partager les fichiers \`*.log\` ou \`summary.tsv\` bruts.

### Vérifications complémentaires ciblées, lecture seule

\`\`\`bash
# Depuis TrueNAS, distinguer conteneur arrêté et port non publié.
sudo docker ps -a --format 'table {{.Names}}\t{{.State}}\t{{.Ports}}'
sudo ss -ltn

# Réseau interne du proxy Docker : métadonnées seulement, jamais la clé ni la Socket API.
sudo docker inspect gatus docker-socket-proxy \
  --format '{{.Name}} {{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}'

# Vérification Prometheus en lecture seule, sans afficher les URLs de scrape.
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
\`\`\`

La présence d'un port en écoute ne valide pas l'authentification ou
l'application. **Ne pas créer/recréer 24 conteneurs pour obtenir du vert** :
réconcilier d'abord le catalogue avec les services intentionnellement
déployés, puis confirmer les sondes nécessaires. Séparer les correctifs
Compose (cibles/ports) de ceux du runtime (service réellement arrêté).
