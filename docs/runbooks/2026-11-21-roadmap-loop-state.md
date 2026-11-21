# Boucle roadmap du 21/11/2026 : état

Mode sprint homelab approuvé par le propriétaire le 21/11/2026 : appliquer,
redéployer et créer sans accord pas à pas, une PR par dépôt, questions après
cinq passes, cycle de réconciliation toutes les trois passes
([skill](../../.agents/skills/nabla-roadmap-loop/SKILL.md)).

| Dépôt | PR de consolidation |
|---|---|
| nabla-compose | [#430](https://github.com/AlbanAndrieu/nabla-compose/pull/430) |
| fastapi-sample | [#452](https://github.com/AlbanAndrieu/fastapi-sample/pull/452) |
| nabla-openclaw | [#26](https://github.com/AlbanAndrieu/nabla-openclaw/pull/26) |
| nabla-site-alban | aucune PR ouverte : branche créée au premier changement |

## Compteur

| Passe | Début | Fin | Réconciliation |
|---|---|---|---|
| 1 | 21/11 | en cours | après la passe 3 |

## Journal

| Item | Statut | Preuve |
|---|---|---|
| Consolidation dans #430 : Pi-hole, honeypot, mail des 20 zones, route Tunnel `login` | TESTED | branche `fix/cron-fastapi-cloud-gate-20261120` |

## Questions en attente

Reprises du [runbook du 20/11](2026-11-20-roadmap-pass-blockers.md), à poser
après la cinquième passe : Q1 (CrowdSec et Tunnel), Q2 (Watchtower), Q5
(`talosconfig` dans Vaultwarden), Q6 (secours DNS et préfixe IPv6).
