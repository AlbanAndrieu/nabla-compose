# Sept migrations — portefeuille d'exécution sécurisé (18 octobre 2026)

**Portée : préparation GitOps et contrats hors ligne, pas de déploiement.**
La source d'autorité reste [roadmap.md](roadmap.md). Le manifeste
[workstreams.json](../config/migrations/workstreams.json) reflète la **préparation**
et ne devient ni catalogue v2, ni inventaire runtime, ni magasin de secrets.
Tous les résultats de ce lot sont `repository_ready` ou `runtime_observed` :
**aucune recette live ni sauvegarde/restauration ne peut être déduite du code**.

## Contrat commun

- Aucun accès à une API d'administration TrueNAS/pfSense/Cloudflare, aucune
  rotation, suppression ZFS, purge, réindexation, création de compte ou restart.
- Déploiement, puis recette *une application à la fois* ; source, dépendances,
  identités, environnement, stockage, monitoring et rollback explicites.
- Secrets exclusivement matérialisés côté opérateur : `Vaultwarden` comme
  source transitoire, `/mnt/cpool/secrets/runtime/<service>/.env.secrets`
  en permissions root-only ; jamais en Git, argument CLI ou sortie CI.
- Les dépendances externes injoignables valent **UNKNOWN**, pas `DOWN`.
  Une sonde HTTP 302/403 Access vaut preuve de frontière, pas de santé origine.
- Une merge PR vaut livraison source uniquement. L'acceptation runtime exige
  les tests d'API, stockage, authentification et rollback datés ; l'acceptation
  reboot exige également le redémarrage sans perte fonctionnelle.

## Ordre proposé et critères vérifiables

| Priorité | Chantier | Préparation existante | Recette encore requise |
| --- | --- | --- | --- |
| P0 | Secrets runtime / Vaultwarden | `config/secrets/manifest.json`, migration `--stage`/acceptation par service | Secret staging byte-identique, permissions, Compose, smoke et reprise |
| P1 | DefectDojo | Compose existant, diagnostic LAN et importeur fail-closed | DNS/TLS privé, API authentifiée, worker/DB, import synthétique isolé, déduplication |
| P1 | Catalogue v1 → Backstage v2 | Descripteurs + tests parité, `x-nabla` transitoire | IDs/relations/85 sondes et trois consommateurs strictement équivalents |
| P1 | OpenClaw → LiteLLM embeddings | Préflight SecretRef, sauvegardes SQLite, alias `embedding` | SecretRef réellement résolu, budget, restore isolé, index *fresh* par agent |
| P1 | OpenRAG / Docling / Bababou | `/mnt/cpool/bababou` → `/mnt/bababou:ro` déclaré | Traverse UID/ACL, Docling conversion, ingestion puis retrieval pertinent |
| P1 | Observabilité Gatus/Prometheus/FastAPI | Réconciliateur et diagnostics en lecture seule | 85 moniteurs, 25 négatifs triés, `up`/lastError, origines indépendantes |
| P2 | FreshRSS GitOps / MCP | Ops API GReader, OPML et MCP stdio read-only | Deux comptes séparés, dix flux autorisés, tokens distincts et test périodique |

### P0 — Secrets et identité

Commencer par **Scanopy, AutoKuma et Joplin** ; préserver les secrets
d'encryption de Sentry/ClickHouse et les autres clés liées aux données.
Un même lot associe la matérialisation `env_file` et le descripteur
`apps/<service>/catalog-info.yaml`, sans supprimer les sources héritées.
Voir [la procédure canonique](secrets-migration-roadmap.md). Vaultwarden bootstrap
reste isolé des secrets applicatifs.

### P1 — DefectDojo LAN, sans exposition

Les dernières observations démontrent les processus RUNNING et le DNS privé,
**pas** l'authentification, l'état Celery et un import accepté. Les contrats
`preflight-defectdojo.sh`, `diagnose-defectdojo.sh` et
`scripts/security/import-scan-defectdojo.sh` existent. L'import doit cibler
l'origine LAN autorisée, protéger le jeton, viser un produit/engagement
de test et confirmer la déduplication avant tout planificateur.

### P1 — Cutover catalogue v2

Réconcilier les IDs, URLs/aliases, `expectedRunning`, `deploymentUnitId`,
conditions Gatus, rangs `probePriority` et relations. Préparer d'abord des
descripteurs Backstage et les projections v2 ; **pas de suppression**
de `catalog/homelab-services.json` jusqu'à la parité démontrée pour
FastAPI, site Alban, Homarr/Gatus/AutoKuma. Le cutover final est coordonné
et ne maintient pas deux autorités pérennes.

### P1 — Embeddings OpenClaw et Bababou

Un alias `embedding` OpenAI-compatible ne garantit pas la même famille
de vecteurs. Isoler `main`/`cron` et leurs backups, confirmer le
fingerprint modèle/dimensions, clé LiteLLM dédiée et budget non illimité.
Ne pas rejouer les 617 fichiers mémoire sans index-source guard.
Pour Bababou, le **dataset est `cpool/bababou`**, monté à
`/mnt/bababou` *en lecture seule*. Vérifier le montage effectivement
présent, les ACL de traversée, le parsing Docling, la provenance des documents
et une requête de retrieval sur un échantillon non sensible.
Aucun contenu privé du dataset ne doit aller en CI/GitHub.

### P1 — Corrélation de sondes

Gatus doit être évalué par identité, statut attendu et historique de
redémarrages ; distinguer `not_observed`, `disabled`, `probe_error`,
`dependency_unavailable` et `service_down` **avec preuve**.
Prometheus `up=0` ne prouve pas une panne FastAPI ; vérifier le
`lastError`, le port et `/metrics` puis `/health` indépendamment.
Rester en lecture seule pour qualifier le dernier baseline 60/85.

### P2 — FreshRSS

Préserver les dix sources publiques allowlistées et les identités
`securitypublic` (site serveur) et `securityagent` (MCP local).
ClientLogin retourne un token limité, exclusivement via canal protégé.
MCP stdio, outils de lecture seulement, pas de connecteur extérieur
ou de proxy public vers les articles privés. Les comptes/API sont activés
uniquement lors d'une recette contrôlée.

## Quality gate locale, sans homelab

```bash
python3 scripts/security/check-migration-readiness.py --check --json
python3 -m unittest tests.test_migration_readiness_contract -v
```

Le script ne lit que le manifeste et la **présence des chemins versionnés**.
Il vérifie dépendances acycliques, périmètre fixe et interdiction de déclarer
une recette live sans preuve. Il **ne sonde aucun service**, ne lit aucun
`.env` et n'ouvre aucun socket. Il doit échouer si le contrat est incomplet.
La quality gate générale et les contrôles SAST/SCA existants restent
indépendants et obligatoires avant merge.

## Handoff

Prochaine séquence sans accès administratif : renforcer les tests contractuels
existants de migration de secrets, DefectDojo, catalogue, OpenClaw, OpenRAG,
sondes et MCP FreshRSS ; tenir les statuts `NOT_RUN` explicitement.
Tout état `runtime_accepted` ou `reboot_accepted` doit être
enregistré dans les runbooks après exécution réelle, jamais par un
changement de case dans ce manifeste.
