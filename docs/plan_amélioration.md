# Plan approfondi d'amélioration - nabla-compose

> Ce plan est issu d’un audit global du projet. Il priorise les axes d’amélioration par impact et détaille les actions concrètes à mener.

> La roadmap opérationnelle consolidée pour la migration des anciennes applications TrueNAS, des secrets et de l'identité est maintenant maintenue dans [`docs/homelab-platform-migration-roadmap.md`](./homelab-platform-migration-roadmap.md).

## Table des matières
- [1. Gestion des secrets](#1-gestion-des-secrets)
- [2. Fichiers d'environnement](#2-fichiers-denvironnement)
- [3. Réseau et sécurité](#3-réseau-et-sécurité)
- [4. Monitoring et logs](#4-monitoring-et-logs)
- [5. Healthchecks](#5-healthchecks)
- [6. Modularité et volumes](#6-modularité-et-volumes)
- [7. Labels Traefik et Prometheus](#7-labels-traefik-et-prometheus)
- [8. CI/CD et tests automatiques](#8-cicd-et-tests-automatiques)
- [9. Permissions et montages](#9-permissions-et-montages)
- [10. Actions prioritaires (par impact)](#10-actions-prioritaires-par-impact)

---

## 1. Gestion des secrets
- Centraliser la gestion des secrets (utiliser `secrets:` Docker Compose partout).
- Stocker secrets dans un gestionnaire (Vaultwarden, Hashicorp Vault) ou des fichiers sécurisés.
- Utiliser des montages read-only pour les secrets.

## 2. Fichiers d'environnement
- Factoriser fichiers `env_file` pour éviter la redondance.
- Documenter chaque variable par service.
- Générer des exemples `.env` pour nouveaux utilisateurs.

## 3. Réseau et sécurité
- Uniformiser l’usage du réseau `intranet`.
- Restreindre les ports à localhost où possible (`127.0.0.1:<port>`).
- Ajouter et documenter des règles Traefik pour les APIs/admin.

### Topologie autoritative de l’ingress direct

Le namespace `*.int.albandrieu.com` est privé par défaut (LAN/VPN) et ne doit
pas être publié dans le DNS public Cloudflare. Les rares exceptions historiques
d'ingress direct doivent être explicites, temporaires et suivies comme dette de
sécurité.

Chemin privé normal :

`LAN/VPN -> DNS interne -> Traefik :443 sur TrueNAS -> service Docker`

Chemin public direct, uniquement pour une exception déclarée :

`Internet -> DNS public non-.int (ou exception legacy) -> pfSense -> HAProxy -> Traefik :443 -> service Docker`

État et suivi :

- [x] déclarer Traefik en `x-nabla` comme reverse proxy Docker hébergé sur TrueNAS ;
- [x] déclarer Garage S3 et Garage WebUI en `x-nabla`, avec leurs relations `exposedBy` vers Traefik ;
- [x] ajouter un nœud logique `pfsense-haproxy` à la topologie autoritative ;
- [x] documenter la preuve TLS observée : HAProxy termine TLS sur le WAN `:443`, puis ré-établit TLS vers `172.17.0.24:443` avec `ssl verify none` avant Traefik ;
- [x] rendre explicites les ports backend Traefik Garage S3 `3900` et Garage WebUI `3909` ;
- [ ] ajouter à terme une vérification read-only de dérive entre la topologie déclarée et la configuration HAProxy pfSense observée par API/export généré ;
- [ ] distinguer dans les consommateurs les relations de dépendance fonctionnelle des chemins d’exposition (`HAProxy`, `Traefik`, `Cloudflare Tunnel`, DNS-only, LAN/VPN-only).

Les métadonnées `x-nabla` restent déclaratives : elles ne modifient ni l’ordre de démarrage Docker Compose ni le routage runtime.

## 4. Monitoring et logs
- Généraliser le driver de logs `json-file` + options de rotation (`max-size`, `max-file`).
- Monter les logs critiques en read-only.
- Activer les métriques Prometheus sur tous les endpoints compatibles.

## 5. Healthchecks
- Ajouter systématiquement des healthchecks sur les services critiques.
- Utiliser des tests HTTP, commandes ou socket pour vérifier l’état.

## 6. Modularité et volumes
- Harmoniser et externaliser les volumes partagés (`/mnt/cpool/`).
- Documenter la fonction de chaque volume.
- Grouper les volumes par usage (ex : tous les volumes data / code / configs).

## 7. Labels Traefik et Prometheus
- Synchroniser les labels Traefik sur tous les services exposés.
- Standardiser la configuration Prometheus pour chaque micro-service.
- Documenter la structure de l’intranet et des sous-domaines.

## 8. CI/CD et tests automatiques
- Ajouter des checks de sécurité (grype, trivy), de bonnes pratiques Docker et tests qualité dans `.gitlab-ci.yml`.
- Vérifier que tous les fragments Compose sont valides (`docker compose config`).
- Renforcer les hooks pre-commit.

## 9. Permissions et montages
- Monter tous les secrets et données sensibles en read-only.
- Vérifier les permissions des volumes data.

---

## 10. Actions prioritaires (par impact)

### Améliorations peu impactantes (à faire en premier)
- Harmoniser les labels Traefik et Prometheus sur les fragments Compose (ajout/correction).
- Ajouter des healthchecks de base (HTTP ou commande simple) sur les services critiques.
- Sécuriser les montages des secrets en read-only.
- Documenter et factoriser les variables d’environnement.

### Améliorations intermédiaires
- Uniformiser l’ajout des services au réseau `intranet`.
- Centraliser la gestion des logs et ajouter log rotation.
- Factoriser les volumes partagés.
- Mettre à jour les scripts automation pour valider les configs.

### Améliorations structurantes
- Migrer la gestion des secrets vers Docker secrets ou un gestionnaire tiers.
- Réviser l’arborescence des volumes et configs.
- Refondre la documentation des fragments Compose.
- Ajouter des outils CI/CD avancés (Grype, Trivy, reload automatique des fragments).

---

> Ce plan doit être suivi, en commençant par les actions les moins disruptives pour garantir la stabilité des déploiements. Chaque changement sera justifié et documenté.

---
