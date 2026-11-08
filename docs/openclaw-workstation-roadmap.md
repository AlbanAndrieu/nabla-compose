# OpenClaw Workstation — historique et retrait des doublons

> **État au 6 novembre 2026 : la migration Gateway vers TrueNAS est terminée.**
> L'autorité courante appartient à [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md). La [PR Compose #323](https://github.com/AlbanAndrieu/nabla-compose/pull/323) a fixé le gitlink ; la [PR OpenClaw #10](https://github.com/AlbanAndrieu/nabla-openclaw/pull/10) clôt le cutover et décrit les preuves runtime. Ne pas réappliquer les anciennes procédures de cette Workstation.

## P0 — Réception TrueNAS : terminée, vérification continue

- Le Gateway Workstation `openclaw-gateway.service` est arrêté et désactivé ; il reste une voie de **rollback manuel**, testé le 1er novembre.
- Le Gateway TrueNAS `openclaw-gateway` a passé readiness, Telegram, WhatsApp et un tour d'agent ; le LiteLLM TrueNAS relaie vers le GPU de **LiteLLM Workstation**. La clé main, la clé cron et le modèle `gpt-4.1-mini` ont servi une complétion réelle.
- Le `HEARTBEAT` TrueNAS de santé Homelab est opérationnel et distinct du briefing du matin ; le digest GitOps s'exécute via `exec` déterministe et a livré un message en français. `agent:cron:main` a été recréé.
- Les échecs historiques du 1er–2 novembre (blocage du `doctor` dans ZFS, rollback Workstation), du 3–4 novembre (base PostgreSQL de LiteLLM déplacée sur `intranet`) et les échecs digest `--top 3-5`, Tool Search et X HTTP 402 restent les leçons à conserver. Les actions de reprise sont documentées dans [nabla-openclaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md).

## P1 — Nettoyage des scripts historiques (en cours)

- **Propriétaire unique :** `nabla-openclaw` pour le Gateway, le cron, le heartbeat, les policies et leurs modifications. Le dépôt Compose garde l'infra TrueNAS, les clés LiteLLM, les scripts de diagnostic inter-hôtes et les chemins de secours documentés.
- Les artefacts temporaires Workstation `HEARTBEAT-SCRATCH.template.md` et `apply-openclaw-heartbeat-scratch.py` ainsi que l'inventaire Git pré-cutover ont été retirés : ils n'ont plus de consommateur runtime. Le contrat [`test_openclaw_policy_relocation.py`](../tests/test_openclaw_policy_relocation.py) interdit leur retour.
- Les autres diagnostics et wrappers `scripts/workstation/openclaw-*` sont **encore présents** : certains sont référencés par `justfile`, des tests ou la procédure de rollback. Ne pas les supprimer en masse. Le retrait total n'est pas encore accepté tant que la parité de leurs consommateurs n'est pas démontrée.
- Remplacer progressivement les actions de mutation du Gateway source par les commandes du dépôt dédié. Aucun `systemctl --user enable`, `--apply` cron ou test de génération ne doit être déclenché par un simple audit Compose.

## P2 — Clôture de compatibilité

- Prouver que les recettes `just`, les automatisations systemd et les tests ne lisent plus les politiques doublonnées sous `ops/openclaw-workstation`, puis retirer ces seules copies.
- Conserver le chemin de récupération chiffré, l'identité runtime et les protections anti-double cron. Contrôler les permissions 0600 des archives et les secrets hors Git.
- Valider localement `test_openclaw_policy_relocation.py`, les tests OpenClaw ciblés et la quality gate du HEAD exact ; **NOT_VERIFIED** tant que non exécutés.

## P3 — Travaux hors migration

- Slack : nouveau token et configuration à valider après `invalid_auth` ; ne pas réutiliser le token révoqué.
- Discord : réactivation conditionnelle après reprise du `doctor` et vérification de la vraie clé.
- Ne pas remettre en marche le Gateway Workstation en parallèle du TrueNAS.

Référence des anciens dysfonctionnements :
[incidents mémorisables, dont le diagnostic 429](incidents/2026-11-06-migrations-retour-experience.md).
