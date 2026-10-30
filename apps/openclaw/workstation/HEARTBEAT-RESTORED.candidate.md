# HEARTBEAT — reprise contrôlée des objectifs historiques

<!-- CANDIDAT NON ACTIF. Application GitOps et configuration heartbeat à valider d'abord. -->
<!-- Ne jamais lire directement de tokens, prompts, emails ou échanges WhatsApp privés. -->

tasks:
  - name: homelab-health
    interval: 2h
    prompt: "Vérifier seulement les preuves récentes Gatus, Prometheus, OpenClaw et les synthèses expurgées LiteLLM Workstation/TrueNAS. Pour une source inaccessible, indiquer UNKNOWN et ne pas conclure DOWN. Ne lancer aucune inférence de test, aucun restart ni mise à jour. Signaler seulement les nouvelles anomalies."
  - name: workboard-follow-up
    interval: 6h
    prompt: "Lister en lecture seule les tâches OpenClaw et Workboard seulement si ces commandes existent ; ne pas appeler dispatch, move, cancel ou continue work. Résumer les nouveaux blocages et les actions proposées, sans les exécuter."
  - name: security-diagnostics
    interval: 12h
    prompt: "Consulter les diagnostics existants du Gateway, des cooldowns et des proxies LiteLLM. Jamais doctor --fix, npm update, modification de quota ou suppression de session. Indiquer explicitement si les traces des deux LiteLLM ne sont pas disponibles."

# Les autres tâches historiques (CalDAV, Gmail, WhatsApp, Obsidian,
# Loki, briefing 08:00 et digest 09:00) restent dans la politique
# déclarative séparée : aucune connexion à un compte personnel ici.
# Si aucune nouvelle anomalie n'est prouvée, répondre HEARTBEAT_OK.
