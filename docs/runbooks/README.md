# Runbooks — entrée opérationnelle

> Les runbooks décrivent **quoi contrôler, comment intervenir et comment revenir en arrière** ; ils ne sont ni un second backlog ni un journal quotidien. Priorités et statuts : [portefeuille H01–H21](../roadmap-portfolio.md). Vérifier l'environnement, le SHA, les sauvegardes et les droits avant toute mutation.

## Choisir une procédure canonique

| Besoin | Procédure | Gate minimum |
| --- | --- | --- |
| Diagnostic read-only, `DENIED` vs `DOWN` | [Réception runtime](homelab-runtime-acceptance.md) · [Diagnostic E2E](homelab-e2e-diagnostics.md) | Source, vantage, horodatage, statut sans inférence |
| Apps TrueNAS : état, restart, backup | [Opérations Apps](production-app-operations.md) · [cycle de vie](../truenas-app-lifecycle.md) | `check`, sauvegarde et rollback avant `apply` |
| Migration d'Apps et V2 | [Opérateur de migration](truenas-migration-operator.md) · [recette H17](h17-catalog-runtime-acceptance.md) | Parité des consommateurs, plan, contrôle post-déploiement |
| Talos/CSI NFS | [Préflight CSI](../kubernetes-csi-preflight.md) | Conserver driver effectif et tests RWX ; ne pas rejouer H01 |
| Sauvegarde/rotation PostgreSQL | [G1 restauration](postgres-g1-restore-and-secret-rotation.md) | Restauration isolée, sécurité TLS, preuve de rotation |
| Secrets Vaultwarden / runtime | [Initialisation secrets](../secrets-runtime-initialization.md) | Permissions 0600, source cohérente, aucun secret en logs |
| Cloudflare / Traefik / réseau | [Provenance DNS/ingress](../dns-ingress-ownership.md) · [bascule TrueNAS](truenas-cloudflare-cutover-20261121.md) | SNI/TLS, tests WAN négatifs, pas d'exposition nouvelle |
| Gatus / Prometheus | [Réconciliation](gatus-catalog-reconciliation.md) · [sondes](2026-11-04-probe-remediation.md) | Cible `planned` distincte d'un échec réel |
| CTEM et SBOM | [CTEM exposition](ctem-external-exposure.md) · [Dependency-Track](ctem-dependency-track-acceptance.md) | Autorisation de scan, API 401 anonyme, import/déduplication |
| Nexus et postes clients | [Ingress privé Nexus](nexus-private-dns-ingress.md) | HTTPS vérifié, jamais d'exception TLS globale |
| Entra ID pilote | [Tenant de test](entra-tenant-and-test-user.md) | Plan et identité explicitement validés |
| Support RAG / LiteLLM | [FastAPI et LiteLLM](fastapi-sample-litellm.md) · [OpenRAG](openrag-babou-ingestion-diagnostics.md) | Test factuel, citations, budget et refus |
| CI et agents | [Playbook agent](../agent-execution-playbook.md) · [quality gate](../../.agents/skills/local-first-quality/SKILL.md) | L1 ciblé puis gate locale sur SHA exact |

## Exécution sécurisée

1. **Observer** : sélectionner un seul service, utiliser les sondes read-only avec délais bornés et conserver la provenance ; le mode distant reste `NOT_RUN` pour le LAN.
2. **Préparer** : identifier la ressource, la sauvegarde, la dépendance et le rollback ; ne pas confondre fichiers Compose et Apps TrueNAS gérées.
3. **Agir uniquement si autorisé** : script versionné `--check` puis changement explicite. Aucun `docker compose down`, `kubectl apply`, migration ou redémarrage par simple validation documentaire.
4. **Réceptionner** : comparer avant/après, tester le chemin utilisateur et les refus d'accès, enregistrer résultat, SHA, horodatage et limitations dans le portefeuille.

## Historique hors chemin critique

Les fichiers `2026-*.md` du répertoire constituent des relevés utiles, **pas** des instructions à rejouer. Les incidents se trouvent dans [`docs/incidents/`](../incidents/) et l'ancien pfSense dans [`docs/pfsense/`](../pfsense/). Le [journal du 28/11](2026-11-28-roadmap-loop-state.md) garde la provenance des optimisations de snapshots et Nexus. Ne supprimer un runbook historique qu'après inventaire de ses références et conservation de sa procédure de restauration.
