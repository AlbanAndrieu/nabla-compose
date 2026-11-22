# CTEM / Dependency-Track — réception prioritaire H13

> Arbitrage 22/11/2026 : **Dependency-Track est prioritaire avec les outils CTEM**, distinct du lot H08 Nexus/Joplin différé. Owner infrastructure : `nabla-compose`. Pas d'exposition WAN, aucune migration v4→v5 implicite.

## Contrats avant une première installation

- Définition : `apps/dependency-track/compose.yml` (frontend LAN :31084, API LAN :31083), PostgreSQL partagé `dependencytrack`, secret de runtime `/mnt/cpool/secrets/runtime/dependency-track/.env.secrets` en `root:root 0600`, Prometheus job `dependency_track` et Gatus après déploiement.
- **Épinglage obligatoire des deux images** : les valeurs `latest` sont **interdites pour une nouvelle recette** ; le tag `latest` sur Docker Hub peut encore référencer v4 pendant sa fin de vie, tandis que v5 est une migration de plateforme. Vérifier et épingler une version stable `X.Y.Z` identique entre frontend et API (version consultée 22/11 : 5.2.0) puis recetter les propriétés/variables propres à v5, avec gestion de TLS PostgreSQL et des secrets. Ne pas confondre les anciennes variables `ALPINE_*` et les propriétés `DT_*` de v5 ; **aucun démarrage sans revue de ces différences**.
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

Le `--check` doit **échouer fermé** si l'image est flottante, si le secret manque, si une base existante n'a pas de chemin de migration ou si le client ne valide pas la CA PostgreSQL. Ne pas transformer ces blocages en `DOWN`.

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
