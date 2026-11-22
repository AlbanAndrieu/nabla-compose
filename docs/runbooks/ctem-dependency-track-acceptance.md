# CTEM / Dependency-Track — réception prioritaire H13

> Arbitrage 22/11/2026 : **Dependency-Track est prioritaire avec les outils CTEM**, distinct du lot H08 Nexus/Joplin différé. Owner infrastructure : `nabla-compose`. Pas d'exposition WAN, aucune migration v4→v5 implicite.

## Contrats avant une première installation

- Définition : `apps/dependency-track/compose.yml` (frontend LAN :31084, API LAN :31083), PostgreSQL partagé `dependencytrack`, secret de runtime `/mnt/cpool/secrets/runtime/dependency-track/.env.secrets` en `root:root 0600` et Gatus après déploiement. En **v5**, `DT_METRICS_ENABLED=true` expose `/metrics` sur le **serveur de gestion :9000**, pas sur l'API :8080 ; Prometheus scrute `dependency-track-api:9000` par DNS Docker privé (`intranet`), **sans publication du port de gestion sur le LAN**.
- **Épinglage et compatibilité CODED dans la PR #437** : les deux images sont désormais fixées sans substitution à `ghcr.io/dependencytrack/{apiserver,frontend}:5.2.0`, plutôt que `latest` (qui peut encore référencer v4). Le service API utilise `DT_DATASOURCE_URL` et `DT_DATASOURCE_USERNAME` (v5), le CA PostgreSQL montée en lecture seule et `sslmode=verify-full`. Le secret runtime attend `DT_DATASOURCE_PASSWORD`, **réutilisant sans rotation** le champ Vaultwarden historique `ALPINE_DATABASE_PASSWORD` via le manifeste ; le bootstrap PostgreSQL et ses tests utilisent le nouveau nom. Le certificat doit couvrir `172.17.0.24` dans son SAN ou il faut paramétrer un nom DNS vérifiable. **Code préparé, pas une preuve que v5 démarre sur TrueNAS.**
- S'il existe une base v4 avec des données, exiger **l'outil de migration hors-ligne** dédié + snapshot validé, jamais une simple substitution d'image. Si App absente et base vide, privilégier une première installation fraîche.
- Le TLS PostgreSQL doit être contrôlé côté client (CA/SAN/hostname, `verify-full` si pris en charge par la configuration JDBC), pas seulement par `hostssl` côté serveur.

Sources fournisseur : https://dependencytrack.github.io/docs/next/reference/container-images/ et https://dependencytrack.github.io/docs/next/guides/administration/configuring-database/ .

## Séquence déjà versionnée sur TrueNAS

```bash
cd /mnt/cpool/compose/nabla-compose
bash scripts/truenas/rollout-pending-apps.sh --plan dependency-track
sudo bash scripts/truenas/prepare-security-tooling-secrets.sh --check dependency-track
sudo bash scripts/truenas/bootstrap-app-postgres.sh --check dependency-track
sudo bash scripts/truenas/rollout-pending-apps.sh --check dependency-track
```

La configuration **Git** n'autorise plus d'image flottante et les contrôles existants vérifient le secret et la présence du rôle PostgreSQL. **Attention** : le `--check` ne prouve pas à lui seul qu'une base historique v4 est vide, que le SAN est correct ou que l'API v5 fonctionne ; consigner ces points comme **bloquants manuels** jusqu'à un smoke runtime. Ne pas transformer une absence de recette en `DOWN`.

Après revue du plan, si toutes les portes sont vertes, le déploiement est **unitaire et réversible** : la commande de mutation préparée par le script `--plan` est `NABLA_RUNTIME_CHANGE_APPROVED=yes ... --apply dependency-track`, puis observer la DB, la sauvegarde du rôle et l'état App. **Cette étape est NOT_RUN depuis l'environnement distant.**

## Recette fonctionnelle

1. `app.query` : `dependency-track` RUNNING et ses deux conteneurs stables, sans redémarrage ; aucune route Cloudflare, aucun port ouvert sur le WAN.
2. `curl --fail-with-body http://172.17.0.24:31084/` : interface LAN disponible ; API LAN `http://172.17.0.24:31083` avec endpoint de santé supporté par la **version déployée** ; `401/403` attendu sur une API exigeant une clé.
3. Gatus : date/heure, cible, statut. Prometheus : `up{job="dependency_track"} == 1` et séries d'application réelles ; `up=1` ne prouve pas que l'import fonctionne.
4. Depuis un opérateur autorisé, importer **un CycloneDX volontaire de test** vers un projet de laboratoire par API avec clé limitée, puis confirmer le composant, la version, la date de traitement et la déduplication d'un second import identique.
5. Révoquer/retirer le projet de test suivant la politique de rétention, sans purge globale. Confirmer qu'une requête sans autorisation échoue. Protéger les secrets d'import et les noms privés.

## Articulation des outils CTEM

- **Amass** : candidats et DNS avec provenance LAN/externe, périmètre approuvé, sortie privée ; aucune création automatique de vulnérabilité.
- **Dependency-Track** : SBOM et vulnérabilités de composants effectivement déclarés/provenant d'artefacts vérifiés.
- **Prowler / Cartography / Neo4j / OASM** : preuves de configuration cloud et graphe, sans substituer ces bases au catalogue `entityRef`.
- **DefectDojo** : consolidation de findings qualifiés et validés (traces, source, sévérité, suppression des doublons), imports privés uniquement.
- **FastAPI Sample** : affiche provenance/fraîcheur/statut, ne reçoit jamais un token d'administration de Dependency-Track dans sa réponse publique.

**ACCEPTED seulement après** : tests API/SBOM, métriques, secret et TLS, refus anonyme, non-exposition WAN et sauvegarde/restauration documentés avec SHA et heure ; sinon `CODED / NOT_VERIFIED`.
