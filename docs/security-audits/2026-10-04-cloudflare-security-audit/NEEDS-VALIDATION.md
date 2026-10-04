# NEEDS VALIDATION

## Scanopy daemon first-initialization boundary

**Fingerprint :** `scanopy-daemon-public-bootstrap-boundary`

### Trace source

- `apps/scanopy/compose.yml:23` — `network_mode: host`.
- `apps/scanopy/compose.yml:24` — `privileged: true`.
- `apps/scanopy/compose.yml:39` — socket Docker brut monté dans le daemon.

Le dépôt cible utilise `ghcr.io/scanopy/scanopy/daemon:latest`, donc la révision
réellement exécutée n'est pas déterminée par Git.

La source publique Scanopy courante a également été consultée pour comprendre le
contrat upstream :

- `backend/src/daemon/shared/config.rs` : bind par défaut `0.0.0.0`, port
  `60073`;
- `backend/src/daemon/shared/handlers.rs` : `/api/health` et
  `/api/initialize` sont dans les routes publiques ;
- le handler d'initialisation n'applique son garde « already initialized »
  qu'après présence de `network_id` **et** `api_key`.

Ces faits upstream ne prouvent pas que le conteneur live exécute exactement cette
révision.

### Faits manquants

1. digest/révision exacte de l'image Scanopy déployée ;
2. état déjà initialisé ou non du daemon ;
3. adresse effective d'écoute sur TrueNAS ;
4. politique host/pfSense pour TCP/60073 ;
5. comportement des logs de la version déployée pendant l'initialisation.

### Validation locale sûre

Sur une machine jetable isolée, sans socket Docker réel ni secrets :

1. utiliser **le digest exact** relevé sur TrueNAS ;
2. démarrer le daemon avec un HOME/config scratch ;
3. utiliser uniquement des UUID/clés factices ;
4. déterminer si la première initialisation est acceptée sans authentification ;
5. arrêter au premier résultat suffisant et vérifier si la clé factice apparaît
   dans les logs.

Ne pas reproduire ce test actif sur le homelab partagé.

### Validation owner-observed sur TrueNAS

Sans envoyer de requête d'initialisation :

1. relever le digest de l'image ;
2. inspecter passivement le socket/listener TCP/60073 ;
3. confirmer le firewall/routage autorisé vers ce port ;
4. vérifier seulement la **présence** de l'état d'initialisation, sans imprimer
   `network_id`, `api_key` ou autre secret ;
5. vérifier la politique de rétention/redaction des logs.

### Remédiation à privilégier si la frontière est confirmée

- pinner Scanopy sur un tag + digest revu ;
- limiter `SCANOPY_BIND_ADDRESS`/firewall à la portée nécessaire ;
- éviter l'exposition LAN du daemon si seul le serveur local doit le joindre ;
- remplacer le socket Docker brut par un proxy filtré si les appels Scanopy le
  permettent ;
- documenter explicitement tout privilège restant comme root-equivalent.
