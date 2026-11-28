# Documentation — carte canonique

Lisez **uniquement le document correspondant à la tâche** : ne préchargez pas tout `docs/`. Les informations actives, les procédures, les décisions et les preuves ont des propriétaires distincts.

| Question | Source d'autorité |
| --- | --- |
| Quel travail prioriser ? | [Portefeuille H01–H21](roadmap-portfolio.md) |
| Quel est le prochain gate ? | [Plan actif](roadmap.md) |
| Comment diagnostiquer ou intervenir ? | [Index des runbooks](runbooks/README.md) |
| Quelles règles pour l'agent ? | [AGENTS.md](../AGENTS.md), puis [playbook à la demande](agent-execution-playbook.md) |
| Quelle architecture ? | [Topologie](homelab-network-topology.md), [DNS/ingress](dns-ingress-ownership.md), [Talos/TrueNAS](truenas-talos-bootstrap.md), [architecture de sécurité](security-tooling-control-architecture.md) |
| Quel contrat de catalogue ? | [Normalisation V2](service-catalog-v2-normalization.md), [consommateurs](service-catalog-consumers.md) |
| Quelles contraintes de sécurité ? | [Secrets runtime](secrets-runtime-initialization.md), [accès privé](private-homelab-access-architecture.md), [CTEM](adr/0004-ctem.md) |
| Quelle preuve historique ? | [Journal 28/11](runbooks/2026-11-28-roadmap-loop-state.md), [incidents](incidents/), [archives](archive/) |
| Comment restaurer ? | [Reboot et restauration](homelab-reboot-runbook.md), [G1 PostgreSQL](runbooks/postgres-g1-restore-and-secret-rotation.md), [OpenWebUI PRA](openwebui-backup-pra.md) |

## Répartition inter-dépôts

- [FastAPI Sample](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) : API, statut des sondes, ergonomie opérateur, runtime cloud.
- [Site Alban](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/quality-roadmap.md) : interface Next.js, support, SEO, WAF Vercel du site.
- [Site Bababou](https://github.com/AlbanAndrieu/nabla-site-bababou/blob/master/docs/roadmap.md) : application et publications.
- [OpenClaw](https://github.com/AlbanAndrieu/nabla-openclaw) : agents, heartbeat et automatisations.
- **Ce dépôt** : Compose, TrueNAS, Talos, ZFS, infrastructure Cloudflare, secrets et projections du catalogue. Pas de duplication des roadmaps applicatives.

## Hygiène documentaire

- **Backlog** : une seule ligne par Hxx dans `roadmap-portfolio.md`. `roadmap.md` porte seulement l'ordre opérationnel et la preuve à chercher.
- **Runbook** : prérequis, `check`, `apply` autorisé, vérification, rollback. Pas de journal de session ni de statut répété.
- **ADR** : choix architectural et alternatives ; **incident** : symptômes, cause, remédiation, prévention ; **archive** : contexte daté non exécutable sans nouveau préflight.
- **Preuves** : distinguer `CODED`, `TESTED`, `DEPLOYED`, `ACCEPTED` et `NOT_VERIFIED` ; conserver les dates et les SHAs, ne jamais requalifier `DENIED` en `DOWN`.
- **Nettoyage** : conserver les références historiques et les procédures de recovery. La suppression physique de fichiers exige la vérification des liens et consommateurs.
