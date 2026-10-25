# APISIX — démarrage isolé et rollback

**ADR-0001 accepté pour staging**, mais aucune gateway déployée. Ce installation de test
est indépendant de Traefik, FastAPI et TrueNAS : il interroge uniquement
une page de test, sur un réseau Docker `internal: true`, **sans ports hôte**.

1. Définir `APISIX_KEY` (clé aléatoire de 24 à 256 caractères, sans espace ni caractère de contrôle) dans le shell ;
   ne pas la placer dans Git ou l'historique de commandes.
2. Exécuter `just apisix-contract` (contrôle sans Docker).
3. Exécuter `just apisix-up` sur une workstation disposant de Docker.
4. Exécuter `just apisix-check` pour vérifier les métadonnées des deux conteneurs sans clé. Ce contrôle ne teste pas la route HTTP.
5. Exécuter `just apisix-smoke` : absence de clé 401, clé 200,
   route inconnue 404, méthode non autorisée 404/405. Le smoke désactive
   les proxys HTTP hérités pour garantir un test direct du réseau Docker isolé.
6. Exécuter `just apisix-down` pour supprimer le réseau et les conteneurs.
   **Aucune clé APISIX n'est nécessaire pour ce rollback** : le wrapper utilise
   uniquement une valeur de substitution lors de l'interpolation Compose,
   sans redémarrer les services.

La clé APISIX ne remplace jamais le jeton machine FastAPI. Le service de test
n'expose aucune Admin API ni métriques sur un port hôte.
Image APISIX `3.19.0-debian` versionnée pour le laboratoire.
Avant un déploiement TrueNAS durable, épingler par **digest vérifié**,
ne pas inventer un digest ; ajouter ensuite l'auth OIDC et la propagation
`traceparent` derrière Traefik sur un hostname privé.

Si le smoke échoue, consulter les diagnostics expurgés du service, puis effectuer `down`.
Cela ne doit pas altérer les flux de production.

## Vérification après migration

Exécuter `just apisix-check` uniquement après le démarrage autorisé du
service. `runtime=running health=none http=not_checked` prouve
**uniquement** qu'un conteneur est actif. Un `exit=2` signifie
`not_deployed_or_ambiguous` ou `unverified`, pas une panne réseau
démontrée. Le smoke authentifié est distinct et nécessite `APISIX_KEY`.

APISIX est **optionnel** dans la migration TrueNAS :
`sudo bash scripts/truenas/migration-operator.sh --check --section apisix`.
Ne pas l'ajouter à la liste des services critiques tant qu'il n'a pas
été déployé. Le rapport post-migration général utilise `--section postmigration`.
Voir le [runbook de migration](../../docs/runbooks/truenas-migration-operator.md).
