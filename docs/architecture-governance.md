# Gouvernance d'architecture — décisions et dispatch inter-dépôts

**Propriétaire de ce registre :** nabla-compose (vue plateforme).
**Statut :** procédure proposée en Draft PR #278. Ce document ne constitue
ni une approbation de déploiement ni un changement de politique d'accès.

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

### Procédure (une opération par étape)

1. **Identifier le changement.** Décrire le problème et le risque sans
   prescrire immédiatement un outil.
2. **Classifier le périmètre.** Si plusieurs dépôts, une API, une identité,
   un ingress ou une donnée sensible changent, ouvrir une proposition
   RFC/ADR dans le registre Compose.
3. **Désigner la source d'autorité.** Assigner UN dépôt producteur du contrat.
4. **Comparer les options.** Noter coût de fonctionnement, sécurité,
   migration, rollback et critères d'échec.
5. **Faire la revue.** Inclure les dépôts consommateurs et la sécurité ;
   un Draft n'équivaut pas à un ADR accepté.
6. **Répartir le travail.** Chaque dépôt reçoit ses propres tâches et ses
   propres tests d'acceptation. Aucun copier-coller de roadmap actif.
7. **Valider les frontières.** Tests de contrat négatifs/positifs et
   preuve du HEAD exact, local-first sans CI payante.
8. **Livrer progressivement.** Publication et activation séparées, avec
   compatibilité, feature flags et rollback.
9. **Enregistrer la décision.** Status `proposed → accepted → superseded`,
   conserver l'historique au lieu de modifier rétroactivement un ADR accepté.

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

[Proposition de POC Apache APISIX](adr/0001-apisix-api-gateway-poc.md)
est **proposed**. Les responsabilités sont réparties ainsi :

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

## Cadence de réconciliation

Une revue par PR transversale suffit pour un petit homelab. Assurer les liens
entre PRs et ADR ; la **roadmap active du dépôt reste autoritaire pour son
implémentation**. Le registre décide où dispatcher une nouvelle demande,
il ne duplique pas les tâches des autres roadmaps.
