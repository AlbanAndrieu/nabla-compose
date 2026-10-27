# 27 octobre 2026 — Ressources RUNNING, DefectDojo DEPLOYING, Vaultwarden et H-05/H-06

## Statut de collecte du catalogue

Le référentiel Backstage v2 versionné comporte **154 entités**, dont
**151 Component/Resource** et **141 mappings Compose**. Ces objets sont
*déclaratifs* ; ils ne constituent pas des mesures runtime.

Le collecteur `scripts/truenas/collect-service-resource-evidence.py`
produit désormais un JSON privé `nabla-service-resources/v1`, enrichi
des métriques CPU, RAM, mémoire GPU lorsqu'attribuable, couche écrivable
Docker et datasets ZFS. Il inspecte **Docker ps RUNNING uniquement**.
La clé `coverage` compte les conteneurs détectés, associés ou non
au catalogue et indique si l'inventaire était borné. La liste
`unmapped_running_containers` donne les noms et mesures disponibles
des conteneurs sans correspondance certaine. Aucun conteneur
introuvable n'est qualifié de `DOWN` ; l'absence n'est pas une valeur 0.

**Réception opérateur du 27 octobre (capture du 26 octobre 23:37 UTC)** :
`resources-20261026T233659Z.json` créé dans
`/mnt/cpool/var/nabla/service-resources` ; Docker **144 RUNNING**,
**92 mappés**, **52 non mappés**, `inventory_complete=true`,
**151 entités de service** dans le rapport, GPU indisponible sur
TrueNAS. Cela **prouve la collecte de l'inventaire runtime**, pas
que chaque mesure CPU/RAM/ZFS a été reçue pour chacun des 144
conteneurs. L'agent GitHub ne peut pas lire ce JSON local.

Pour les 52 conteneurs non mappés, la prochaine version du relevé
inclut `compose_project`, `compose_service` et
`mapping_issue` (identités contrôlées et expurgées),
afin de corriger les mappings exacts au lieu d'inférer un service
depuis son nom. Le rapport existant contient au minimum les noms
et consommations CPU/RAM disponibles. Il ne faut ni écrire
des chiffres imaginaires dans
`catalog/generated/entities.json` ni commiter un relevé périmé ou
privé dans Git. L'opérateur générera un instantané `0600`
pour import dans les cartes OWNER de nabla-site-alban PR #262.

```bash
cd /mnt/cpool/compose/nabla-compose
sudo install -d -o root -g root -m 0700 /mnt/cpool/var/nabla/service-resources
sudo python3 scripts/truenas/collect-service-resource-evidence.py \
  --check --host truenas \
  --output "/mnt/cpool/var/nabla/service-resources/resources-$(date -u +%Y%m%dT%H%M%SZ).json"
```

Pour comparer une VM/hôte GPU différent, exécuter le collecteur
sur cet hôte : l'absence de NVIDIA sur TrueNAS ne signifie pas
`0 MiB GPU`. Le stockage ZFS partagé est présenté comme
un dataset partagé et jamais comme une consommation exclusive.

## P0 — DefectDojo DEPLOYING et deux URLs indisponibles

**Preuve récente opérateur :** Custom App `defectdojo` en
`DEPLOYING`; `http://172.17.0.24:31085/` **et**
`https://defectdojo.int.albandrieu.com/` inaccessibles.

Le DNS privé avait été validé précédemment, mais ne prouve
aucune disponibilité actuelle du port. Le Compose impose
`defectdojo-uwsgi depends_on defectdojo-initializer:
service_completed_successfully`. Si l'initializer reste
en cours d'exécution ou sort avec erreur, le backend Django,
puis le frontend Nginx, peuvent rester absents.
La pression mémoire/OOM connue est un autre risque :
ne pas la masquer par des redeploys répétitifs.

```bash
cd /mnt/cpool/compose/nabla-compose
sudo python3 scripts/truenas/diagnose-defectdojo-deploying.py --check
sudo python3 scripts/truenas/diagnose-defectdojo-deploying.py \
  --check --include-log-classes
sudo bash scripts/truenas/preflight-defectdojo.sh
```

Le premier contrôle lit uniquement `midclt app.query`,
l'état/exit-code/OOM/health des cinq conteneurs attendus,
et l'état HTTP local. Le second examine une fenêtre de logs
bornée **sans afficher les logs**, et retourne seulement des
classes telles que `database_connection`,
`migration_or_initializer`, `filesystem_permission`
ou `memory_kill`.

**Décision selon la preuve :**
- `initializer_running` : attendre/diagnostiquer cette étape,
  sans toucher à Traefik ou au compte admin.
- `initializer_failed` : vérifier connexion PostgreSQL,
  migrations et permissions ; ne pas `DROP` la base.
- `OOMKilled=true` : stabiliser RAM, JVM, Docker et VM.
- initializer `exited(0)` puis uWSGI absent : regarder la
  dépendance Compose et les conteneurs.
- uWSGI + Nginx `running` mais HTTP absent : seulement
  alors examiner le bind :31085, les réseaux et Traefik.
- `DJANGO_UNAVAILABLE` sur le helper admin est attendu si
  uWSGI n'est pas prêt ; ne pas tenter une rotation du mot de passe
  avant le retour du backend.

## DefectDojo — analyse des logs initializer reçus

La capture d'initializer fournie le 27 octobre montre :

- 21:04 CET : `172.17.0.24:5432` accessible ;
- 21:07 CET : test de base PostgreSQL réussi ;
- 22:25 CET : triggers d'audit `pghistory` activés et
  migrations Django indiquées comme déjà appliquées ;
- `Admin user already exists; skipping first-boot setup` ;
- dernière ligne fournie :
  `Initializing non-standard permissions`.

**Ni code de sortie 0 ni erreur explicite** ne figurent dans
cette capture. Le délai important ne prouve pas un blocage
permanent : vérifier l'état Docker actuel de
`defectdojo-initializer` et, si toujours actif, la présence
d'une attente PostgreSQL. **Aucun DROP DATABASE** ni
rotation des mots de passe n'est justifié par ces logs.

```bash
sudo python3 scripts/truenas/diagnose-defectdojo-deploying.py \
  --check --include-log-classes
sudo python3 scripts/truenas/diagnose-defectdojo-postgres-waits.py --check
```

Le diagnostic SQL ne restitue que des catégories
`state/wait_event_type/wait_event`, le nombre de sessions et
d'attentes et leur durée. Il ne divulgue aucune requête SQL
ni identifiant. En cas de `LOCK_WAIT_OBSERVED`, examiner
la session bloquante **avant** un redémarrage de DefectDojo.

## Vaultwarden — preuves distinctes du déploiement

`config/secrets/manifest.json` définit les objets
`nabla/prod/code`, `nabla/prod/openrag`,
`nabla/prod/defectdojo`. Une édition manuelle d'env runtime
n'implique aucune mise à jour du coffre.

Depuis une session **non-root** avec `BW_SESSION` déjà
déverrouillée, et avec un `sudo -n cat` autorisé pour lire
le fichier runtime root-only :

```bash
VENV_PYTHON="$HOME/.cache/nabla-compose/dev-venv/bin/python"
for app in code openrag defectdojo; do
  "$VENV_PYTHON" scripts/secrets/compare_vaultwarden_runtime_readonly.py \
    --check --app "$app"
done
```

Le script ne divulgue aucun secret ; il compare précisément
chaque champ de manifest avec les valeurs `.env.secrets`
avec `hmac.compare_digest` et retourne `MATCH`, `DRIFT`
ou `UNVERIFIED`. Il **ne synchronise pas** Vaultwarden :
c'est la **cache de la CLI `bw`**, pas une preuve temps réel du
serveur. Aucun `bw edit`, rotation, installation ni
`materialize_runtime --install` n'est exécuté. Un coffre
verrouillé ou `sudo -n` indisponible produit `UNVERIFIED`.

### Résultat Vaultwarden du 27 octobre

L'inventaire CLI **avant mise à jour du classificateur** retournait :
`code=VAULT_ITEM_NOT_UNIQUE`,
`openrag=VAULT_ITEM_NOT_UNIQUE` ; cette catégorie
regroupait objets manquants **et** doublons. Le code distingue
maintenant `VAULT_ITEM_MISSING`,
`VAULT_ITEM_IN_OTHER_FOLDER` et
`VAULT_ITEM_DUPLICATED_*` via une seconde recherche sans
filtre de dossier, toujours sans afficher les objets.

Pour `defectdojo`, cinq secrets applicatifs sont `MATCH`.
`DD_ADMIN_USER=DRIFT` et
`DD_ADMIN_PASSWORD=UNVERIFIED` : le résultat ne révèle
aucun mot de passe. La nouvelle colonne
`unverified_reasons` distingue une valeur absente/vidée
dans l'objet Vaultwarden d'une clé runtime absente/vidée.
Le hash Django reste indépendant et le login n'est pas
opérationnel tant qu'uWSGI n'est pas prêt.

```bash
# Après la fin du build FastAPI en cours, sous l'utilisateur BW déverrouillé.
bw sync
VENV_PYTHON="$HOME/.cache/nabla-compose/dev-venv/bin/python"
for app in code openrag defectdojo; do
  "$VENV_PYTHON" scripts/secrets/compare_vaultwarden_runtime_readonly.py \
    --check --app "$app"
done
```

`bw sync` actualise la **cache locale CLI** ; il ne modifie
pas les objets distants. Ne jamais copier de secret dans un ticket
ou régénérer les clés Django/AES256 pendant l'initialisation.

## Prometheus / Akvorado — collecte H-05 / H-06

Depuis TrueNAS, la vérification readiness et le rapport
consolidé sont **indépendants** :

```bash
sudo python3 scripts/truenas/diagnose-fastapi-prometheus-runtime.py --check
bash scripts/truenas/observe-prometheus-akvorado-lan.sh --observe-seconds 20
```

Le dernier état rapporté par l'opérateur était
`Prometheus 21/28 targets UP` et une API ayant déjà refusé
des connexions ; cela ne prouve pas son état présent.
Pour Akvorado, la configuration Orchestrator montée correspond
au YAML Git, mais les derniers flux observés comportaient
des erreurs de métadonnées `ifIndex` et aucune insertion SQL
confirmée. Le rapport sépare :

- HTTP readiness/targets Prometheus ;
- Inlet/Outlet NetFlow, rejets actifs
  `metadata missing` et nouveaux lots ClickHouse ;
- preuve de lignes SQL `NOT_VERIFIED` (indépendante des compteurs).

En cas de rejets persistants :

```bash
sudo bash scripts/truenas/diagnose-akvorado-config.sh --check
python3 scripts/truenas/check-akvorado-metadata-config.py --check
python3 scripts/truenas/diagnose-akvorado-flow.py \
  --strict --fail-on-blocked --observe-seconds 30
```

Pas de flux artificiel pfSense, de changement de secrets ni de
redeploy généralisé sur la seule base d'un compteur historique.

## Acceptation

- Rapport privé et horodaté portant CPU/RAM/ZFS pour les
  workloads RUNNING, plus liste explicite des non-mappés.
- DefectDojo `RUNNING` et HTML HTTP local rétabli avant
  diagnostic de l'authentification admin et de Traefik.
- Vaultwarden parité contrôlée, dérives isolées et corrigées
  avec source de vérité confirmée.
- Prometheus targets actuelles visibles, Akvorado sans rejets
  actifs puis preuve de lignes SQL persistées.
- Les changements ont été commités sans lancer de quality gate,
  conformément au souhait opérateur ; runtime **NON VALIDÉ**.
