# Nabla Compose — Services Homelab

Infrastructure déclarative pour les applications TrueNAS SCALE, le cluster
Talos/Kubernetes et les services de sécurité, d'observabilité et d'IA.

> Ce dépôt contient des configurations et scripts capables de changer
> l'état d'une infrastructure privée. **Ne pas exécuter un
> `docker compose up`, une migration de secret, un reset d'index ou un
> redémarrage global depuis ce README.** Les opérations mutantes
> exigent une validation explicite, une sauvegarde et un rollback.

## Démarrage : lecture seule

1. Lire [`AGENTS.md`](AGENTS.md) pour les règles de contribution, les
   instructions locales et les limites d'accès à TrueNAS.
2. Consulter la [roadmap active](docs/roadmap.md) pour les priorités et
   les critères d'acceptation.
3. Utiliser l'[index des runbooks](docs/runbooks/README.md)
   pour sélectionner une procédure ciblée.
4. Se référer au
   [skill local-first](.agents/skills/local-first-quality/SKILL.md)
   avant un changement de code.

## Architecture et responsabilités

| Source | Responsabilité |
| --- | --- |
| `apps/<service>/compose.yml` et `x-nabla` | Service, dépendances et exposition souhaitées |
| `catalog/` et `catalog-info.yaml` | Identités Backstage et projections générées |
| `scripts/truenas/` | Diagnostics et opérations contrôlées sur TrueNAS |
| `scripts/talos/` | Déploiement et contrôles Talos/Kubernetes |
| `scripts/pfsense/` | Diagnostics et politique réseau pfSense |
| `docs/roadmap.md` | Actions non terminées, priorités, gates runtime |
| `docs/runbooks/` | Procédures ciblées et preuves opérateur |

Données : les datasets `/mnt/cpool/` et les secrets
`/mnt/cpool/secrets/runtime/` ne sont pas recréés ni modifiés
implicitement par les contrôles read-only. Le catalogue déclaratif ne
représente pas un relevé de l'état réel des services.

La collecte runtime relève de `fastapi-sample` ;
la présentation des services relève de `nabla-site-alban`.
Ne pas copier leurs responsabilités dans ce dépôt.

## Contribution et qualité

Sur une branche de travail **non protégée**, utiliser un worktree isolé
et une `.venv` verrouillée par worktree. Le cache `uv` peut être partagé.
Ne pas charger automatiquement `.envrc` ni installer de dépendances
dans le Python de TrueNAS.

```bash
just agent-skills-check
```

Pour des contrôles de compatibilité rapides avec **Node 22 / npm 10**
sans dépendance installée ni crédit CI, utiliser :

```bash
just node22-fast
```

Ce contrôle valide des contrats statiques et la syntaxe Bash.
Il ne remplace pas les tests Python ni le smoke Docker.
La version canonique du projet reste Node 24 ; consulter
[le runbook du mode rapide](docs/runbooks/node22-local-fast-tests.md).

Puis, dans la même révision après les tests ciblés :

```bash
just quality
```

Ces commandes s'exécutent **séparément** sur un worktree de développement,
et non dans le checkout canonique TrueNAS. Préférer une PR Draft,
des commits `[skip ci]` et les gates locales avant toute CI distante.
La gate complète doit être exécutée sur le **HEAD exact** publié.

## Historique

L'ancien README comportait des commandes manuelles de création de
sous-modules, `docker compose up`, arrêt de services systemd et
installation Sentry qui ne sont **pas** adaptées à une reprise sécurisée
de cette infrastructure. Son contenu est conservé **à l'identique**
dans l'[archive historique](docs/archive/README-legacy-compose-notes.md)
pour traçabilité et n'est pas un runbook actif.
