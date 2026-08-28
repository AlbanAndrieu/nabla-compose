# Plan approfondi d'amélioration - nabla-compose

> La roadmap consolidée et priorisée est désormais [`docs/homelab-platform-migration-roadmap.md`](homelab-platform-migration-roadmap.md). Ce fichier conserve les axes historiques, mais la roadmap consolidée fait foi pour l'ordre d'exécution.

## Priorité actuelle

La gestion des secrets est **P0** et précède les nouvelles migrations d'applications TrueNAS natives.

Avant qu'un service contenant des mots de passe, API keys, clés de chiffrement ou secrets OAuth passe en `compose-ready` :

1. inventorier ses variables sans stocker leur valeur dans Git ;
2. ajouter leurs références dans `config/secrets/bitwarden-map.json` ou documenter explicitement leur statut de bootstrap secret ;
3. valider le manifest avec `python scripts/validate_secret_manifest.py` ;
4. migrer/récupérer les valeurs via Vaultwarden et le CLI officiel Bitwarden `bw` ;
5. préserver les clés de chiffrement pendant le cutover quand une rotation casserait les données existantes ;
6. supprimer l'ancien export shell ou `.env` seulement après validation du nouveau chemin.

La trajectoire cible est :

`exports shell/gitcrypt -> Vaultwarden + bw -> Keycloak OIDC -> HashiCorp Vault`

## Axes historiques

### Gestion des secrets

- Centraliser les secrets dans Vaultwarden en première étape.
- Utiliser `bw` pour les opérations humaines et le bridge `bitwarden-api` uniquement pour l'automatisation Doco-CD qui en dépend.
- Garder les bootstrap secrets minimaux hors Git dans des fichiers root-only `0600`.
- Migrer ensuite vers HashiCorp Vault KV v2 avec politiques et authentification adaptées aux workloads.

### Fichiers d'environnement

- Ne pas considérer les `.env` persistants comme source de vérité des secrets.
- Les `.env` générés depuis un gestionnaire de secrets doivent être éphémères, `0600` et hors du working tree.
- Documenter chaque variable non secrète et chaque référence secrète par service.

### Réseau et sécurité

- Uniformiser l'usage du réseau `intranet` lorsque pertinent.
- Restreindre les ports à localhost ou aux réseaux nécessaires.
- Ne jamais publier Docker socket/docker-socket-proxy sur Internet.

### Monitoring et logs

- Généraliser la rotation des logs.
- Maintenir les métriques Prometheus sur les services compatibles.
- Utiliser les endpoints FastAPI Sample documentés dans le skill `homelab-runtime-status` pour distinguer runtime, santé et exposition.

### Healthchecks

- Ajouter des healthchecks fonctionnels aux services critiques.
- Ne pas déduire qu'un service est fonctionnel uniquement parce que son conteneur est `RUNNING`.

### Modularité et volumes

- Migrer les ixVolumes TrueNAS vers des datasets explicites sous `/mnt/cpool/<service>`.
- Séparer les sous-datasets lorsque les composants ont des cycles de sauvegarde différents.

### CI/CD et tests automatiques

- Maintenir Compose Validate, Pre-commit, MegaLinter et Service Consumers.
- Valider automatiquement le manifest de références de secrets sans donner à CI accès à Vaultwarden.
- Continuer Gitleaks/Trivy/secret scanning pour empêcher la réintroduction de valeurs sensibles.

### Permissions et montages

- Utiliser les UID/GID attendus par les applications migrées.
- Restreindre les fichiers temporaires contenant des secrets à `0600`.
- Monter les secrets en fichier read-only lorsque l'application le supporte.

## Ordre d'exécution

1. P0 secrets Vaultwarden/Bitwarden CLI et inventaire.
2. P1 observation runtime Docker Compose dans FastAPI Sample.
3. Migration des applications TrueNAS natives vers Compose + `/mnt/cpool`.
4. Validation de NPMplus avant migration Nginx Proxy Manager.
5. Keycloak comme IdP avec GitHub comme broker d'identité.
6. HashiCorp Vault comme gestionnaire de secrets machine/humain à long terme.

Voir [`docs/homelab-platform-migration-roadmap.md`](homelab-platform-migration-roadmap.md) pour les critères de cutover et l'ordre détaillé des services.
