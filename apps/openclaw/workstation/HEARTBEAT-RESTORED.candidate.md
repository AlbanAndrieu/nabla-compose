# Heartbeat — contrôles historiques restaurés (candidat inactif)

- À chaque réveil, consulter uniquement les preuves de santé **déjà disponibles** (Gatus, Prometheus, OpenClaw et résumés expurgés LiteLLM Workstation/TrueNAS) ; si l'une manque, afficher UNKNOWN, pas DOWN.
- Mentionner seulement les anomalies nouvelles ou aggravées et les Workboard/Tasks bloqués déjà visibles ; aucune relance automatique ni boucle de travail.
- Ne pas lancer d'inférence de test, de commande de réparation, de connexion Gmail/WhatsApp/CalDAV, de synchronisation Obsidian, de reindex mémoire ou d'augmentation de quota.
- Si aucune nouveauté n'est confirmée, répondre HEARTBEAT_OK.

<!-- Ne contient aucun tasks: actif : les cadences de l'ancien heartbeat
     doivent être reconstruites par jobs isolés après validation des ACL.
     Ne pas déployer tant que le budget et la version runtime sont inconnus. -->
