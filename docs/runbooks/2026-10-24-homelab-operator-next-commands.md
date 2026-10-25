# Homelab — commandes opérateur restantes (2026-10-24)

> **Historique — état observé en octobre 2026.** Ce fichier conserve
> ses commandes et preuves à titre de traçabilité ; il n'est pas le point
> d'entrée pour un nouveau diagnostic. Lire d'abord
> [l'acceptation runtime courante](homelab-runtime-acceptance.md) et
> [la roadmap active](../roadmap.md). Aucune commande mutante ci-dessous
> n'est autorisée par cet archivage. La PR #274 est fusionnée.


**Document opérateur canonique** pour les contrôles de migrations TrueNAS
du 24 octobre. Les scripts ne doivent pas afficher son contenu, seulement
le chemin de cette documentation. Ce runbook contient les commandes à exécuter,
non une deuxième roadmap.

**Runbooks spécialisés (historique conservé, ne pas dupliquer leur procédure) :**
- [pfSense : OOM, DNSBL et WhatsApp](2026-10-24-pfsense-unbound-pfblocker-whatsapp.md)
- [Récupération des Apps TrueNAS (23 octobre)](2026-10-23-app-error-recovery.md)
- [Acceptation historique des migrations (24 octobre)](2026-10-24-truenas-migration-acceptance.md)
- [Migration accélérée Talos/TrueNAS](2026-10-23-fast-batch-migration.md)

Ce document appartient à `nabla-compose`. Il complète
`scripts/truenas/finish-migrations-20261024.sh`.

**Sécurité :** toutes les commandes présentées comme diagnostics sont en lecture
seule pour le runtime. Le script central peut créer des rapports privés `0600`.
Aucune commande de cette liste ne lance de déploiement, de réparation ou de
migration de secret. Ne pas exécuter les commandes en bloc. Lire le résultat
d'une étape avant de passer à la suivante.

L'ordre des responsabilités reste :
`nabla-compose` = identité, exposition souhaitée et déploiement déclaré ;
`fastapi-sample` = observations et DTO OWNER/SERVICE ;
`nabla-site-alban` = rendu, icônes locales et cache SERVICE expurgé.

## Étape 0 — quality gates locales consolidées

Le runner `finish-migrations-20261024.sh` propose deux modes distincts :

- `--next-commands` **affiche seulement le chemin** de ce runbook, sans
  reproduire son contenu, sans root et sans accéder à TrueNAS ;
- `--local-gates` exécute **séquentiellement** les cinq recettes ci-dessous,
  sur un checkout de développement **non-root**, et s'arrête au premier échec.

```bash
# Consultation sans exécution :
bash scripts/truenas/finish-migrations-20261024.sh --next-commands
just migration-20261024-commands

# Option manuelle : exactement cinq commandes, dans cet ordre :
just migration-20261024-commands
just migration-20261024-test
just catalog-convergence-check
just agent-skills-check
just quality

# Option consolidée (mêmes cinq recettes) :
bash scripts/truenas/finish-migrations-20261024.sh --local-gates
# Ou :
just migration-20261024-local-gates
```

La qualité locale peut vérifier ou modifier des fichiers du checkout selon
la définition actuelle de `mise run agent-quality`. Elle ne déploie pas
TrueNAS et ne lance pas de CI GitHub. Ne pas exécuter `--local-gates`
en root ou dans le répertoire GitOps TrueNAS monté dans les conteneurs.
Exécuter sur un worktree de développement isolé avec `just`, `mise` et
les outils de qualité disponibles. Une sortie `LOCAL_GATES_COMPLETE=5`
ne valide **pas** l'état des Apps.

## Étape P0 — diagnostic groupé des cinq services à vérifier

**Commande opérateur TrueNAS, uniquement sur un checkout contenant les scripts
revus de la PR #274, sans migration ni relance d'Apps :**

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh \
  --check --section critical
```

Ce mode accepte explicitement les sections `critical` et `sentry`.
Il lance **cinq familles de preuves indépendantes**, même si la première
échoue : Prometheus (UID/GID 568, YAML principal, règles, boucle de crash),
OpenRAG (état App et backend/frontend, Langflow, OpenSearch, secret canonique),
Sentry (consommateurs Kafka, credentials, préflight sans redéploiement) et
Akvorado (inlet/outlet, deux scrapes à 20 secondes, erreurs de métadonnées
et nouveaux batches ClickHouse), puis DefectDojo (uWSGI, HTML, DNS privé, Traefik TLS).

Le résultat terminal fournit les comptes `PASS/FAIL` et le chemin du rapport
privé. Le propriétaire doit inspecter les journaux correspondant aux gates
en échec **sur TrueNAS**, sans copier les secrets ni les logs bruts dans une PR.

| Service | Dernière preuve connue | Gate d'acceptation |
| --- | --- | --- |
| Prometheus | `running`, 15 règles valides/lisibles, 8 targets non UP | corriger les cibles DOWN séparément ; ne pas réparer à nouveau les règles |
| OpenRAG | `STOPPED`, backend/frontend absents au dernier relevé ; démarrage annoncé par l'opérateur, non revérifié | App `RUNNING`, backend/frontend healthy ; Docling et ingestion restent des gates distinctes |
| Sentry | `DEPLOYING`, 2 consommateurs Kafka `unhealthy` ; redémarrage annoncé par l'opérateur, non revérifié | consumers healthy, Sentry edge et smoke E2E après accord |
| Akvorado | 38 190 flux historiques rejetés ; aucune nouvelle activité sur la fenêtre de 20 s | nouveaux flux et **lignes SQL ClickHouse** attestés, métadonnées réconciliées |

| DefectDojo | UI HTTPS privée ne répond pas (signalement opérateur, sans diagnostic détaillé) | origin HTML 200/30x, uWSGI en marche, DNS privé et HTTPS SNI vérifiés |\n\nPour Prometheus, **ne pas appliquer `--expected-unreadable 2`** sur la base
de l'ancien inventaire. Vérifier le nombre actuel en `--check`; une
correction de règles nécessite son propre acquittement `--apply`.
Ne pas modifier TSDB/WAL, Kafka offsets, corpus OpenRAG ni secrets.

La commande groupée ne constitue **ni** un feu vert de redéploiement, **ni**
une preuve d'acceptation applicative si des gates échouent. Sur le TrueNAS
canonique resté sur un `master` plus ancien, utiliser les scripts `--check`
individuels déjà présents ; ne pas recopier la PR Draft dans un bind en cours
d'exécution pour obtenir cette commande.

## Relevé opérateur du 24 octobre, 23 h 09 — triage stabilisé

Ce bloc remplace les hypothèses plus anciennes de crash Prometheus ou
d'OpenRAG `DEPLOYING`. Il s'agit de **six gates individuelles,
dont cinq bloquantes**, et non de cinq applications cassées.

| Gate | Preuve | Action suivante |
| --- | --- | --- |
| Prometheus | conteneur `running`, SHA du YAML monté égal à l'hôte ; `promtool` PASS avec 15 règles ; job `prometheus` UP | distinguer serveur sain et **8 scrape targets non UP** |
| Prometheus rules | 15/15 fichiers lisibles par `568:568` | **ne pas répéter les réparations de modes** |
| OpenRAG | TrueNAS `STOPPED`, backend/frontend `missing`, Langflow/OpenSearch Docker healthy ; lifecycle = 1 intentional-stopped différé | vérification d'intention + préflight secret avant tout `app.start` |
| Sentry | TrueNAS `DEPLOYING`, classe `kafka-timeout` ; 2 consumers `running/unhealthy`, restarts=0, logs récents `sample=0` | inspecter les codes numériques des healthchecks, le heartbeat et les préflights Kafka, sans reset d'offsets |
| Akvorado | inlet 3 190 paquets, Kafka 3 190 messages, outlet 38 190 flux reçus et 38 190 erreurs, batch ClickHouse=0 | comparer la config statique présente dans orchestrator, exporter et ifIndexes, puis **nouvelles** métriques après trafic |
| Cycle de vie Apps | `sentry=DEPLOYING`, une App intentional-stopped | préserver les reports privés et ne pas traiter tous les STOPPED comme crash |

Les cibles non UP de Prometheus sont :
`docling`, `fastapi_sample`, `haproxy`, `litellm_hermes`,
`opensearch`, `opensearch-security`, `pfsense_exporter`
(`unknown`) et `postgres_exporter`.
**Un scrape OpenSearch DOWN ne signifie pas que le conteneur OpenSearch
est arrêté** : son healthcheck Docker est `healthy`.

Le compteur `akvorado_outlet_metadata_provider_errors_total=75860`
et le compteur SNMP `=1315` sont **cumulatifs**. Les deux scrapes à
20 secondes ont mesuré `delta_received_flows=0`,
`delta_metadata_missing=0`, `delta_kafka_messages=0` et
`delta_clickhouse_batches=0`.
Cela prouve une chaîne historiquement bloquée par le metadata provider ;
cela **ne prouve pas** qu'un nouveau flux est encore rejeté maintenant.

Le dépôt déclare seulement un metadata provider statique
`172.17.0.1/32` avec l'interface `ifIndex=11`.
L'étape de diagnostic ajoutée à la PR #274 vérifie par hash le fichier
`/etc/akvorado/akvorado.yaml` dans le conteneur orchestrator,
puis affiche les erreurs cumulées pour l'exportateur attendu et les
autres, **sans afficher les adresses du flux**.

```bash
# Diagnostics exclusivement en lecture seule, depuis un checkout revu
# de la PR #274 (ou après son intégration sur master).
sudo bash scripts/truenas/diagnose-akvorado-config.sh --check
sudo python3 scripts/truenas/diagnose-akvorado-flow.py \
  --strict --observe-seconds 20 --fail-on-blocked --require-inserts
sudo bash scripts/truenas/diagnose-sentry-consumers.sh --check
sudo bash scripts/truenas/recover-sentry-deploying.sh --check
```

Ne pas interpréter les erreurs SNMP passées comme la preuve que SNMP est
encore actif. Si la configuration host/conteneur diffère, examiner la
Custom App stockée dans TrueNAS avant toute nouvelle réconciliation.
Si les SHA concordent, cela atteste le montage, **pas** la configuration
déjà chargée en mémoire ni les ifIndexes envoyés aujourd'hui par pfSense.

La documentation upstream Akvorado précise que les flux sans
métadonnées d'interface sont rejetés et que le provider statique
doit associer l'adresse exporter et les ifIndexes observés :
https://github.com/akvorado/akvorado/blob/main/console/data/docs/02-configuration.md

Aucun effacement ClickHouse, TSDB/WAL, flux historiques, offset Kafka,
corpus OpenRAG ni restart massif n'est autorisé sur cette preuve.

## Archives P0 — preuves antérieures, remplacées par le relevé de 23 h 09

**À ne pas utiliser comme consignes de réparation actuelles :**
les commandes `--apply` ci-dessous documentent des états de permissions
anciens. Les 15 règles Prometheus sont désormais lisibles ; ne pas répéter
une réparation de fichiers. Ne jamais redémarrer les services cités sur
la base d'un état archivé.

**Prometheus** : App TrueNAS `RUNNING`, conteneur `restarting`,
exit 2, **2221 redémarrages**. Montage `/etc/prometheus` correct,
UID/GID `568:568` et lecture hôte du YAML principal OK, mais
`prometheus.yml` est maintenant en **0644** (world-readable).
Les 15 règles sont inventoriées et **une seule** reste illisible
(`uid=1000 gid=568 mode=0600`). La tentative d'appliquer
`--expected-unreadable 2` a **été refusée à juste titre** par la
protection anti-dérive. Aucune réparation ne s'est produite.

```bash
# Vérifications non mutantes, avant chaque intervention :
sudo bash scripts/truenas/repair-prometheus-config-access.sh --check
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check

# Si le YAML principal reste 0644 et le chemin/montage sont vérifiés,
# réparation séparée UNIQUEMENT du fichier principal après revue :
sudo bash scripts/truenas/repair-prometheus-config-access.sh --apply

# Si le préflight des règles constate toujours exactement UN fichier
# inaccessible, réparation explicite UNIQUEMENT de celui-ci :
sudo bash scripts/truenas/repair-prometheus-rules-access.sh \
  --apply --expected-unreadable 1 \
  --acknowledge I_ACCEPT_PROMETHEUS_RULES_PERMISSION_REPAIR

# Preuves de sortie :
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
```

Ne pas copier les deux `--apply` sans consulter les préflights et
l'état courant : chaque correction nécessite sa propre validation et
son autorisation opérateur. Ne pas modifier les ACL en masse, effacer la
TSDB/WAL ou redéployer toute l'App.

**OpenRAG** : App `STOPPED`, aucun backend/frontend Docker, mais
Langflow `running+healthy` et OpenSearch `running+healthy`.
Ce n'est **pas** un simple healthcheck frontend `created` ; vérifier
la cause de l'arrêt, le secret canonical et les dernières tâches
middleware avant tout `app.start`.

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section openrag
sudo bash scripts/truenas/diagnose-stuck-apps.sh --check --app openrag
```

**Sentry** : TrueNAS `DEPLOYING`, deux consommateurs Kafka
`sentry-events-consumer` et
`sentry-post-process-forwarder-errors` `unhealthy`. Ne pas
redémarrer Kafka, réinitialiser ses consumer offsets ni redéployer
Sentry avant le diagnostic des consommateurs et la preuve de santé
du runtime ClickHouse et des credentials.

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section sentry
sudo bash scripts/truenas/diagnose-sentry-consumers.sh --check
sudo bash scripts/truenas/recover-sentry-deploying.sh --check
```

Ce mode `--check` collecte les preuves détaillées dans des journaux
privés. Il ne lance ni `--apply`, ni `--finalize`, ni smoke mutante.
Un diagnostic `SESSTMOUT` oriente vers le groupe Kafka et la
coordination, pas automatiquement vers une corruption des offsets.

**Gate bloquante** : tant que Prometheus, OpenRAG, Scrutiny et Sentry
n'ont pas de validation runtime, ne pas déclencher les migrations
TrueNAS groupées, Talos/Kubernetes ou la suppression de secrets legacy.

## Qualité locale : anomalies corrigées après le retour opérateur

La séquence de développement a établi : `59 passed, 6 skipped` pour
les contrats migrations/Sentry, `8 passed` pour les tests du catalogue,
`8 passed` pour les tests unitaires de politique des skills ; le contrôle
réel `agent-skills-check` échouait car la section réglementaire avait
disparu de `docs/roadmap.md`. Le contrôle global a ensuite bloqué sur
`QG_LARGE_DELETION` (environ 97 % du document supprimé).

**Correctif dans la PR #274 :** restaurer la roadmap entière depuis la
révision `master` contrôlée, puis conserver seulement le suivi de la PR.
Ne jamais utiliser `QUALITY_ALLOW_LARGE_DELETION=1` pour un écrasement
accidentel de documentation.

`just quality` appelle maintenant directement
`bash scripts/agent-quality-gate.sh`, sans phase
`mise run agent-quality` qui tentait de réécrire les verrous et télécharger
plusieurs outils depuis TrueNAS. Les contrôles de qualité restent
bloquants : pré-commit/Python/outils manquants ne deviennent pas `PASS`.

**Écart mise sur TrueNAS :** la branche GitHub vérifiée contient
`lockfile_version = 2`, mais l'opérateur a obtenu
`unsupported lockfile version 3` sur son fichier local. Avant toute
régénération ou modification du lockfile :

```bash
git status --short -- docs/roadmap.md mise.lock
git show HEAD:mise.lock | sed -n '1,6p'
sed -n '1,6p' mise.lock
mise --version
```

Cette comparaison doit rester **en lecture seule** ; ne pas exécuter
`mise lock`, `git reset --hard`, `git clean` ou télécharger de nouveaux
artéfacts pour masquer le décalage.

## Étape A — checkout opérateur TrueNAS et réseau Git (pré-requis)

Le 24 octobre, un checkout TrueNAS a été observé en retard sur GitHub, avec
`fastapi-sample` modifié comme sous-module. La PR Compose #273 est fusionnée ; la reprise active est la PR Draft #274. Les PR site #254 et FastAPI
#373 ont été fusionnées le 24 octobre 2026 à 16:27 et 16:28 UTC. **Ne pas appliquer une branche Draft à TrueNAS.**

Exécuter depuis `/mnt/cpool/compose/nabla-compose` :

```bash
git status --short
git branch --show-current
git log -1 --oneline
getent ahostsv4 github.com
curl -4 -I --connect-timeout 8 --max-time 12 https://github.com
git remote -v
```

Après rétablissement réseau, uniquement sur `master` propre et après fusion
des correctifs nécessaires :

```bash
git -c submodule.recurse=false fetch origin master
git -c submodule.recurse=false merge --ff-only origin/master
```

Ne pas exécuter `reset --hard`, `clean` ou un `git submodule update --force`.
Une connexion GitHub indisponible interdit de prétendre que TrueNAS contient
les derniers correctifs. Ne pas corriger les certificats en désactivant TLS.

## Étape B — diagnostics centraux en lecture seule

Sur TrueNAS, une fois le checkout opérateur à jour :

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section platform
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section migrations
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section observability
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section secrets
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section convergence
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section lan
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section services
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section ai
sudo bash scripts/truenas/finish-migrations-20261024.sh --plan-wave core
sudo bash scripts/truenas/finish-migrations-20261024.sh --plan-wave gatus
sudo bash scripts/truenas/finish-migrations-20261024.sh --plan-wave deferred
```

Les sections peuvent échouer tant que les migrations ne sont pas terminées.
C'est un résultat de diagnostic, **pas** une autorisation de `--apply`.
Les rapports sont privés. Ne pas les publier sur GitHub ou dans un chat.

## Étape B.1 — diagnostics P0 individuels (une commande par incident)

Après revue des scripts de la PR Compose #274 sur le checkout opérateur
**par fusion revue dans master**, sélectionner une seule section selon le chantier.
Chaque commande collecte un rapport privé sous
`/mnt/cpool/var/nabla/migration-20261024`. Aucune ne lance un redeploy.

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section prometheus
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section openrag
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section akvorado
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section secrets
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section convergence
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section lan
```

L'exécution **individuelle** permet de collecter une seule preuve à la fois.
`--section akvorado` compare deux intervalles de compteurs, dont les
insertions ClickHouse : prévoir un trafic réel pendant la fenêtre de mesure.
`--section prometheus` sépare la preuve Docker des cibles réseau.
`--section openrag` n'exécute que des comparateurs de secrets en mode
`--check`. **Le mode `--apply-step openrag-secret` a été retiré** :
l'ancien script `reconcile-openrag-opensearch-secret.sh --apply`
écrit dans `/mnt/cpool/openrag/.env.secrets` au lieu du chemin Vaultwarden
canonique. Ne pas le lancer, y compris avec `--allow-reviewed-drift`.

Pour retrouver uniquement les noms des rapports produits par un diagnostic,
consulter son récapitulatif `summary.tsv` dans le répertoire privé indiqué.
Ne jamais coller de fichiers `.env`, de réponses OWNER brutes ou de journaux
contenant des tokens dans GitHub.

## Étape C — Prometheus : réparer la cause, pas uniquement l'icône RUNNING

Le snapshot OWNER du 24 octobre montrait **App prometheus RUNNING** et
**conteneur principal prometheus exited**. Il s'agit d'une observation
historique. Il faut mesurer l'état actuel, et non conclure sur la base du
snapshot.

```bash
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
sudo bash scripts/truenas/repair-prometheus-config-access.sh --check
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check
```

L'analyse doit distinguer l'accès UID/GID 568 à la configuration, les règles
Prometheus, la présence du conteneur principal, le TSDB et les cibles/exporters.
Ne pas modifier les données de Prometheus ni son WAL. Ne pas redémarrer avant
d'avoir identifié le problème. Si une permission est incorrecte, demander une
réparation **ciblée** avec ses préconditions et une validation après changement.
Un exporter RUNNING ne prouve pas qu'une métrique Gatus/Prometheus est fraîche.

## Étape D — OpenRAG / Docling / LiteLLM : dépendances et secrets

```bash
sudo bash scripts/truenas/diagnose-openrag-dependencies.sh --check
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check openrag
python3 scripts/check-service-migration-bundle.py --app openrag
```

**Correction GitOps en PR #274 :** le comparateur OpenRAG/OpenSearch cherche
les candidats canoniques `/mnt/cpool/secrets/runtime/opensearch/.env`
ou `.env.secrets`, puis l'ancien `apps/opensearch/.env`. Il ne suppose pas
que le fichier trouvé est le secret effectif du conteneur déjà lancé.
Le mode `--apply` historique est **désactivé** ; comparer et revoir
Vaultwarden/la configuration Custom App avant tout cutover. Si `midclt`
est absent, les préflights TrueNAS doivent être exécutés sur TrueNAS,
non depuis la workstation. Ne jamais afficher les valeurs de secret.

Le résultat d'OpenRAG doit prouver backend et frontend `running+healthy`,
Langflow et OpenSearch disponibles. La disponibilité Docling,
des embeddings LiteLLM workstation et de l'ingestion doit être validée
séparément ; un conteneur sain ne prouve pas l'indexation des documents.

## Étape E — Akvorado / pfSense : rejet des flux NetFlow v5

Pour les preuves OOM Unbound/CrowdSec et tests Wi-Fi, suivre le
[runbook pfSense spécialisé](2026-10-24-pfsense-unbound-pfblocker-whatsapp.md).
Le diagnostic détaillé n'est pas reproduit dans le runner.


```bash
python3 -m unittest discover -s tests -p 'test_akvorado*' -v
python3 scripts/truenas/diagnose-akvorado-flow.py --strict --fail-on-blocked --observe-seconds 30
python3 scripts/truenas/diagnose-akvorado-flow.py --strict --require-inserts --observe-seconds 30
docker compose -f apps/akvorado/compose.yml config --quiet --no-interpolate --no-env-resolution
```

Le deuxième relevé ne doit pas montrer de nouveaux rejets
`metadata missing`. Le troisième exige de nouveaux lots ClickHouse
**sans** nouveaux rejets. Ces compteurs ne prouvent pas des lignes SQL ;
vérifier ensuite les lignes récentes avec une requête SQL limitée, puis leur
visibilité dans Akvorado Console. Il faut d'abord valider le schéma de
l'application Akvorado épinglée et confirmer le chargement du provider statique
`172.17.0.1/32, ifIndex=11`. Le nom physique et la vitesse restent inconnus.
Ne pas augmenter le tracking global Netgate 1100, ni activer un balayage SNMP
lourd. Ne pas redéployer automatiquement.

## Étape F — sondes LAN et DTO OWNER/SERVICE

```bash
sudo bash scripts/truenas/verify-fastapi-lan-probes.sh --check
python3 scripts/quality/check-site-catalog-convergence.py
python3 scripts/quality/check-agent-skill-precedence.py
```

La preuve LAN exige : collecteur `FASTAPI_RUNTIME_MODE=homelab`, activation
`HOMELAB_INTERNAL_PROBES_ENABLED=true`, `eligible>0`,
`sampled>0` et `completed>0`. Une déclaration host/port LAN sans
résultat ne vaut pas une sonde. L'activation des sondes LAN nécessite la
politique SSRF et un collecteur LAN autorisé. Aucun contournement de 401/403.

Dans un checkout où `../nabla-site-alban` pointe sur la même
révision de catalogue source :

```bash
python3 scripts/quality/check-site-catalog-convergence.py --site-generated ../nabla-site-alban/lib/homelabCatalogIcons.generated.ts
```

Les données OWNER (IP, ports, TLS, Cloudflare, latence, heure de sonde,
Prometheus) restent interdites au cache public du site. Une
`catalogRevision` incompatible impose `unknown`, jamais un faux OK.

## Étape G — secrets à migrer, un service à la fois

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
python3 scripts/secrets/inventory_vaultwarden.py --json
sudo bash scripts/truenas/accept-runtime-env-first-wave.sh --check all
```

L'inventaire Vaultwarden exige une session Bitwarden CLI autorisée. En son
absence, marquer le résultat **NOT_RUN**, pas SUCCESS. Ne pas transmettre
`BW_SESSION`, `DIAGNOSTICS_ACCESS_KEY` ni une sortie d'environnement.

La première vague prévue reste `scanopy`, `joplin`, `autokuma` et
`code`. D'autres identités sont dans `config/secrets/manifest.json`.
Lire les clés **par nom seulement**. Corriger les sources et les permissions
avant de préparer un `--stage`. Le passage à `--accept` exige un service
sélectionné, une validation Compose, un test fonctionnel et un rollback.
Les copies git-crypt historiques sont des sources de récupération, pas la
destination d'exécution.

## Étape H — noms et ports, puis Talos

```bash
sudo bash scripts/truenas/migrate-homeassistant-openwebui-names.sh --check
python3 scripts/quality/check-site-catalog-convergence.py
```

La cible déclarée est `openwebui` ; l'ancien hôte Cloudflare reste en place
jusqu'à recette avec Access. `homeassistant` est déjà canonique côté Compose.
Les ports Gatus `:8085`, Bichon `:15630`, Garage S3 `:3900`,
Garage Admin `:3903` et Garage UI `:3909` doivent être vérifiés
indépendamment dans le runtime. Ne jamais remplacer une URL interne par
l'origine Cloudflare simplement parce qu'elle est déclarée.

Depuis la workstation autorisée, avec `talosctl` et `kubectl` configurés :

```bash
bash scripts/talos/validate-cluster.sh
python3 scripts/talos/preflight-supported-upgrade.py --check
bash scripts/talos/smoke-truenas-csi-nfs.sh --check
```

Ne pas exécuter `kubectl apply`, `helm upgrade` ou une migration CSI/PVC
en masse sans plan de rollback et autorisation.

## Étape I — qualité locale et fermeture

Sur la branche de PR de développement, avec les outils prévus installés
dans le **poste de développement** et aucun secret runtime importé :

```bash
just agent-skills-check
just catalog-convergence-check
python3 -m unittest discover -s tests -p 'test_akvorado*' -v
python3 -m pytest -q tests/test_finish_migrations_20261024.py
just quality
```

Ne pas annoncer la quality gate complète comme validée tant qu'elle n'a
pas été réellement exécutée sur le HEAD exact. La PR Compose #273 est fusionnée ; la reprise active est la PR Draft #274. Les PR FastAPI #373 et Site #254 sont
fusionnées, mais leurs déploiements et la collecte OWNER/LAN demandent encore
une validation indépendante. Les skills externes ne s'installent qu'après
accord explicite demandé à l'utilisateur.

## Opérations mutantes : hors exécution automatisée

Le script central sait proposer `--plan-wave`, puis exécuter
`--apply-wave` avec le **hash de plan frais** et un acquittement explicite,
uniquement depuis le checkout TrueNAS canonique `master` propre.
Les réconciliations de secrets et les redéploiements demandent également
une revue ciblée. Ne jamais copier tous les `--apply` dans une commande
unique. Un échec du diagnostic n'autorise pas le démarrage automatique
d'un service ni une réparation des permissions.

**Done :** artefacts de catalogue concordants, secrets sous Vaultwarden,
Prometheus avec conteneur principal et scrape validés, OpenRAG/Docling
fonctionnels, Akvorado avec nouvelles lignes ClickHouse observées,
sondes LAN réelles et rendus OWNER/SERVICE conformes.

## Étape J — demandes de données nécessaires pour continuer les trois projets

Ces commandes fournissent les **preuves manquantes**, sans rendre publiques
les données privées de TrueNAS. Elles ne supposent pas que le site et FastAPI
sont à la même version que le catalogue Compose.

### J.1 — État des PR et révisions

Sur une workstation autorisée (ou TrueNAS si HTTPS GitHub fonctionne) :

```bash
git -c submodule.recurse=false fetch origin master
git log -1 --format='%h %s' origin/master
git status --short --ignore-submodules=none
```

**Ne pas** exécuter `merge` lorsque le checkout a des changements locaux
non revus. La PR #273 est fusionnée ; la PR #274 est Draft, donc ses
nouveaux scripts ne sont pas nécessairement disponibles sur `master`.
Le résultat `git status` peut contenir
un sous-module modifié : préserver cet état et documenter sa cause.

### J.2 — Vérification de la convergence des catalogues

Dans `nabla-compose`, sans informations sensibles :

```bash
just agent-skills-check
just catalog-convergence-check
python3 scripts/generate-catalog-v2-artifacts.py --check
python3 scripts/generate-service-topology.py --check
python3 scripts/generate-service-consumers.py --check
```

Sur la workstation qui possède **les deux checkouts** sur des révisions
connues et compatibles :

```bash
python3 scripts/quality/check-site-catalog-convergence.py \
  --site-generated ../nabla-site-alban/lib/homelabCatalogIcons.generated.ts
```

Un digest identique ne confirme pas la disponibilité HTTP des services.
La vérification de l'accès OWNER doit utiliser
`/api/homelab-access?diagnose=1` et les routes protégées du site en Wi-Fi
autorisé. La vérification SERVICE doit être faite sur un réseau externe.
Ne pas contourner 401/403. Ne pas recopier de payload OWNER dans des tests.

### J.3 — Diagnostic Prometheus principal et exporter

```bash
sudo midclt call app.query | jq -r '.[] | select((.id // .name)=="prometheus") | [.id,.state] | @tsv'
sudo docker inspect prometheus --format '{{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}'
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
sudo bash scripts/truenas/repair-prometheus-config-access.sh --check
sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check
```

Le nom de conteneur `prometheus` est le **nom attendu**, pas une identité
garantie. Si `docker inspect` ne le trouve pas, examiner l'inventaire
Docker avec le filtre du projet Compose ; ne jamais choisir un sidecar au
hasard. Un échec n'autorise pas à changer UID 568 ou supprimer le WAL.

### J.4 — OpenRAG, LiteLLM, Docling, Langflow et secret canonique

```bash
sudo bash scripts/truenas/diagnose-openrag-dependencies.sh --check
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check openrag
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check akvorado
python3 scripts/check-service-migration-bundle.py --app openrag
```

Inventorier la présence et les permissions des fichiers **sans en lire
le contenu** :

```bash
sudo stat -c '%a %u:%g %n' /mnt/cpool/secrets/runtime/openrag/.env.secrets
sudo stat -c '%a %u:%g %n' /mnt/cpool/secrets/runtime/akvorado/.env.secrets
```

Si les fichiers sont absents, conserver `NOT_RUN` pour le contrôle de
matérialisation. Lire `config/secrets/manifest.json` et vérifier la présence
des noms requis dans Vaultwarden. Ne pas lancer l'ancien reconciler en
`--apply`. Tester l'indexation de **documents de test non sensibles**
après validation des dépendances ; OpenRAG `running` ne prouve pas l'ingestion.

### J.5 — Akvorado, NetFlow v5, ClickHouse et pfSense

```bash
python3 -m unittest discover -s tests -p 'test_akvorado*' -v
python3 scripts/truenas/diagnose-akvorado-flow.py --strict --fail-on-blocked --observe-seconds 30
python3 scripts/truenas/diagnose-akvorado-flow.py --strict --require-inserts --observe-seconds 30
docker compose -f apps/akvorado/compose.yml config --quiet --no-interpolate --no-env-resolution
```

Le code doit être au **HEAD fusionné** avant l'observation. Confirmer
le provider statique `172.17.0.1/32`, `ifIndex=11`, dans la configuration
chargée par Akvorado Outlet. Les compteurs de batch indiquent une activité,
pas nécessairement une ligne stockée. Lire les lignes datées ClickHouse
avec une requête limitée et une identité **lecture seule**, après avoir
identifié la table et les colonnes effectivement exposées par Akvorado.
Ne pas inventer de SQL ni modifier le volume de trafic pfSense.

### J.6 — Sondes LAN et couverture Gatus / Prometheus

```bash
sudo bash scripts/truenas/verify-fastapi-lan-probes.sh --check
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section lan
sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section observability
```

`HOMELAB_INTERNAL_PROBES_ENABLED` ne doit être activée **que dans le
collecteur LAN autorisé**, après contrôle SSRF. Une liste de 85 endpoints LAN
déclarés n'est pas une preuve : il faut `eligible`, `sampled` et
`completed` strictement positifs, avec horodatage. Le DTO OWNER publie
la provenance et la fraîcheur de chaque sonde ; le DTO SERVICE exclut
les adresses et informations sensibles.

### J.7 — Secrets première vague et migration unitaire

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
sudo bash scripts/truenas/accept-runtime-env-first-wave.sh --check all
python3 scripts/secrets/inventory_vaultwarden.py --json
```

Le dernier contrôle nécessite une session `bw` autorisée ; la sortie
complète peut contenir de la métadonnée privée et reste locale.
Vérifier successivement `scanopy`, `joplin`, `autokuma` et `code`.
Les transitions `--stage` et `--accept <service>` sont **mutantes**
et restent réservées à une intervention distincte après sauvegarde,
contrat Backstage, validation de secret et plan de rollback.
Ne pas lancer `--accept all`.

### J.8 — Talos/Kubernetes et qualité de la PR

Depuis la workstation avec `talosctl` et `kubectl` installés :

```bash
bash scripts/talos/validate-cluster.sh
python3 scripts/talos/preflight-supported-upgrade.py --check
bash scripts/talos/smoke-truenas-csi-nfs.sh --check
```

Depuis le checkout **de la PR #274**, sans publication ni déploiement :

```bash
just agent-skills-check
just catalog-convergence-check
just migration-20261024-test
python3 -m unittest discover -s tests -p 'test_akvorado*' -v
just quality
```

Aucune preuve de production ne doit être conclue sur un test local seul.
Le passage hors Draft et la fusion restent des décisions distinctes.

