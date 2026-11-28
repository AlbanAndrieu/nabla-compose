# Services Homelab — plan actif (28 novembre 2026)

> **Une seule source de backlog** : [portefeuille H01–H21](roadmap-portfolio.md). Cette page ne répète pas les 21 fiches : elle donne la prochaine action et la preuve de clôture. Les instructions sont dans [l'index des runbooks](runbooks/README.md), les décisions dans les ADR, les observations datées dans [le journal du 28/11](runbooks/2026-11-28-roadmap-loop-state.md) et les incidents dans `docs/incidents/`. Aucun statut live n'est déduit du contenu Git.

## Règles d'acceptation

`CODED` = versionné ; `TESTED` = tests associés à un SHA ; `DEPLOYED` = installation prouvée ; `ACCEPTED` = recette runtime indépendante, datée et réussie. `PARTIAL` et `NOT_VERIFIED` ne sont pas des succès. `DENIED`, `NOT_RUN`, `UNVERIFIED` ne prouvent jamais `DOWN`.

## Ordre opérateur et prochaine preuve

| Ordre | Chantier | Prochaine preuve / condition de clôture | Référence |
| --- | --- | --- | --- |
| 1 · P0 | **H17 — Backstage/catalogue V2** | Même `catalogRevision` et `entityRef` entre Compose, Sample TrueNAS et site Alban ; `sentry-edge` associé à une seule App ; suppression V1 après audit des lecteurs et rollback | [Recette H17](runbooks/h17-catalog-runtime-acceptance.md) |
| 2 · P0 | **H13 — CTEM / Dependency-Track** | Import d'un SBOM CycloneDX de test, sonde, métriques et refus anonyme ; Amass LAN/externe autorisé, revue avant DefectDojo ; ne pas exposer en WAN | [CTEM](runbooks/ctem-external-exposure.md) · [Dependency-Track](runbooks/ctem-dependency-track-acceptance.md) |
| 3 · P0 | **H05 — observabilité et qualité de preuve** | Vérifier les règles Gatus/Prometheus, fraîcheur et provenance, distinguer cibles `planned` de pannes avérées | [Triage](runbooks/homelab-runtime-acceptance.md) |
| parallèle · P1 | **H18 — EnOcean/Somfy** | Inventaire USB/passerelle et pilote lecture seule ; pas d'achat/réappairage avant compatibilité | [Étude](roadmap-homeassistant-integrations.md) |
| conditionnel | **H03/H04** | Secrets strictement nécessaires et vérification HTTPS/DNS/Access/Tunnel depuis une vantage indépendante | [Secrets](secrets-runtime-initialization.md) · [Ingress](dns-ingress-ownership.md) |
| différé | **H08 et H09–H21** | Reprendre uniquement les reliquats détaillés dans le portefeuille après arbitrage ; IPv6 Freebox/R7000 **en dernier** | [Portefeuille](roadmap-portfolio.md) |

## Acquis à ne pas rejouer sans régression démontrée

- **H01 CSI NFS/Cilium** : gate RWX multi-workers, reclaim, NetworkPolicy et Falco reçue le 21/11. Évolutions SPIRE et IAM suivies séparément.
- **H02 sauvegarde PostgreSQL** : neuf bases et trois restaurations isolées prouvées le 21/11. Rotation des identifiants et vérification de clients restant dans H03/H09.
- **pfSense retiré** au profit Freebox/R7000 depuis le 18/11 ; anciens runbooks pfSense = historique, pas procédure de production.
- **Vaultwarden 1.37.5** et adaptateur : dernière réception saine le 21/11. Les secrets Keycloak/Joplin/Homarr/postgres_exporter ont été matérialisés le 28/11, mais leur preuve ne clôt pas toutes les consommations applicatives.
- **Dependency-Track 5.2.0** : API et frontend déployés et contrôlés le 25/11 ; import SBOM de bout en bout encore ouvert.
- **Nexus 3.92.3** : caches APT/npm/PyPI déployés le 27/11 ; restent HTTPS privé, clients et restauration préalable à upgrade.
- **ZFS** : doublons de snapshots ciblés traités le 28/11 ; garder dans le [journal](runbooks/2026-11-28-roadmap-loop-state.md) les détails et décisions résiduelles.

## Discipline de réconciliation

1. Modifier **la ligne Hxx du portefeuille** pour statut, propriétaire, blocage et preuve ; ne pas dupliquer le backlog dans des runbooks ou les agents.
2. Actualiser ce plan seulement quand **l'ordre des priorités change** ; une correction de script n'implique pas une nouvelle page de roadmap.
3. Déplacer les comptes rendus terminés vers `archive/` ou `incidents/` uniquement après validation des liens et du maintien des procédures de restauration. Ne jamais effacer les preuves d'acceptation.
4. Mettre à jour le runbook canonique seulement si la procédure, la commande de contrôle ou le rollback change.
5. Pour `site-support` v8 (PR #461), tests de prompt et évaluation live restent distincts : l'acceptation des citations RAG exige une preuve sur les réponses du site ; ne pas transformer le taux faible de citations en statut « terminé ».

Voir aussi : [gouvernance documentaire](README.md), [instructions agents](../AGENTS.md), [journal d'exécution](runbooks/2026-11-28-roadmap-loop-state.md).
