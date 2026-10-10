# TrueNAS — acceptation progressive DSOMM, Gatus, Sentry, Scrutiny

Date : 2026-10-10 · PR #251 · Procédure **lecture seule par défaut**.

> Ce runbook ne valide **aucun** runtime à lui seul. Un état déclaré
> `RUNNING` n'est pas une preuve de santé, de persistance ou de récupération
> après reboot. Ne pas redémarrer, recréer, modifier des secrets ni lancer un
> `--apply` depuis les diagnostics.

## Préconditions et ordre

La quality gate locale est bloquante avant un changement de service :
`just loop` puis `just pre-push` sur un HEAD propre. L'ancien échec
`opencre-contract` venait d'une assertion de shebang contradictoire ;
ne pas relâcher `check-shebang-scripts-are-executable` pour contourner
une régression de test.

Depuis le checkout TrueNAS
`/mnt/cpool/compose/nabla-compose`, collecter un état compact, sans secrets :

```bash
git status --short --branch
git rev-parse --short HEAD
sudo midclt call app.query |
  jq -r '.[] | select(.id=="dsomm" or .id=="gatus" or .id=="sentry" or .id=="scrutiny") | [.id,.state] | @tsv'
sudo bash scripts/truenas/triage-post-reboot-apps.sh
```

La sélection `app.query` ne conclut pas qu'un service est absent lorsque
l'ID réel diffère du nom du dépôt ; dans ce cas, recouper avec
`midclt app.query` complet et les labels Compose.

## 1. DSOMM — première acceptation à traiter

Contrat déclaré : DSOMM 4.4.1, port HTTP privé `172.17.0.24:31088`,
seed/evidence dans `/mnt/cpool/dsomm/state`, baseline en profil `manual`.
Ne pas confondre avec OpenCRE, qui reste `planned` et bloque les images
mutables en mode `--apply`.

```bash
python3 -m pytest -q tests/test_dsomm_contract.py --tb=short
sudo bash scripts/truenas/deploy-dsomm.sh --check
curl -fsS -o /dev/null -w 'dsomm_http=%{http_code}\n' \
  --connect-timeout 2 --max-time 8 http://172.17.0.24:31088/ || true
sudo stat -c '%a %U:%G %n' /mnt/cpool/dsomm/state 2>/dev/null || true
```

### Diagnostic du conteneur existant — Caddy et capabilities

Preuves opérateur du 10 octobre : `dsomm` redémarre avec exit 255
(1109 redémarrages), `OOMKilled=false`, `CapDrop=["ALL"]`,
`CapAdd=null`, `no-new-privileges:true`; logs répétés :
`exec /usr/bin/caddy: operation not permitted`.

Le Compose canonique conserve `cap_drop: [ALL]` et
`cap_add: [NET_BIND_SERVICE]` car Caddy embarque une file capability.
Cela **n'apparaît pas dans le conteneur inspecté**, ce qui justifie un
contrôle de divergence entre **source**, **Custom App persistée** et
**runtime**. Aucun besoin établi de `privileged:true`.

```bash
# Source déclarée (configuration uniquement ; ne pas imprimer les variables).
python3 - <<'PY'
import yaml
with open("apps/dsomm/compose.yml", encoding="utf-8") as source:
    service = yaml.safe_load(source)["services"]["dsomm"]
for key in ("image", "cap_drop", "cap_add", "security_opt", "restart"):
    print(f"declared.{key}={service.get(key)}")
PY

# Config réellement appliquée, sans Env ni mounts sensibles.
sudo docker inspect dsomm --format \
  'runtime.name={{.Name}} image={{.Config.Image}} exit={{.State.ExitCode}} error={{.State.Error}} oom={{.State.OOMKilled}} restarts={{.RestartCount}} cap_add={{json .HostConfig.CapAdd}} cap_drop={{json .HostConfig.CapDrop}} security_opt={{json .HostConfig.SecurityOpt}}'

# Connaître l'App TrueNAS, sans exposer custom_compose_config (peut contenir
# des substitutions de secrets). L'état STOPPED est distinct du restart Docker.
sudo midclt call app.query '[["id","=","dsomm"]]' |
  jq '[.[] | {id,state,version,active_workloads:{containers:(.active_workloads.containers // 0)}}]'
```

**Arrêt de sécurité** : ne pas appliquer de `docker update`,
`docker restart`, `midclt app.start` ou `deploy-dsomm.sh --apply`
avant d'avoir confirmé l'origine de la définition qui ne contient
pas `NET_BIND_SERVICE`. L'action de réconciliation doit être explicite,
maintenir les fichiers `/mnt/cpool/dsomm/state`, et démontrer
`CapAdd=["NET_BIND_SERVICE"]` au runtime puis HTTP 31088 sain.

### Preuve du 10 octobre : DSOMM STOPPED (read-only)

Le `--check` opérateur a confirmé le seed 5.0.2 (22 activités et
22 évidences), l'image 4.4.1 locale, le Compose et les projections
synchronisés, le dataset non vide `cpool/dsomm` et un checkout propre.
Il s'est arrêté explicitement sur : `ERROR: dsomm: TrueNAS App is
STOPPED`. Aucune application n'a été démarrée, aucun état n'a été écrasé.

Étape de diagnostic suivante, **avant** tout `--apply` ou `app.start` :

```bash
sudo midclt call app.query '[["id","=","dsomm"]]' |
  jq '[.[] | {id, state, active_workloads, version}]'
sudo docker ps -a --filter label=com.docker.compose.project=ix-dsomm \
  --format '{{.Names}} {{.Status}}'
sudo stat -c '%a %U:%G %n' /mnt/cpool/dsomm/state \
  /mnt/cpool/dsomm/state/model.yaml \
  /mnt/cpool/dsomm/state/team-progress.yaml \
  /mnt/cpool/dsomm/state/team-evidence.yaml
```

La présence d'une App STOPPED **n'autorise pas** à remplacer sa
configuration automatiquement. Examiner d'abord les jobs récents
d'applications dans l'interface TrueNAS ou via `core.get_jobs` en
masquant les arguments (susceptibles de contenir des secrets).
Conserver les fichiers d'état et leurs empreintes pour comparaison.
Une reprise nécessitant des mutations doit être décidée séparément,
avec rollback des fichiers d'état et de la définition de l'App.

L'état `STOPPED` ou `MISSING` est un **résultat bloquant attendu du
--check**, pas un ordre de déploiement. Avant tout `--apply`, vérifier
provenance de l'image, état des modèles/seeds, volume et rollback.
**Done :** app `RUNNING`, HTTP prêt, modèles et évidence persistants,
contrôle fonctionnel humain. Ne passer `x-nabla.status` de `planned`
à `active` qu'après ces preuves.

### Acceptation runtime DSOMM confirmée — 10 octobre

Résultats vérifiés par l'opérateur : **12 tests DSOMM réussis**, **22
sous-tests réussis**, `deploy-dsomm.sh --check` sans erreur, capacité
Docker `CAP_NET_BIND_SERVICE` présente et `curl` HTTP **200** sur
`172.17.0.24:31088`. La réconciliation TrueNAS est fonctionnelle ;
aucun autre `--apply` ou redémarrage nécessaire. L'acceptation
`reboot accepted` reste **en attente** d'un futur test de reprise.

### Vérifications suivantes : Gatus, Sentry, Scrutiny

Le statut Gatus n'est pas encore confirmé. Depuis TrueNAS, recueillir
les observations sans lancer `app.start` ni `app.update` :

```bash
sudo midclt call app.query '[["id","=","gatus"]]' |
  jq '[.[] | {id,state,active_workloads:{containers:(.active_workloads.containers // 0)}}]'
sudo docker ps -a --filter label=com.docker.compose.service=gatus \
  --format '{{.Names}} {{.Status}}'
curl -sS -o /dev/null -w 'gatus_http=%{http_code}\n' \
  --connect-timeout 2 --max-time 8 http://172.17.0.24:8085/ || true
sudo stat -c '%U:%G %a %n' /mnt/cpool/gatus \
  /mnt/cpool/gatus/gatus.db 2>/dev/null || true
```

Après Gatus, les scripts de diagnostic Sentry et Scrutiny sont
lecture seule :

```bash
sudo bash scripts/truenas/diagnose-sentry.sh --check
sudo bash scripts/truenas/diagnose-scrutiny.sh --check
```

Ne pas publier de logs bruts contenant credentials ou valeurs
d'environnement. Corriger chaque défaut constaté indépendamment,
sans effet de bord sur d'autres Apps.

## 2. Gatus — historique et contrôles synthétiques

Contrat déclaré dans `apps/gatus/compose.yml` : stockage SQLite
`/mnt/cpool/gatus:/data`, historique `/data/gatus.db`.
Gatus interne n'est pas un substitut à l'observation externe de
`fastapi-sample.fastapicloud.dev`.

```bash
sudo midclt call app.query '[["id","=","gatus"]]' |
  jq -r '.[] | [.id,.state] | @tsv'
sudo docker ps -a --filter label=com.docker.compose.service=gatus \
  --format '{{.Names}} {{.Status}}'
sudo test -d /mnt/cpool/gatus && echo 'gatus_dataset=present'
sudo test -f /mnt/cpool/gatus/gatus.db && echo 'gatus_db=present'
```

**Done :** app `RUNNING`, UI/endpoint prêt, base persistante non vide,
checks suivis dans le catalogue, restauration/reboot testée avant toute
suppression d'ancienne configuration. Une DB absente peut être normale
avant le premier démarrage ; ne pas créer de placeholder manuellement.

## 3. Sentry — edge, migration et consommateurs

```bash
sudo bash scripts/truenas/diagnose-sentry.sh --check
curl -fsS --connect-timeout 2 --max-time 8 \
  http://172.17.0.24:9005/_health/ || true
```

Le diagnostic spécialisé est **lecture seule** ; il sépare le statut de
l'App, les jobs de migration, Relay, Kafka, Snuba/ClickHouse et la santé
edge. Le dernier smoke E2E historique ne dispense pas d'une vérification
du runtime actuel. Ne pas afficher les valeurs de
`/mnt/cpool/secrets/runtime/sentry/.env.secrets` ni
`.env.migrator.secrets`. Comparer seulement la provenance et les
présences de noms de clés. **Done :** edge et chaîne d'ingestion
actuellement sains ; réconciliation des secrets canoniques et épreuve
de reprise documentées.

## 4. Scrutiny — secrets, InfluxDB et SMART

```bash
sudo bash scripts/truenas/diagnose-scrutiny.sh --check
sudo midclt call app.query '[["id","=","scrutiny"]]' |
  jq -r '.[] | [.id,.state] | @tsv'
curl -fsS --connect-timeout 2 --max-time 8 \
  http://172.17.0.24:31054/api/health || true
```

Ne **pas** utiliser `--capture-startup` sans approbation explicite :
ce mode lance un conteneur temporaire. Ne pas copier ni réintroduire
l'ancien `/mnt/cpool/scrutiny/.env.secrets` sans analyse ;
l'emplacement canonique déclaré est
`/mnt/cpool/secrets/runtime/scrutiny/.env.secrets`.
**Done :** web et collector fonctionnels, InfluxDB accessible,
jeton validé sans impression de valeur, mesures SMART récentes et
reprise documentée.

## Séquencement de la suite

P0 : pre-push vert et changement commité ; P1 : DSOMM puis Gatus puis
Sentry puis Scrutiny, **une acceptation à la fois** ; P2 : Scanopy,
Joplin, AutoKuma ; P3 : Docling → OpenRAG → LiteLLM/workstation GPU.
Ne pas modifier une App pendant l'analyse d'une autre. Consigner
date, HEAD, ID d'App, check exécuté, état et preuve sans secrets
dans l'incident/roadmap correspondant.
