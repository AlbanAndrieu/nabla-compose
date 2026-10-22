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
   nécessite `--include-gatus` explicite. Cette option traite **Gatus seul**,
   sans redémarrer les applications RUNNING du core.
3. **Dernière vague** : les Apps non essentielles `STOPPED` sont
   exclusivement démarrées avec `--include-deferred`, **sans redémarrer
   le core**. L'ordre `deferredStartOrder` suit les dépendances
   `entityRef`/Backstage résolues, et non l'ordre alphabétique. Les
   fournisseurs externes à cette vague doivent être `RUNNING` ;
   les dépendances manquantes, ambiguës ou cycliques bloquent toute la
   vague. Les Apps `planned`/`disabled` sont également bloquantes.
   Le premier échec de démarrage ou du health gate **interrompt la vague**
   pour éviter de poursuivre vers des consommateurs non fonctionnels.

L'ancien `restore-app-set.sh` réutilise le même fichier d'Apps
optionnelles et les exclut par défaut. Ce script continue de restaurer
des Apps STOPPED, il **ne sait pas redémarrer** des Apps RUNNING ; le
nouvel orchestrateur ci-dessous remplit ce besoin spécifique.

## Contrôles locaux sans GitHub Actions

Depuis une copie locale du dépôt disposant de `python3`, `pytest` et `just` :

```bash
just truenas-catalog-v2-test
```

La cible exécute la compilation Python et les contrats de planification, vagues,
Vaultwarden. Elle n'utilise aucun runner GitHub, ne contacte pas TrueNAS et
n'installe aucune dépendance. Pour la validation complète avant publication,
exécuter séparément `just quality` sur l'environnement de développement
disposant de `mise` et des outils déclarés. Un test local réussi **ne remplace
pas** la validation réelle `--check` sur TrueNAS.

## Vérification des dépendances du core

Le préflight calcule `coreDependencyBlockers` depuis les seules relations
`entityRef` identifiées dans Backstage et les états `app.query` TrueNAS.
Pour chaque App RUNNING de `coreRestartOrder`, une dépendance doit avoir
**exactement un** fournisseur TrueNAS identifié et ce fournisseur doit être
`RUNNING`. Un fournisseur absent, ambigu, `STOPPED`, `CRASHED` ou
`UNKNOWN` bloque **la vague core seulement**, avant tout arrêt/démarrage.
Le contrôle n'invente jamais d'identité d'App à partir du nom de service.

`coreDependencyBlockers` fait partie du rapport JSON et du `planHash` :
résoudre les blocages puis relancer `--check` pour une nouvelle empreinte.
L'absence de relations déclarées dans Backstage n'est pas une preuve de
santé : la couverture de l'inventaire doit être revue séparément.
Ce contrôle n'autorise aucun redémarrage dans cette PR.

## Protection des opérations concurrentes

Toute commande `--apply` prend un verrou exclusif du noyau Linux
(`flock`) sur `/mnt/cpool/var/nabla/restart/.catalog-v2-restart.lock`
**avant** la lecture de `app.query` et le calcul de `planHash`. Si une
autre exécution est en cours, la commande refuse d'intervenir ; le verrou
est libéré à la sortie, même sur erreur. Le répertoire est privé (`0700`),
le verrou et les journaux sont `0600` ; liens symboliques et fichiers
spéciaux ne sont pas acceptés comme verrou.

`--check` n’utilise aucun verrou et ne modifie **jamais TrueNAS** ; un
fichier de rapport est toutefois créé si `--output` est fourni. Son JSON indique
`selectedWaveReady` et `selectedWaveBlocker` pour la vague choisie.
Une dépendance ayant plusieurs fournisseurs Backstage est une **ambiguïté
bloquante** : ne pas déduire le service cible par nom.
Une App `STOPPED` non sélectionnée pour le core n'empêche plus la vague
core à elle seule. En revanche, une App `STOPPED` dont dépend la vague
facultative doit être soit incluse explicitement dans cette vague, soit
déjà `RUNNING` ; sinon le préflight `deferredDependencyBlockers` bloque. Le verrou protège
uniquement cet orchestrateur, pas les actions `midclt` manuelles externes.

## Préparation (lecture seule sur TrueNAS)

```bash
cd /mnt/cpool/compose/nabla-compose
PLAN="/tmp/nabla-v2-core-$(date +%s%N).json"
sudo python3 scripts/truenas/restart-catalog-v2-apps.py --check \
  --output "$PLAN"
sudo jq '{selectedWave,selectedWaveReady,selectedWaveBlocker,planHash,
          counts,coreDependencyBlockers,missingRunningSecrets,unverifiedRunningSecrets,
          nonBlockingGatus,runningDeferredExcluded,deferredLast}' "$PLAN"
```

Les sorties `--output` sont créées exclusivement (permissions `0600`) :
**ne pas réutiliser un nom de fichier existant**. Les exemples génèrent un
fichier distinct pour chaque vague. Contrôler le champ `selectedWaveReady`
ainsi que `selectedWaveBlocker` avant toute intervention.

Un snapshot `--apps-json` ne peut **jamais** être marqué
`selectedWaveReady=true`, même si aucun secret n'est attendu. L'autorisation
opérationnelle doit être recalculée par `--check` en direct sur TrueNAS.

Le mode `--apps-json` est un diagnostic **hors ligne** : la présence des secrets
sur l'hôte TrueNAS n'y est pas vérifiée. Les secrets concernés portent le statut
`not-checked` et figurent dans `unverifiedRunningSecrets` /
`unverifiedDeferredSecrets` (ou `gatusSecretUnverified`). Ce n'est **pas**
une preuve de fichier manquant et ce n'est **jamais** une autorisation
d'exécuter `--apply`.

`planHash` identifie **les états de tous les TrueNAS Apps**, la révision
du catalogue, les preuves de secrets et **la vague sélectionnée** ; il change
dès qu'une App change d'état ou que la vague diffère. `--apply` recalcule depuis `app.query` pour éviter
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
HASH="$(sudo jq -r .planHash "$PLAN")"
sudo python3 scripts/truenas/restart-catalog-v2-apps.py --apply \
  --expected-plan-hash "$HASH" \
  --acknowledge-downtime I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART
```

Ceci occasionne de vraies interruptions. **Ne pas exécuter actuellement** :
les 13 secrets manquent. Le préflight refusera sans arrêt d'Apps.
L'exécution garantit seulement un arrêt/démarrage de chaque App dans son
périmètre et l'exécution du health gate Docker existant : cela ne garantit
ni l'accès métier de bout en bout, ni Vaultwarden, ni les sondes réseau.

Une fois le core accepté, relancer `--check` pour capturer un **nouveau**
`planHash` : la première vague a changé l'état du système. Pour les autres
vagues, utiliser **une seule** des options mutuellement exclusives :

```bash
# Diagnostiquer Gatus avant son activation ; si CRASHED, le préflight refuse.
PLAN="/tmp/nabla-v2-gatus-$(date +%s%N).json"
sudo python3 scripts/truenas/restart-catalog-v2-apps.py --check --include-gatus \
  --output "$PLAN"
HASH="$(sudo jq -r .planHash "$PLAN")"
sudo python3 scripts/truenas/restart-catalog-v2-apps.py --apply \
  --include-gatus --expected-plan-hash "$HASH" \
  --acknowledge-downtime I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART

# Vague facultative : autorise uniquement les Apps STOPPED, non planned/disabled.
PLAN="/tmp/nabla-v2-deferred-$(date +%s%N).json"
sudo python3 scripts/truenas/restart-catalog-v2-apps.py --check --include-deferred \
  --output "$PLAN"
HASH="$(sudo jq -r .planHash "$PLAN")"
sudo python3 scripts/truenas/restart-catalog-v2-apps.py --apply \
  --include-deferred --expected-plan-hash "$HASH" \
  --acknowledge-downtime I_ACCEPT_SEQUENTIAL_TRUENAS_RESTART
```

Avant une vague facultative, examiner explicitement le graphe prévu :

```bash
sudo jq '{selectedWave,selectedWaveReady,deferredStartOrder,
          deferredDependencyBlockers,plannedOrDisabledDeferred,
          missingDeferredSecrets,unverifiedDeferredSecrets}' "$PLAN"
```

La liste `deferredLast` reste l'inventaire des Apps déclarées
facultatives ; **seule `deferredStartOrder` est exécutable**. Un graphe
incomplet ne doit jamais être reconstitué par heuristique de noms.

**Recalculer `HASH` après chaque `--check`**, avant le `--apply` correspondant.
Chaque `--include-*` sélectionne **seulement** sa vague ; aucune des deux
ne redémarre le core. La première vague reste le comportement par défaut
sans option. Les 13 secrets runtime manquants bloquent le core, mais ne
bloquent pas artificiellement une vague sans dépendance à ces Apps.
Les erreurs Gatus et des Apps facultatives sont consignées avec un
**exit code non nul** ; elles n'entraînent pas d'arrêt ou redémarrage
des applications du core. Toute erreur core arrête immédiatement sa vague. Le journal JSONL sous
`/mnt/cpool/var/nabla/restart` enregistre les actions et résultats,
sans variables d'environnement ni contenu de secrets.

**Contraintes :** root requis pour `--apply`, snapshot figé par
`planHash`, listes d'App ID exactes, `app.stop` et `app.start`
via TrueNAS middleware uniquement. Aucun usage `apt`, aucun
redémarrage du TrueNAS hôte, aucun stockage de mot de passe.

## Diagnostic Vaultwarden CLI lent

L'inventaire utilise dorénavant un délai par requête borné et configurable
(default 90 s, maximum 300 s) ; aucune donnée secrète n'est renvoyée :

```bash
python3 scripts/secrets/inventory_vaultwarden.py --timeout-seconds 120
```

Un timeout indique l'absence de confirmation (et non l'absence de secrets).
Vérifier `bw --version` et `bw status | jq -r .status` **sans**
afficher `BW_SESSION`. Ne pas exécuter `bw list items` sans filtres
en sortie standard destinée aux journaux ou au support.
