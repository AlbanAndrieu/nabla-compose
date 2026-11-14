# ADR — Limites des dépôts et diagnostics Homelab

**Proposé le 14 novembre 2026 · décision à valider par migration réelle.**
Source de référence : [plan de séparation](../scripts/ops/plan-repository-split.py), [H11](../roadmap-portfolio.md) et les roadmaps propres à `ansible-workstation` et `nabla-openclaw`.

## Décision proposée

- **`nabla-compose`** reste propriétaire de la topologie déclarative Backstage V2, des déploiements TrueNAS/Compose/Talos, du catalogue et du dispatch des scripts d'acceptation. N'a pas de privilèges pfSense ou workstation par défaut.
- **`ansible-workstation`** possède l'état OS Ubuntu, les playbooks, audits d'hôte, sauvegarde/reprise OS, DNS et outillage installé. N'exécute ni les mutations du Gateway OpenClaw ni les opérations de firewall.
- **`nabla-openclaw`** possède la configuration Gateway, cron, heartbeat, politiques, scripts d'exploitation OpenClaw et leur rollback. **Déjà sous-module** `apps/openclaw` : ne pas ajouter un second gitlink. Les scripts LiteLLM TrueNAS/clé proxy et les opérations inter-hôtes restent à examiner individuellement.
- **`nabla-pfsense` (à créer)** possède la posture pfSense, scripts PHP sur pfSense, diagnostic/récupération Unbound/HAProxy, plans upgrade et tests dédiés. Compose conserve la *déclaration de dépendances, le lien d'inventaire et les recettes d'acceptation inter-composants*.
- **`fastapi-sample`** possède les API et la normalisation des états/horodatages/identités et collecte depuis TrueNAS ; **Gatus** est ordonnanceur de sondes synthétiques, **Prometheus** source des métriques et séries temporelles, **Grafana** présentation/alerting. Compose ne doit pas reconstituer une deuxième base de statuts en shell.

## Submodules — retenir un critère technique, pas une habitude

`apps/openclaw` est déjà un gitlink car le déploiement consomme un **SHA exact**. Pour `ansible-workstation` et `nabla-pfsense`, préférer deux checkouts frères + références versionnées dans l'inventaire. Un nouveau sous-module ne se justifie que si un workflow Compose **consomme un arbre à SHA fixe** au build/apply ; le mettre sous `integrations/` (pas `apps/`) et contrôler `git submodule update --init` de manière explicite. Les submodules chargés sans raison élargissent le checkout, les mises à jour gitlink et la surface de qualité.

## Frontières de privilèges — quatre capacités indépendantes

| Plan | Autorisation | Exécution admissible | Interdits |
| --- | --- | --- | --- |
| `observe-public` | Aucun secret | Résultats Cloud `/sickz`, états publics expurgés | Confondre un 200 Cloud avec la santé d'un service |
| `observe-internal` | Identité de service dédiée, GET limité | FastAPI TrueNAS `/api/homelab/status`, `/api/homelab/health`, observations Gatus/Prometheus | Token d'administration ou Docker socket en lecture publique |
| `inspect-host` | Auth hôte séparée et auditée | `midclt`, commandes pfSense read-only, état Docker/ZFS, `promtool`, preuves de reboot | Mutations implicites, secrets/variables bruts dans stdout |
| `mutate-recover` | Identité administrateur, approbation explicite | Restauration, DNSBL/HAProxy, restart, scripts PHP `--apply` avec backup et rollback | Utiliser le même credential qu'une sonde |

Un `403` Cloudflare Access peut être **attendu**. `NOT_RUN`, `STALE`, `DENIED`, `NO_SAMPLE` et `DOWN` restent distincts. Mesurer l'âge de l'observation, le point de vue (`truenas-internal` ou `cloud-outside-in`), `entityRef` et `catalogRevision`. L'endpoint `/sickz` utilise des cibles URL : ne pas inventer une correspondance `serviceId` sans preuve de jointure.

## Politique de diagnostic : rationaliser sans supprimer la reprise

1. **FastAPI TrueNAS** d'abord pour les composants internes, **FastAPI Cloud `/sickz`** ensuite pour l'exposition réellement outside-in ; résultat mis en cache, synthèse par ID *uniquement si corrélable*.
2. **Gatus et Prometheus** alimentent l'observabilité continue : ne pas relancer un fan-out d'HTTP/curl en boucle lorsqu'une preuve récente existe.
3. **Scripts ponctuels de Compose** uniquement pour les écarts d'observateurs et les opérations qui exigent des privilèges de host, de configuration, de restauration ou d'acceptation versionnée. Une panne du contrôleur FastAPI doit laisser possible un diagnostic autonome depuis TrueNAS.
4. Garder les assertions statiques sur les manifestes, contrats `entityRef`, checksum, `promtool`, backup/restore et smoke d'intégration. Ne pas transformer un script d'administrateur en exporter persistant.
5. Distinguer script **observation** (GET, aucune mutation) d'un script **réconciliation/mutation** (`--apply`, contrôle des privilèges et sauvegarde préalable). Aucune commande à effet de bord dans le chemin de diagnostic par défaut.

## Migration progressive et conditions de retrait

| Vague | Lot | Précondition et preuve | Stratégie |
| --- | --- | --- | --- |
| M0 | Inventaire | `python3 scripts/ops/plan-repository-split.py` + recherche des imports, `justfile`, scripts systemd, tests et docs | Aucun déplacement |
| M1 | Workstation/OpenClaw | Parité destination, système `--user`, propriétaire des fichiers, cron unique, rollback désactivé préservé | Copier puis wrappers temporaires ; archiver les anciens tests après parité |
| M2 | pfSense | Créer dépôt; déplacer **scripts et tests ensemble**, vérifier API/SSH/PHP, snapshots, branches `--check`/`--apply`, permissions négatives | Enlever les implémentations de Compose après adaptation de tous les consommateurs ; `nabla-pfsense` non encore créé |
| M3 | Diagnostics doublonnés | Matrice des sorties/codes; FastAPI/Gatus/Prometheus disponibles et tests d'incident « observateur indisponible » | Remplacer les agrégateurs par adaptateurs courts ; garder les checks host spécialisés |
| M4 | Cleanup | CI de chaque dépôt, contrat inter-dépôts au SHA épinglé, suppression des chemins morts et mise à jour du catalogue | Aucune suppression en bloc ; revenir à l'ancien SHA/checkout si nécessaire |

**Critère DONE :** les scripts sont réellement adoptés dans leurs dépôts propriétaires, aucune tâche systemd/CI/Just n'appelle un chemin abandonné, et les tests de permissions négatives, migrations et rollback sont exécutés sur un SHA exact. Une extraction documentaire n'est pas une migration terminée.
