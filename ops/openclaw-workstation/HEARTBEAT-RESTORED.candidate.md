# Heartbeat — observateur de santé, candidat inactif

- À chaque réveil, lire **uniquement** les derniers états **déjà collectés** de Gatus, Prometheus, OpenClaw et LiteLLM Workstation/TrueNAS, sans sondage génératif. Indiquer l'horodatage et la fraîcheur des observations quand ils sont disponibles.
- Ne remonter que les changements **nouveaux ou aggravés** ; dédupliquer le même symptôme d'un réveil à l'autre. Une source inaccessible ou trop ancienne vaut **UNKNOWN / NOT_VERIFIED**, jamais DOWN par défaut.
- Limiter la synthèse à **3 anomalies prioritaires**, avec pour chacune un service, un signal expurgé, son niveau de preuve et la prochaine vérification **en lecture seule**. Ne pas transformer un motif de log 429 en attribution certaine d'agent.
- Les Workboard/Tasks bloqués **déjà visibles** peuvent être signalés brièvement ; ne jamais créer ni lancer de tâche depuis ce heartbeat.
- Ne pas lancer d'inférence de test, de commande de réparation, de connexion Gmail/WhatsApp/CalDAV, de synchronisation Obsidian, de réindex mémoire, de modification du routage ou d'augmentation de quota.
- Ne pas afficher de secret, payload, message privé, identifiant de session ou log brut. Les connexions dégradées et les preuves manquantes doivent rester distinguées des pannes avérées.
- En l'absence de nouveauté confirmée, répondre `HEARTBEAT_OK` **uniquement si cet acquittement est compatible avec la version OpenClaw déployée** ; vérifier le comportement silencieux natif avant activation.

<!-- CANDIDAT INACTIF. Aucun tasks: actif.
     Cadence et coût proposés dans heartbeat-restoration.policy.json :
     every=2h, lightContext=true, isolatedSession=true, skipWhenBusy=true,
     target=none, activeHours=08:00-22:00 Europe/Paris.
     Les 14 fonctions historiques sont des automations séparées, non activées.
     Aucun apply, secret, modèle ou job réel ne doit être déduit de ce fichier. -->
