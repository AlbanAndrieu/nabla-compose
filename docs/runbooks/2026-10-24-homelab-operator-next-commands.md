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
`fastapi-sample` modifié comme sous-module. Les PR #273, site #254 et FastAPI
#373 restent Draft. **Ne pas appliquer une branche Draft à TrueNAS.**

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
pas été réellement exécutée sur le HEAD exact. Les PR Compose #273,
FastAPI #373 et Site #254 restent Draft jusqu'à validation et décision
de mise en production. Les skills externes ne s'installent qu'après
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
