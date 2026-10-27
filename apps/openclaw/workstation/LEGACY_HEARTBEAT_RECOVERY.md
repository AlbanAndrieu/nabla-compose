# Récupération revue de l'ancien heartbeat OpenClaw (sans activation)

Statut : **inventorié, non déployé**, pas de nouvelle tâche ni heartbeat génératif.
Sources fournies par l'opérateur le 27 octobre 2026, conservées sur la
Workstation : le clone `nabla` déchiffré via git-crypt, le
`~/.openclaw/workspace/HEARTBEAT.md.before-fix` et une archive
`openclaw-backups/openclaw-2026-08-04_0220.tar.gz` (~993 Mo).
Ces documents sont **des sauvegardes potentielles**, pas une preuve de
configuration en cours d'exécution.

## Ordre de récupération

1. Inspecter **en privé** les métadonnées et permissions de
   `HEARTBEAT.md.before-fix` (source récente), sans publier son contenu.
2. Comparer les **comportements voulus**, et non les secrets, avec
   `nabla/env/home/dotfiles/.openclaw/workspace/HEARTBEAT.md`,
   qui est lisible dans le clone déverrouillé.
3. Considérer l'archive d'août comme filet de récupération de dernier
   recours. Ne pas l'extraire intégralement, l'uploader, ni écraser
   `~/.openclaw` : elle peut contenir clés, tokens, sessions
   et comptes. Son mode `0644` observé dans le listing opérateur
   est **trop permissif** pour une sauvegarde OpenClaw potentiellement
   sensible. Vérifier son propriétaire et passer en `0600`
   dans une console locale autorisée.
4. Ne restaurer dans le dépôt public que des politiques **nouvelles,
   expurgées et approuvées**, jamais le blob git-crypt ni le fichier
   entier des sauvegardes.

## Inventaire des fonctionnalités à conserver

| Fréquence historique | Intention dans l'ancien document | Cible revue | Statut |
| --- | --- | --- | --- |
| 15 min | Workboard : tâches en cours, suivi et « continue work » | Collecte déterministe read-only ; action de travail séparée et autorisée | Proposée |
| 30 min | Synchroniser CalDAV / vdirsyncer | Job système isolé avec ACL et surveillance d'échec, sans LLM | Non réactivé |
| 1 h | Santé Gatus/Prometheus/ArgoCD/endpoints | Collecteurs déterministes et alerte sur changement, sans inférence périodique | Proposé |
| 1 h | Triage Gmail | Identité Gmail autorisée **configurée en privé**, règles least privilege, pas de suppression automatique | Non réactivé |
| 1 h | Notifications et WhatsApp sync | Collecteur indépendant, préservation des exclusions privées ; pas de contenu dans Git | Non réactivé |
| 6 h | Nouvelles notes Obsidian / base de connaissances | Import limité aux dossiers allowlistés, aperçu avant écriture | Non réactivé |
| 6 h | Doctor, disque, mémoire, health | `openclaw doctor` en **lecture seule** seulement ; aucun `--fix` | Proposé |
| 12 h | Audit documentation et qualité | Git diff + analyses offline, changements via PR Draft | Proposé |
| 12 h | Logs et insights Loki | Synthèse expurgée ; aucune remédiation mutable implicite | Proposé |
| 01:00 | Velocity assessment | Rapport hebdomadaire ou quotidien isolé selon coût réel | Différé |
| 04:00 | Brainstorm notes | Facultatif, sans accès automatique à notes privées, budget dédié | Différé |
| 08:00 | Morning Briefing | `MORNING_BRIEFING.md` dédié, preuves horodatées, déclenchement isolé | Politique versionnée, job non créé |
| 09:00 | Digest Discord | `daily-tech-news-digest.policy.json`, skill pin, résultat de validation avant livraison | Job existant, réconciliation non appliquée |
| Hebdo | QA base de connaissances et sécurité infra | Collecte deterministic + revue humaine | Proposé |

**Aucune de ces cadences ne doit être copiée telle quelle dans
`HEARTBEAT.md` natif** : le heartbeat de 30 minutes réveillerait
le modèle pour des opérations de fréquences différentes et augmenterait
la consommation. Utiliser systemd timers/cron isolés pour les contrôles
déterministes et OpenClaw cron isolé seulement pour le raisonnement utile.

## Contenu de briefing conservé

Le fichier actuel `MORNING_BRIEFING.md` reprend déjà météo à la
demande, disque, RAM, charge CPU, services essentiels, calendriers,
Gmail/WhatsApp, alertes et règles de couleur.
La revue du 27 octobre ajoute : **workboard OpenClaw**, état des
tâches/« en cours », et **récapitulatif des actions effectivement
réalisées** séparé des actions proposées.

L'ancienne procédure prescrivait `openclaw tasks list`
**sans `--plain`** en haut de fichier, mais la section
briefing reprenait `--plain`. Préférer l'invocation non formatée
et vérifier `openclaw tasks --help` sur la CLI installée.
L'absence de la sous-commande doit être signalée, pas contournée
par un autre outil pouvant muter l'état.

Le texte de la source la plus récente contenait aussi un
résultat d'authentification Gmail obsolescent et une exclusion
de conversation WhatsApp personnelle. **Ne pas versionner leurs
identifiants ni leurs contenus.** La configuration privée et
les droits actuels font autorité. Aucun état « synchronisé » n'est
déduit du simple texte de la sauvegarde.

## Contrôles de sécurité

- `HEARTBEAT.md` déployé doit rester non génératif jusqu'à
  attestation des budgets LiteLLM et du parcours `main`.
- Aucun retour automatique de `openclaw doctor --fix`, réécriture
  des sessions SQLite, réindexation mémoire, ou archivage Gmail.
- Les compétences/skills et MCP externes sont épinglés et revus avant
  d'être mis à disposition de l'agent `cron`.
- Vérifier indépendamment la disponibilité réelle des sources
  Gatus, Prometheus, CalDAV et messageries avant de publier
  un briefing.
- La sauvegarde de travail reste sur la Workstation et
  n'est pas transmise à l'agent ou à GitHub par défaut.
