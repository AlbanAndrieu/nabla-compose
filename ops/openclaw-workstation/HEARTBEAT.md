# HEARTBEAT.md — surveillance native OpenClaw

<!--
Le heartbeat principal est volontairement non génératif tant que
son coût et le 429 ne sont pas attribués. Les commentaires sont ignorés
par OpenClaw : reason=empty-heartbeat-file, aucun appel de modèle.

Ce fichier n'est PAS le modèle du briefing quotidien.
Le briefing détaillé, avec météo, CPU, RAM, disque, services, Gatus,
Prometheus, CalDAV, Gmail, WhatsApp et tâches, est versionné dans
ops/openclaw-workstation/MORNING_BRIEFING.md et projeté dans le workspace
par le script GitOps.

Le briefing doit être demandé explicitement ou exécuté dans une tâche
isolée avec sa propre cadence et son propre budget, jamais dans le
heartbeat toutes les 30 minutes.

Règles permanentes :
- Pas de mail, calendrier, messages, SSH, Docker ou accès aux fichiers
  personnels sans autorisation et connecteur réellement disponible.
- Aucune affirmation « synchronisé », « vert », « pas d'alertes »
  sans preuve récente des collecteurs déterministes.
- Aucun contournement des budgets LiteLLM ou des SecretRef.
- Ne pas lancer de memory reindex ou d'inférence pour remplir le briefing.
- Contrôler les coûts 429, la mémoire et le job du matin séparément.
- Ne pas copier le texte de l'ancienne sauvegarde verbatim dans un
  heartbeat périodique non borné.
-->
