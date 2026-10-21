# TrueNAS / Catalog v2 — redémarrage par vagues et garde-fous

Diagnostic capturé le **21 octobre 2026** (hors production Git) :
67 Apps RUNNING, 32 STOPPED, 45 Apps sans mapping Backstage direct,
13 matérialisations runtime de secrets manquantes parmi les RUNNING.
Ces chiffres sont des observations historiques, **pas des vérités GitOps**.

## Ordre unique (source : config/truenas/restore-optional-apps.txt)

1. **Core RUNNING** : les Apps réellement RUNNING sont redémarrées **une à une**
   et non toutes arrêtées d'un coup. L'ordre est topologique pour les
   dépendances Backstage résolues, avec priorités stables des fondations.
2. **Gatus isolé** : Gatus n'est **pas** dans les Apps optionnelles et
   son échec ne bloque **jamais** le core ni les Apps différées. L'activation
   nécessite `--include-gatus` explicite.
3. **Dernière vague** : les 31 Apps non essentielles STOPPED du snapshot
   utilisateur et les autres App IDs déjà déclarés optionnels sont
   uniquement lancés avec `--include-deferred`. Les Apps
   `planned`/`disabled` connues bloquent cette action.
   Aucune App STOPPED n'est implicitement redémarrée.

L'ancien `restore-app-set.sh` réutilise le même fichier d'Apps
optionnelles et les exclut par défaut. Ce script continue de restaurer
des Apps STOPPED, il **ne sait pas redémarrer** des Apps RUNNING ; le
nouvel orchestrateur ci-dessous remplit ce besoin spécifique.

## Préparation (lecture seule sur TrueNAS)

```bash
cd /mnt/cpool/compose/nabla-compose
sudo python3 scripts/truenas/restart-catalog-v2-apps.py --check \
  --output /tmp/nabla-v2-restart-preflight.json
sudo jq '{planHash,counts,missingRunningSecrets,nonBlockingGatus,
          runningDeferredExcluded,deferredLast}' /tmp/nabla-v2-restart-preflight.json
```

`planHash` identifie **les états de tous les TrueNAS Apps**, la révision
du catalogue et l'état de disponibilité des secrets ; il change dès qu'une
App change d'état. `--apply` recalcule depuis `app.query` pour éviter
une exécution sur snapshot périmé.

### Blocages attendus actuellement

- 13 secrets runtime manquants sur des RUNNING : **aucune mutation tant
  qu'ils sont absents**. Vérifier chaque App contre
  `config/secrets/manifest.json` depuis un compte utilisateur déverrouillé :
  `python3 scripts/secrets/materialize_runtime.py --app <id> --verify`.
  `--verify` compare seulement avec l'état runtime et peut échouer si
  celui-ci n'est pas matérialisé. Ne jamais logger `BW_SESSION` ni le
  contenu secret.
- 45 Apps sans mapping : rapport de couverture incomplet, **pas**
  automatiquement une panne. Les liens Backstage/Compose ne doivent
  jamais être inventés par simple correspondance de noms.
- Gatus redémarre en boucle, métadonnées observées : permissions
  config/dataset à diagnostiquer avant `--include-gatus`.
- FastAPI TrueNAS `127.0.0.1:8091/api/site/catalog/v2` répond 404,
  FastAPI Cloud renvoie 401 sans clé (attendu) : ce sont des déploiements
  différents ; ne pas traiter 404/401 comme un DOWN de la plateforme.

## Exécution sensible : ne faire qu'après validation des secrets

```bash
HASH="$(sudo jq -r .planHash /tmp/nabla-v2-restart-preflight.json)"
sudo python3 scripts/truenas/restart-catalog-v2-apps.py --apply \
  --expected-plan-hash "$HASH" \
  --acknowledge-downtime I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART
```

Ceci occasionne de vraies interruptions. **Ne pas exécuter actuellement** :
les 13 secrets manquent. Le préflight refusera sans arrêt d'Apps.
L'exécution garantit seulement un arrêt/démarrage de chaque App dans son
périmètre et l'exécution du health gate Docker existant : cela ne garantit
ni l'accès métier de bout en bout, ni Vaultwarden, ni les sondes réseau.

Une fois le core accepté, Gatus et la vague différée se déclenchent
**séparément**, avec les mêmes confirmations, en ayant vérifié
l'état réel des Apps : `--include-gatus` / `--include-deferred`.
Toute erreur core arrête immédiatement la progression : ne pas
redémarrer des autres Apps aveuglément. Le journal JSONL sous
`/mnt/cpool/var/nabla/restart` enregistre les actions et résultats,
sans variables d'environnement ni contenu de secrets.

**Contraintes :** root requis pour `--apply`, snapshot figé par
`planHash`, listes d'App ID exactes, `app.stop` et `app.start`
via TrueNAS middleware uniquement. Aucun usage `apt`, aucun
redémarrage du TrueNAS hôte, aucun stockage de mot de passe.
