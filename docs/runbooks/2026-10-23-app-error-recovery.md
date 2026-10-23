# Réparer les Apps TrueNAS en erreur — séance du 23 octobre 2026

**Objectif :** remettre LiteLLM puis Scrutiny et OpenRAG en service sans
masquer les causes avec un redéploiement massif. Les diagnostics sont
en lecture seule ; chaque commande de mutation est isolée et soumise à
validation opérateur. Ne jamais committer ni coller les tokens dans un log,
une issue ou dans ChatGPT.

## Ce que prouvent les logs fournis

- 06:41, 06:47, 06:52, 07:17 et **08:32** : LiteLLM `app.up` bloqué
  avant le démarrage par l'absence de
  `/mnt/cpool/secrets/runtime/litellm/.env.secrets`.
- 06:57 et 07:18 : Scrutiny `app.up` cherche encore
  **`/mnt/cpool/scrutiny/.env.secrets`**, ancien chemin, alors que
  `apps/scrutiny/compose.yml` déclare
  `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets`. Le manifeste
  réellement chargé par TrueNAS est probablement ancien : vérifier
  la configuration de l'App, ne pas créer un second secret divergent.
- 07:25 : `openrag-backend` est `unhealthy`. Le journal Compose
  ne fournit pas l'exception de l'application ; inspecter les logs
  localement, la dépendance Langflow/OpenSearch et le fichier
  `/mnt/cpool/openrag/.env.secrets`.
- Les autres erreurs historiques du journal, notamment Sentry,
  Scrutiny avant octobre ou Docker qui refuse de stopper certains
  conteneurs en septembre, **ne démontrent pas** leur état au 23 octobre.

## 0. Corriger le test qualité et obtenir la preuve de configuration

La PR #271 corrige le test `mise.lock` : les sous-tables TOML sont
**littéralement** nommées `platforms.linux-x64` et non
`platforms -> linux-x64`. Ce changement ne modifie pas les sommes
SHA-256 publiées. Tester sur un worktree isolé avant le merge :

```bash
cd /mnt/cpool/compose/nabla-compose
git status --short
git fetch origin feat/fast-batch-talos-k8s-services-20261023
git worktree add --detach /mnt/cpool/compose/nabla-pr271-check FETCH_HEAD
cd /mnt/cpool/compose/nabla-pr271-check
just upgrade-runtime-test
just truenas-ai-recovery-test
```

**Ne pas appliquer une mise à jour TrueNAS à partir de ce worktree** :
l'App peut monter des fichiers du checkout canonique
`/mnt/cpool/compose/nabla-compose`. Une fois les corrections
review/merge, exécuter les commandes sur `master` propre.

## 1. Inventaire d'erreurs en lecture seule

Depuis le checkout canonique TrueNAS :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo midclt call app.query |
  jq '[.[] | {id, state, upgrade_available, image_updates_available}]'
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check litellm
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check scrutiny
sudo bash scripts/truenas/diagnose-stuck-apps.sh --check \
  --app litellm --app scrutiny --app openrag
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check
```

Le nouveau script rapporte uniquement état/conteneur/présence de noms de
clés/permissions. Il **n'imprime jamais les valeurs** ni les logs Docker.
Les erreurs de permissions root ou fichier 0600 sont bloquantes. L'état
d'une App retourné comme `UNVERIFIED` signifie inconnu, pas `RUNNING`.
Tester également les stockages avant toute opération.

## 2. LiteLLM P0 — restaurer le secret canonique

**Ne jamais créer un `.env.secrets` vide** et ne pas placer la master
key dans Git ou dans la configuration Hermes.

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check litellm
command -v bw || echo 'Bitwarden CLI absent : vérifier la configuration opérateur'
bash scripts/truenas/configure-bitwarden-cli-local.sh --check
```

Le manifeste Vaultwarden utilise l'item exact
`nabla/prod/litellm` dans le dossier `TrueNAS`. Préserver
`LITELLM_MASTER_KEY`, `LITELLM_SALT_KEY`, `LITELLM_IDE_API_KEY`,
`REDIS_URL` et `LANGFUSE_SECRET_KEY`. `ANTHROPIC_API_KEY` est
facultative jusqu'à son provisionnement réel : **ne pas inventer sa
valeur** ; ne pas activer Hermes/Opus cloud en son absence.

Si un ancien secret local valide existe, envisager uniquement après
revue `sudo bash scripts/truenas/bootstrap-repository-env-files.sh
--stage-existing litellm` (sans détruire l'ancien). Sinon, depuis la
session de l'opérateur **non-root** qui a accès à Vaultwarden :

```bash
# Dans un shell privé, après bw login / bw unlock.
# Ne jamais afficher ni partager BW_SESSION.
export BW_SESSION="$(bw unlock --raw)"
python3 scripts/secrets/materialize_runtime.py --app litellm --install
unset BW_SESSION

sudo stat -c '%U:%G %a %s %n' \
  /mnt/cpool/secrets/runtime/litellm/.env.secrets
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check
```

Résultat attendu : propriétaire `root:root`, permissions `600`,
fichier non vide, noms des clés obligatoires disponibles.
Si les contrôles passent, **autoriser explicitement** l'action isolée :

```bash
# Distinguer STOPPED de RUNNING : ne pas tirer de nouvelle image inutilement.
STATE="$(sudo midclt call app.query '[["id","=","litellm"]]' |
  jq -r '.[0].state // "MISSING"')"
case "$STATE" in
  STOPPED) sudo midclt call -j app.start litellm ;;
  RUNNING) sudo midclt call -j app.redeploy litellm ;;
  *) echo "LiteLLM state=$STATE : diagnostiquer avant mutation" >&2 ;;
esac
sudo midclt call app.query '[["id","=","litellm"]]' |
  jq '[.[] | {id,state,active_workloads}]'
sudo docker inspect litellm |
  jq '.[0] | {state: .State.Status, health: .State.Health.Status,
               exitCode: .State.ExitCode, restarts: .RestartCount}'
curl -fsS --connect-timeout 3 --max-time 8 \
  http://127.0.0.1:4000/health/liveliness
```

Si l'App échoue **après** cette étape, lire sur TrueNAS les logs locaux
(`sudo docker logs --tail 100 litellm`), en supprimant tous tokens,
URL privées et fragments de prompts avant partage. Distinguer :
fichier absent, erreur YAML/modèle provider, base PostgreSQL/Redis ou
clé de routage. En particulier ne pas réessayer indéfiniment
`app.redeploy` si les credentials cloud non fournis provoquent une
erreur de validation LiteLLM : corriger le profil ou attendre les clés.

## 3. Scrutiny P1 — corriger token ET ancien chemin déclaré

```bash
sudo bash scripts/truenas/diagnose-influxdb.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check scrutiny
sudo bash scripts/truenas/bootstrap-scrutiny-influxdb.sh --check
sudo bash scripts/truenas/diagnose-scrutiny.sh --check
```

Le secret attendu est `nabla/prod/scrutiny` dans Vaultwarden et
`/mnt/cpool/secrets/runtime/scrutiny/.env.secrets` sur TrueNAS.
Il doit contenir `SCRUTINY_WEB_INFLUXDB_TOKEN` et le marqueur de
portée v2. Si la configuration d'App chargée cherche encore le chemin
`/mnt/cpool/scrutiny/.env.secrets`, **ne pas dupliquer le token**
sous les deux chemins : il faut réconcilier le Custom App Compose.

Deux voies, à sélectionner après diagnostic :
- secret existant et compatible → vérifier l'item Vaultwarden,
  `python3 scripts/secrets/materialize_runtime.py --app scrutiny --install`
  en tant qu'opérateur non-root authentifié ;
- token de portée ancienne ou manquant → revoir
  `bootstrap-scrutiny-influxdb.sh --check` et la procédure de rotation
  `SCRUTINY_TOKEN_ROTATE=1` avec token admin InfluxDB **sans affichage**.
  Ne pas écraser l'ancien token par défaut.

Le déploiement déclaratif est déjà prévu par
`scripts/truenas/deploy-scrutiny.sh`. Il vérifie InfluxDB, les disques
SMART, le fichier canonique, puis met à jour la définition TrueNAS :

```bash
sudo bash scripts/truenas/deploy-scrutiny.sh --check
# Seulement si vérifications et plan de cutover sont approuvés :
# sudo env SCRUTINY_CUTOVER_APPROVED=1 \
#   bash scripts/truenas/deploy-scrutiny.sh --apply
```

Un état TrueNAS `STOPPED` ou `CRASHED` peut exiger une
réconciliation de l'App avant que le helper autorise `--apply` :
**ne pas supprimer l'App ni le dataset** sans inventorier les données.

## 4. OpenRAG P1 — dépendances avant restart

```bash
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
sudo midclt call app.query |
  jq '[.[] | select(.id == "openrag" or .id == "opensearch"
                    or .id == "langflow" or .id == "docling")
          | {id,state,active_workloads}]'
sudo docker inspect openrag-backend |
  jq '.[0] | {state: .State.Status, exitCode: .State.ExitCode,
               health: .State.Health.Status,
               oomKilled: .State.OOMKilled}'
```

Si `openrag-backend` existe, examiner localement
`sudo docker logs --tail 100 openrag-backend` **avec expurgation avant
partage**. Vérifier les accès réseau `opensearch:9200` et
`langflow:7860` depuis le réseau intranet, les identifiants OpenSearch,
le montage en lecture seule `/mnt/cpool/bababou` → `/mnt/bababou`
et le healthcheck `http://127.0.0.1:8000/health`.
Ne pas recréer un index/vector store ni supprimer le dataset.
Une erreur de healthcheck seule ne justifie pas de réinstaller Docling.

## 5. Puis reprise des migrations et upgrades

Seulement lorsque **LiteLLM démarre, Scrutiny est cohérent, les
dépendances OpenRAG sont validées**, exécuter :

```bash
just upgrade-runtime-test
sudo bash scripts/truenas/finish-migrations-20261024.sh --check
# Preview de l'inventaire d'images réellement mises à jour :
sudo python3 scripts/truenas/fast-bulk-redeploy-apps.py \
  --check --scope applications --parallel 4
```

Le script de redéploiement massif est une **opération de refresh d'images
et de restart** ; il ne corrige ni les fichiers de secret manquants,
ni les tags `latest` opaques, ni le catalogue de versions PHP/Python.
La stratégie d'upgrade Talos/K8s parallèle se trouve dans le runbook
`2026-10-23-fast-batch-migration.md`, à exécuter séparément
depuis la workstation.

En cas de nouvel échec d'App, relever seulement :
nom d'App, état TrueNAS, statut santé, code sortie, horodatage, type
d'erreur expurgé. Mettre à jour le diagnostic avant un nouveau restart.
