# Gouvernance d'architecture — décisions et dispatch inter-dépôts

> **Décision inter-dépôts acceptée (27 octobre 2026) :** [ADR-WKS-001 — workstation Option A](adr/adr-workstation-option-a.md). Roadmap de ce dépôt : [YubiKey et intégrations workstation](roadmap-workstation-yubikey.md). Aucun effet sur l'ADR APISIX.

**Propriétaire de ce registre :** nabla-compose (vue plateforme).
**Statut :** méthode validée par le propriétaire du homelab (25 octobre 2026).
L'ADR-0001 est accepté pour un **POC APISIX staging**, pas pour le cutover.
Ce processus est volontairement léger : les agents peuvent prendre des décisions
réversibles sans soumettre chaque refactoring à une revue humaine.

## Méthode légère : RFC → ADR → contrats → tâches → preuves

Les **ADR** (Architecture Decision Records, format Michael Nygard) enregistrent
le contexte, les options, la décision, ses conséquences et son statut.
Les **RFC** servent aux changements transverses contestables avant décision ;
le modèle **C4** fournit les vues contexte/conteneurs/composants/déploiement ;
la matrice **RACI** donne un responsable et un décideur **par livrable**.
Les modes Team Topologies (collaboration, X-as-a-Service, facilitation) limitent
les dépendances permanentes entre les dépôts.

Références :
- https://github.com/architecture-decision-record/architecture-decision-record
- https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decisions.html
- https://c4model.com/
- https://teamtopologies.com/key-concepts/

### Procédure fast-track (une action par étape)

1. **Décider directement** pour un changement réversible, limité à un dépôt,
   sans exposition nouvelle ni modification d'un contrat consommé.
2. **Écrire une note de décision courte** dans la PR : problème, choix,
   rollback. Un ADR n'est pas requis pour du style, du refactoring ou des tests.
3. **Créer un ADR en Compose** si une décision modifie au moins deux dépôts,
   le routage, la source d'autorité, une interface publiée ou les droits.
   Format cible : 15 à 30 lignes ; pas de réunion ni d'outil central additionnel.
4. **Accepter immédiatement** l'option par défaut documentée si elle est
   réversible et couverte par des tests ; l'agent enregistre son statut.
   Demander une décision humaine uniquement pour une migration irréversible
   ou le remplacement d'un chemin de production essentiel.
5. **Dispatcher les contrats** vers les dépôts propriétaires, avec un unique
   owner par livrable ; corriger le code dans la PR déjà ouverte si possible.
6. **Exécuter les vérifications disponibles** local-first et exact-SHA ;
   mentionner `NOT_RUN` sans transformer une Preview READY en preuve métier.
7. **Documenter le rollback** et les résultats dans l'ADR ou la PR.
   Garder les anciens ADRs et remplacer leur statut par `superseded`.

**SLA agent :** pas d'attente humaine pour un changement réversible en
staging ou documentation. Le formulaire ADR n'est **pas** une gate CI.
La revue d'architecture se fait dans la description de PR, pas au préalable.
Une nouvelle exposition publique ou un relâchement de l'autorisation nécessite
toujours des tests négatifs explicites, même pour un homelab.

### Routing des changements : matrice d'autorité

| Objet / changement | Accountable (décision technique) | Responsible (implémente) | Consulté / consommateur | Preuve obligatoire |
| --- | --- | --- | --- | --- |
| Source canonique Backstage, DNS, TLS, Traefik, APISIX, secrets infra | Compose | Compose | FastAPI, Site, sécurité | `--check`, L0/L1, rollback POC |
| DTO, schémas d'erreur, probes, codes, identité origine, FastAPI JWT | FastAPI | FastAPI | Compose, Site, sécurité | pytest, routes négatives, origine contrôlée |
| Affichage OWNER/SERVICE, cache client, accessibilité, Vercel | Site Alban | Site Alban | FastAPI, Compose | Node 24, tests d'accès, Preview exact-SHA |
| Authentification d'utilisateur / Keycloak futur | Compose infra + application pour autorisation | Compose IdP, FastAPI auth, Site session | sécurité | OIDC/JWKS, role, session, refus, fail-closed |
| Politique de confidentialité / modèle de menace | Revue sécurité/owner | chaque dépôt sur son boundary | trois mainteneurs | matrice d'accès et tests de non-divulgation |

Il s'agit d'une **RACI technique par livrable**, pas d'une attribution RH.
Le projet qui expose une route conserve sa décision d'autorisation : le
fait que Compose ait une gateway ne transfère pas la sécurité de FastAPI.

### Contrat de handoff dans chaque PR

Inclure systématiquement : `Decision/ADR ID`, producteur, consommateurs,
version/compatibilité du contrat, niveau de divulgation
PUBLIC/SERVICE/OWNER/INTERNAL, propriétaire de la route, SHA source,
preuves L0/L1/L2/L3 avec `NOT_RUN` explicite, dépendances, procédure
de retour arrière, critères `Done` et lien au runbook unique.

**Gate de gouvernance :** pas de merge si une autorisation publique
s'élargit implicitement, si des données OWNER deviennent SERVICE, si un
changement de schéma a perdu sa compatibilité sans cutover, ou si une
dépendance est marquée DONE sans validation sur l'environnement adéquat.

## Exemple appliqué — ADR-0001

[ADR-0001 — POC Apache APISIX](adr/0001-apisix-api-gateway-poc.md)
est **accepted pour staging**, sans autoriser une publication publique. Les responsabilités sont réparties ainsi :

- **Compose / PR #278 :** cataloguer Traefik/Cloudflare, décider du hostname
  privé, écrire le POC standalone sans etcd, règles réseau, secrets et rollback.
- **FastAPI / PR #376 :** classer toutes les routes, maintenir l'auth
  à l'origine, publier des codes de diagnostic expurgés, tester 401/403/503,
  préparer JWT/OIDC contract-first.
- **Site / PR #256 :** réutiliser le contrat de 503, cacher les données
  OWNER au premier rendu après une transition d'accès, afficher la référence
  uniquement pour OWNER, valider WCAG et confidentialité.
- **Gate transverse :** anonymes refusés, headers spoofés rejetés, identité
  workload vérifiée, pas de perte de télémétrie, rollback fonctionnel.
- **Keycloak :** explicitement différé. Ne pas le déclarer installé.

## Présentation C4 dans Site Alban

**Outil choisi :** `@xyflow/react` déjà présent dans Site Alban ;
aucun serveur Structurizr, iframe ou dépendance graphique nouvelle.
**Données :** topologie et `catalogRevision` existants, issus de Backstage
v2/FastAPI ; ce document reste la source de la décision et des responsabilités,
le Site est seul responsable du rendu interactif.

- L1 Contexte : acteurs et système Nabla (vue d'architecture déclarée).
- L2 Conteneurs/services : projection bornée des nœuds et relations connus
  de `ServiceTopology`, sans déduire un verdict runtime.
- L3 Composants : différé jusqu'à existence de relations `partOf`
  ou d'un contrat de composants explicites.
- Confidentialité : les vues publiques ne reçoivent que les données déjà
  autorisées du read-model, pas les URL ou preuves OWNER.

[Site #256](https://github.com/AlbanAndrieu/nabla-site-alban/pull/256)
assure le rendu C4 et ses tests. Ne pas stocker un deuxième inventaire
des nœuds C4 dans Compose. Structurizr DSL pourra être **exporté**
ultérieurement depuis le modèle canonique si un format portable est utile.

## Cadence de réconciliation

Une revue par PR transversale suffit pour un petit homelab. Assurer les liens
entre PRs et ADR ; la **roadmap active du dépôt reste autoritaire pour son
implémentation**. Le registre décide où dispatcher une nouvelle demande,
il ne duplique pas les tâches des autres roadmaps.
