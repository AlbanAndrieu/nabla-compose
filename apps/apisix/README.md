# APISIX POC — démarrage et rollback

**ADR-0001 accepté pour staging**, mais aucune gateway déployée. Ce POC
est indépendant de Traefik, FastAPI et TrueNAS : il interroge uniquement
une page de test, sur un réseau Docker `internal: true`, **sans ports hôte**.

1. Définir `APISIX_POC_KEY` (clé aléatoire >= 24 caractères) dans le shell ;
   ne pas la placer dans Git ou l'historique de commandes.
2. Exécuter `just apisix-poc-contract` (contrôle sans Docker).
3. Exécuter `just apisix-poc-up` sur une workstation disposant de Docker.
4. Exécuter `just apisix-poc-smoke` : absence de clé 401, clé 200,
   route inconnue 404, méthode non autorisée non-200.
5. Exécuter `just apisix-poc-down` pour supprimer le réseau et les conteneurs.

La clé POC ne remplace jamais le jeton machine FastAPI. Le POC
n'expose aucune Admin API ni métriques sur un port hôte.
Image APISIX `3.19.0-debian` versionnée pour le laboratoire.
Avant un déploiement TrueNAS durable, épingler par **digest vérifié**,
ne pas inventer un digest ; ajouter ensuite l'auth OIDC et la propagation
`traceparent` derrière Traefik sur un hostname privé.

Si le smoke échoue, lire les logs locaux APISIX, puis effectuer `down`.
Cela ne doit pas altérer les flux de production.
