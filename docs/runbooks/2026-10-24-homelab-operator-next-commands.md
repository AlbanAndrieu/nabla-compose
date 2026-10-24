# Homelab — commandes opérateur restantes (2026-10-24)

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

## Étape A — checkout opérateur TrueNAS et réseau Git (pré-requis)

Le 24 octobre, un checkout TrueNAS a été observé en retard sur GitHub, avec
`fastapi-sample` modifié comme sous-module. La PR Compose #273 reste Draft. Les PR site #254 et FastAPI
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

Après installation des scripts de la PR Compose #273 sur le checkout opérateur
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

**Dette identifiée :** le réconciliateur OpenRAG/OpenSearch compare encore
`/mnt/cpool/openrag/.env.secrets` à
`apps/opensearch/.env`. Ces chemins sont des sources historiques, pas
le stockage cible. Avant tout `--apply`, aligner le contrat sur Vaultwarden
et les copies `/mnt/cpool/secrets/runtime/<service>/`. Ne pas imprimer de
mot de passe, ni recopier une clé dans la documentation.

Le résultat d'OpenRAG doit prouver backend et frontend `running+healthy`,
Langflow et OpenSearch disponibles. La disponibilité Docling,
des embeddings LiteLLM workstation et de l'ingestion doit être validée
séparément ; un conteneur sain ne prouve pas l'indexation des documents.

## Étape E — Akvorado / pfSense : rejet des flux NetFlow v5

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
pas été réellement exécutée sur le HEAD exact. La PR Compose #273 reste Draft. Les PR FastAPI #373 et Site #254 sont
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
non revus. La PR #273 est encore Draft ; les scripts de cette branche ne sont
pas tous disponibles sur `master`. Le résultat `git status` peut contenir
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

Depuis le checkout **de la PR #273**, sans publication ni déploiement :

```bash
just agent-skills-check
just catalog-convergence-check
just migration-20261024-test
python3 -m unittest discover -s tests -p 'test_akvorado*' -v
just quality
```

Aucune preuve de production ne doit être conclue sur un test local seul.
Le passage hors Draft et la fusion restent des décisions distinctes.

