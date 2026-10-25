# Runbooks — index et autorité

> Mis à jour le 25 octobre 2026. Ce répertoire regroupe des procédures
> spécialisées et des comptes rendus historiques. **Un runbook daté n'est
> pas automatiquement une procédure d'exploitation encore valable.**

## Point d'entrée courant

- **[Opérateur de migration TrueNAS](truenas-migration-operator.md)** —
  entrée CLI stable, modes exclusifs, planHash et workflow de rollback.
- **[Acceptation runtime Homelab](homelab-runtime-acceptance.md)** —
  priorité de diagnostic Prometheus → OpenRAG → Akvorado ;
  sondes en lecture seule, preuves minimales, interdictions et décisions.
- **[Diagnostics opérateur spécialisés](2026-10-25-homelab-operator-diagnostics.md)** —
  Gatus, Prometheus et vérifications isolées, sans déploiement.
- **[Triage observabilité](2026-10-25-observability-triage.md)** —
  causes instrumentées, exporter PostgreSQL et Auth FastAPI.
- **[Tests rapides Node 22/npm 10](node22-local-fast-tests.md)** —
  contrats statiques hors ligne et limitations de la preuve.
- **[Relevé TrueNAS du 25/10](2026-10-25-critical-acceptance-evidence.md)** —
  preuve datée PASS=8/FAIL=8, non assimilée à une santé courante.
- **[Roadmap active](../roadmap.md)** —
  priorités, risques ouverts et conditions de clôture.
- **[Skill local-first](../../.agents/skills/local-first-quality/SKILL.md)** —
  worktrees privés, tests, formatage, gate qualité et publication Draft.
- **[Registre des refactorings risqués](homelab-refactoring-risk-register.md)** —
  niveaux de risque, tests négatifs et seuils de publication.
- **[Sécurité/architecture des skills](../agent-skills-architecture.md)** —
  préséance des instructions ; installation des skills externes sur accord.

## Runbooks spécialisés encore utiles

| Domaine | Référence | Usage |
| --- | --- | --- |
| APISIX | [service opt-in](../../apps/apisix/README.md) · [acceptation après migration](truenas-migration-operator.md) | Vérifier le runtime séparément du smoke HTTP, sans ingress public |
| OpenRAG | [README d'exploitation](../../apps/openrag/README.md) · [ingestion](openrag-babou-ingestion-diagnostics.md) | État applicatif, Langflow/OpenSearch/LiteLLM, Docling et corpus privé |
| Sentry | [reprise Apps du 23/10](2026-10-23-app-error-recovery.md) | Historique des incidents ; utiliser le diagnostic ciblé avant toute remédiation |
| DefectDojo | [accès privé](defectdojo-private-ingress-acceptance.md) | Nginx/uWSGI, HTML origine, DNS interne, Traefik et HTTPS SNI |
| Prometheus | [récupération observabilité](2026-10-24-prometheus-pyroscope-dns-dot-recovery.md) | Historique ; ne pas réappliquer un `chmod` déjà traité |
| Akvorado / pfSense | [incident Unbound/pfBlockerNG](2026-10-24-pfsense-unbound-pfblocker-whatsapp.md) | OOM, mémoire, NetFlow, sans attribuer causalité sans preuve |
| Secrets | [feuille de route secrets](../secrets-migration-roadmap.md) | Rotation, staging et rollback explicitement approuvés |
| Talos/CSI | [préflight CSI](../kubernetes-csi-preflight.md) | NFS/CSI et tests multi-nœuds avant migration |

## Journaux et procédures historiques

Ces fichiers sont **conservés pour la traçabilité**, mais leurs états
`UP`, `DOWN`, `DEPLOYING` ou `STOPPED` et leurs commandes `--apply`
ne doivent jamais être réexécutés sans nouveau préflight :

- [Commandes opérateur du 24 octobre](2026-10-24-homelab-operator-next-commands.md) :
  passation multi-domaines de la PR #274.
- [Acceptation des migrations du 24 octobre](2026-10-24-truenas-migration-acceptance.md) :
  planification des vagues, transactions et historiques.
- [Reprise des Apps du 23 octobre](2026-10-23-app-error-recovery.md) :
  état de la récupération, observé à cette date.
- [Quality gate de la PR #274](2026-10-24-pr274-local-quality-one-shot.md) :
  bootstrap épinglé à une PR **fusionnée**.
- [Roadmap antérieure](../archive/roadmap-through-2026-10-24.md) :
  inventaire intégral des décisions et preuves historiques.

**Règle de maintenance :** une nouvelle observation va dans son runbook
d'incident avec date, source et commandes read-only. La roadmap contient
uniquement l'action non terminée et la gate d'acceptation. Un changement
de politique transverse doit être versionné dans le skill correspondant.
Ne pas recopier les journaux bruts, secrets, tokens, DSN ou données privées
dans un document public.
