# OpenClaw Workstation — GitOps, LiteLLM et migration `nabla` (27 octobre 2026)

## Décision et périmètre

**Ordre impératif** : stabiliser LiteLLM Workstation `172.17.0.57:4000`,
puis inventorier la configuration OpenClaw non secrète, puis seulement
préparer la migration des routes vers LiteLLM TrueNAS
`172.17.0.24:4000`. Aucune bascule automatique ou restauration
des secrets, budgets, automations, sessions ou bases SQLite.

Le dépôt **privé** `AlbanAndrieu/nabla` suit historiquement
`env/home/dotfiles/.openclaw/**` ; sa règle `.gitattributes`
`env/home/dotfiles/** filter=git-crypt diff=git-crypt`
rend le contenu chiffré dans les blobs Git distants.
`nabla-compose` est **public**. Il est incorrect de copier
ou de publier ces blobs ou du contenu déchiffré sans revue manuelle.

## P0 — LiteLLM Workstation : appel non authentifié

Événement daté du 27/10/2026 : `GET /v1/models`,
`No api key passed in.`, `user_api_key=null`, 0 token, coût 0,
`requester_ip_address=172.17.0.24`, User-Agent
`litellm/1.106.4`. Il s'agit d'un **rejet de requête
sans clé avant modèle**, pas de 429. Ni IP ni User-Agent ne prouvent
l'identité exacte du client. Ne pas retirer l'authentification
pour rendre ce contrôle vert.

**Cause certaine trouvée dans le code** : le script
`scripts/truenas/diagnose-openrag-startup.sh` interrogeait
`http://172.17.0.57:4000/v1/models` sans clé, en acceptant 401
comme preuve de transport. Ce comportement génère inutilement
des traces d'authentification en échec (mais le script utilise
`curl`, tandis que l'événement ci-dessus a un User-Agent LiteLLM :
**ne pas affirmer que ce script a provoqué cette trace précise**).
Dans la PR #289 la sonde passe désormais par
`/health/liveliness` : endpoint anonyme non facturable.
Les tests existants OpenRAG sont réconciliés et un contrat
spécifique empêche le retour à `/v1/models` anonyme.

Le classifieur redacted
`scripts/truenas/diagnose-litellm-dashboard-auth.py`
reconnaît désormais `MISSING_CLIENT_API_KEY` seulement si
le message et l'absence de clé coïncident avec 0 token.
Aucun hash, ID, IP, User-Agent ni texte source ne sort.

### Garde de recette sans requête LLM

```bash
# Dans un worktree actualisé de la PR #289
just litellm-workstation-auth-contracts
just truenas-openrag-startup-test
```

En complément sur Workstation :
```bash
curl --noproxy '*' -sS -o /dev/null -w 'liveliness=%{http_code}\n' \
  --max-time 5 http://127.0.0.1:4000/health/liveliness
curl --noproxy '*' -sS -o /dev/null -w 'readiness=%{http_code}\n' \
  --max-time 5 http://127.0.0.1:4000/health/readiness
```

Sur TrueNAS, confirmer l'accès à cette **même** instance,
sans jeton ni inférence :
```bash
curl --noproxy '*' -sS -o /dev/null -w 'ws_liveliness=%{http_code}\n' \
  --max-time 5 http://172.17.0.57:4000/health/liveliness
```

Depuis une console TrueNAS sur un checkout mis à jour de #289,
un contrôle supplémentaire du conteneur LiteLLM **sans extraction
des valeurs** :

```bash
just litellm-workstation-upstream-auth-check
```

Le résultat contient uniquement la présence de
`LITELLM_IDE_API_KEY` et de
`LITELLM_FASTAPI_WORKSTATION_API_KEY` dans le conteneur
`litellm` TrueNAS, puis la liveness du proxy Workstation.
Cette vérification n'attribue pas automatiquement la trace
`litellm/1.106.4`. Si la clé manque, corriger sa
matérialisation privée et son injection dans le conteneur
**après revue explicite**, sans copier la valeur dans Git, la
sortie de terminal ou un ticket. Ne pas recréer le service
pour une simple preuve d'absence.

**Suivi P0 après un nouvel événement sans clé (soir du 27/10) :**

Le précédent préflight pouvait retourner `0` avec une clé
absente : il est maintenant **fail closed**. Le code
`truenas_upstream_key_state=missing_runtime_upstream_key`
signifie que l'une des deux variables de clé requises
est vide/absente dans le processus LiteLLM TrueNAS.
`all_present_unvalidated` signifie seulement **présence**,
pas validité ni scope. Si la clé manque, corriger la
matérialisation du fichier privé
`/mnt/cpool/secrets/runtime/litellm/.env.secrets`,
la correspondance du modèle dans `/app/config.yaml` et le
démarrage du conteneur après une revue des changements.
Ne pas afficher le fichier ni coller de valeurs de clé.

Le diagnostic publie aussi
`truenas_litellm_sdk_version` (ex. `1.106.4`)
depuis le conteneur `litellm`, sans modèle ni secret.
Comparer à l'UA `litellm/1.106.4` de la trace
`GET /v1/models` reçue par Workstation. Même si la
version est égale, **l'instance appelante n'est pas prouvée** :
le même SDK peut tourner dans un autre conteneur TrueNAS.

**Séquence d'attribution sans inférence :**
1. Sur TrueNAS uniquement : exécuter
   `just litellm-workstation-upstream-auth-check`.
2. Si `missing_runtime_upstream_key`, vérifier l'injection du
   secret en privé dans le conteneur et la configuration déclarée ;
   ne pas désactiver la protection de `/v1/models`.
3. Si `all_present_unvalidated`, examiner le consommateur
   qui génère la requête de catalogue, ses logs à l'instant
   du `litellm_call_id`, et la présence effective d'un
   header Bearer **sans en publier la valeur**. Une
   correspondance de version n'est qu'un indice.
4. Après correction runtime et déploiement contrôlé, prouver
   qu'aucun nouvel échec du même type n'arrive sur une
   période d'observation. Ne pas modifier les budgets
   OpenClaw pour une erreur de transport sans clé.

Source externe : https://docs.litellm.ai/docs/proxy/docker_quick_start
pour l'injection via `os.environ/...` et la séparation
entre clés de provider et clé d'appel au proxy.

Une réussite confirme un processus/réseau, pas la validité des
clés virtuelles OpenClaw ni la liste des modèles. Identifier
ensuite le client qui appelle `/v1/models` sans `Authorization`.
Pour un **catalogue fonctionnel**, ce client doit utiliser une clé
virtuelle scoped présente dans son magasin privé, et vérifier
que l'en-tête Bearer est réellement attaché. Vérifier
`LITELLM_IDE_API_KEY`, `LITELLM_FASTAPI_WORKSTATION_API_KEY`
et leurs scopes **par des états présence/absence seulement**,
sans lire le contenu. Ne jamais utiliser la master key comme
jeton d'une sonde ordinaire. Ne pas activer les modèles TrueNAS
manquants ou modifier les budgets pour résoudre ce 401.

**DONE P0** : aucun moniteur/versionné n'envoie
`/v1/models` anonyme ; le dernier appel sans clé reçoit
une identité d'appelant démontrée avant correction ;
liveness/readiness 200 au bon vantage point ; requêtes
`openclaw-main` réellement échouées et quotas analysés
séparément ; Workstation reste le modèle de vérité jusqu'au cutover.

## TrueNAS — filtre Compose project trop strict, seconde correction

Relevé opérateur après première correction de découverte :

- `just litellm-workstation-auth-contracts` :
  **29/29 PASS** (3 OpenRAG, 8 pytest, 18 upstream).
- `just litellm-workstation-upstream-auth-check` :
  `truenas_container_selection=compose_running_container_not_found`,
  `truenas_docker_container_status=not_inspected`,
  `truenas_upstream_key_state=unverified`,
  `workstation_liveliness=http_200`, code 2.

Le filtre `com.docker.compose.project=litellm` n'a renvoyé
aucun service running. Un projet Docker Compose créé par TrueNAS
peut avoir un autre nom ou être géré différemment.
**Le nom du projet et ses labels ne sont pas encore attestés** :
ne pas présenter cette hypothèse comme la cause prouvée du
`No api key passed in.` sur le proxy Workstation.

**Correction de code supplémentaire [skip ci] :**
`docker ps --filter name=litellm --filter status=running
--format '{{.ID}}|{{.Names}}'` fournit uniquement des noms et
identifiants internes ; le parser n'accepte comme candidat
que `litellm-litellm-N` (N entier positif), exige une seule
instance et refuse les lignes malformées. Les noms voisins
(`litellm-dashboard`, etc.) ne deviennent jamais candidats.
Le conteneur hérité `litellm` **ne peut plus servir de
cible implicite**, même via les helpers Python ; toutes les
inspections utilisent l'ID découvert, non imprimé.
Liveness Workstation et absence de secrets dans les sorties
sont conservées. Pas de modification de conteneur ou secrets.

```bash
# Sur le checkout TrueNAS mis à jour :
just litellm-workstation-auth-contracts
just litellm-workstation-upstream-auth-check
```

Si la sélection échoue encore, inspecter **uniquement** les
métadonnées pertinentes (jamais `docker inspect` complet) :
```bash
sudo docker ps --filter name=litellm --filter status=running \
  --format 'table {{.Names}}\\t{{.Status}}'
sudo docker inspect --type container \
  --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}' \
  litellm-litellm-1
```
Aucune valeur de `Env` n'est affichée. La deuxième commande
indique les éventuels labels pour expliquer le drift mais ne
constitue pas un contrôle des secrets.

Une sélection `selected/running` ne signifie
toujours **pas** que le client `GET /v1/models`
utilise une clé : le diagnostic vérifie uniquement
la **présence** des variables d'upstream, sans
envoi de requête au catalogue.

## TrueNAS — conteneur LiteLLM actif identifié, ancien conteneur arrêté

**Relevé opérateur :** `sudo docker ps -a --filter name=litellm`
identifie `litellm-litellm-1` `Up 3 days (healthy)` et
`litellm` `Exited (0) 3 months ago`. L'inspection
`sudo docker inspect --type container --format
'{{.State.Status}}' litellm` confirme `exited`.
**Cause du préflight Docker précédent identifiée** :
il avait codé en dur `litellm`, donc inspectait
l'ancien conteneur. La requête vers le proxy Workstation
répondait déjà `http_200` ; aucune variable runtime
du véritable conteneur `litellm-litellm-1` n'avait
encore été inspectée.

**Correction versionnée :**
1. Sélectionner `docker ps` filtré par les labels officiels
   Docker Compose `com.docker.compose.project=litellm` et
   `com.docker.compose.service=litellm`, plus
   `status=running`. Les labels sélectionnent le service,
   pas une chaîne de sous-nom arbitraire.
2. Exiger **une seule** instance running avec identifiant
   Docker hexadécimal et nom attendu (p. ex.
   `litellm-litellm-1`). Refuser les doublons, sorties
   malformées et changements d'état.
3. Inspecter son seul champ `.State.Status`, puis
   utiliser le **même ID interne** pour `docker exec`
   des deux noms de variables autorisés et la version
   du SDK. Ne jamais afficher l'ID, `Env` ou une clé.
4. Conserver un exit 2 si aucun conteneur valide n'est
   découvert, si les clés manquent, ou si Workstation
   n'est pas vivant. Un état `all_present_unvalidated`
   reste une preuve de présence et **non** d'authentification.
5. Pas de `docker start litellm`, `docker rename`,
   `docker compose up` ni modification d'image pour
   résoudre le problème de diagnostic.

```bash
# Contrats locaux d'abord, sans appel modèle :
just litellm-workstation-auth-contracts
# Depuis TrueNAS après synchronisation #289 :
just litellm-workstation-upstream-auth-check
```

Les diagnostics versionnés précédents de ce même runbook
restent utiles comme historique, mais toute référence à
`docker exec litellm` et `inspect litellm` désigne
désormais un **conteneur arrêté**, pas l'instance active.

Référence : https://docs.docker.com/reference/compose-file/services/
(labels `com.docker.compose.project` / `service`) et
https://docs.docker.com/reference/cli/docker/container/ls
(filtres label/status).

## TrueNAS → Workstation : inspection Docker indisponible (dernier relevé)

Le dernier `just litellm-workstation-upstream-auth-check`
exécuté sur TrueNAS a retourné
`workstation_liveliness=http_200` mais
`truenas_litellm_env.container=unavailable`,
`key_presence=unverified`, `truenas_litellm_sdk_version=unverified`,
et exit 2. Il prouve seulement la connexion à
LiteLLM Workstation. Il ne prouve aucune valeur de clé absente.
Le probe original regroupait tout échec de
`docker exec litellm python3 -c ...` en une seule classe,
sans afficher la cause.

**Correctif de diagnostic dans #289 :**
- `docker inspect --type container --format '{{.State.Status}}' litellm`
  fournit uniquement un état allowlisté. Aucune entrée `Env`
  ni secret Docker inspecté ou imprimé.
- La requête `docker exec` retourne désormais un
  `failure_class` fermé, déduit de `stderr` en mémoire :
  `docker_permission_denied`, `docker_daemon_unavailable`,
  `container_not_found`, `container_not_running`,
  `python3_missing_in_container`, `probe_python_failed`
  ou `docker_exec_failed`.
- Pas de redémarrage ou de contournement de l'authentification.
  Si la requête Docker échoue, le statut reste rouge.

Relancer après synchronisation du code :
```bash
just litellm-workstation-auth-contracts
just litellm-workstation-upstream-auth-check
```

Si le diagnostic reste ambigu, exécuter directement sur TrueNAS
ces **deux commandes métadonnées uniquement**, sans afficher
les variables d'environnement :

```bash
sudo docker ps -a --filter name=litellm --format 'table {{.Names}}\t{{.Status}}'
sudo docker inspect --type container --format '{{.State.Status}}' litellm
```

Interprétation : `container_not_found` implique de vérifier
le nom réel du conteneur ; `container_not_running` implique
un problème de lifecycle ; `python3_missing_in_container`
implique un probe non compatible avec l'image ; un `exec`
non autorisé doit être réparé par les permissions Docker,
pas par une master key LiteLLM.
**Ne pas appeler `docker inspect litellm` sans `--format`** :
le JSON complet peut contenir les valeurs de `Env`.

Référence Docker :
https://docs.docker.com/reference/cli/docker/container/exec

## Réception Workstation — preuves de tests du 27/10

L'opérateur a exécuté les premiers nouveaux gates :

- `just litellm-workstation-auth-contracts` et
  `just truenas-openrag-startup-test` : **bloqués car**
  `python3` pointe sur mise Python **3.14.9 sans `pytest`**.
  Aucun échec de test métier prouvé. Les gates sont maintenant
  équipés de `scripts/quality/run-pytest-local.sh` qui sélectionne
  un interpréteur déjà équipé de pytest ou émet une instruction de
  venv sans installer automatiquement de paquet.
- `openclaw-nabla-migration-test` : 3/5 PASS, deux erreurs
  `unsafe_writable_permissions` dues aux fixtures nouvellement
  créées avec le `umask` local. **Les deux tests configurent
  désormais explicitement le mode 0600.**
  `openclaw-nabla-migration-check` a terminé et trouvé
  les anciens fichiers de politique disponibles, sans contenu copié.
- `openclaw-digest-gitops-test` : 3/3 PASS.
- `openclaw-cron-parent-test` : 4/4 PASS ;
  `openclaw-cron-parent-check` : catalogue de 21 entrées,
  `hasMore=false`, aucune session `agent:cron:main`.
  Un test supplémentaire couvre ce catalogue exhaustif.

Les corrections GitHub ont été enregistrées après ces tests :
**leur nouvelle exécution locale n'est pas encore attestée**.

### Environnement pytest local

Ne pas installer pytest dans le Python `mise` global, ni
solliciter les GitHub Actions pour ces contrôles. Si aucun Python
local avec pytest n'est disponible :

```bash
python3 -m venv /tmp/nabla-pytest-venv
/tmp/nabla-pytest-venv/bin/python -m pip install pytest
NABLA_PYTEST_PYTHON=/tmp/nabla-pytest-venv/bin/python just litellm-workstation-auth-contracts
NABLA_PYTEST_PYTHON=/tmp/nabla-pytest-venv/bin/python just truenas-openrag-startup-test
```

L'installation de pytest requiert un index Python disponible et
une validation locale de la dépendance ; elle **ne change aucun
conteneur ni service**. Les contrats stdlib n'ont pas besoin de pytest.
Ne pas déclarer tous les tests `PASS` tant que les suites pytest
n'ont pas été exécutées.

### Sauvegardes HEARTBEAT — inventaire sans extraction

L'opérateur a retrouvé le `HEARTBEAT.md` git-crypt dans le clone
`nabla`, `~/.openclaw/workspace/HEARTBEAT.md.before-fix` et
une archive ancienne `openclaw-2026-08-04_0220.tar.gz`.
Les détails de restauration sont sous
`apps/openclaw/workstation/LEGACY_HEARTBEAT_RECOVERY.md`.

```bash
just openclaw-heartbeat-copies-test
just openclaw-heartbeat-copies-check
```

Le contrôle **ne lit aucun contenu**, n'inspecte pas le contenu
tar et ne déchiffre aucune clé. Il retourne 2 lorsqu'un fichier
présent est lisible par d'autres utilisateurs ou si aucune copie
n'a été trouvée. Si l'archive n'est pas sous
`~/openclaw-backups/`, lancer le script directement en passant
`--archive /chemin/prive/existant`, sans afficher la liste du
contenu de l'archive sur un canal public. Le mode archive
`0644` précédemment observé nécessite une revue locale avant
`chmod 600` par le propriétaire. Aucune permission n'a été modifiée.

## Validation Workstation actualisée — 27 octobre

Les nouveaux résultats communiqués par l'opérateur :

| Gate | Tests attestés |
| --- | ---: |
| `openclaw-nabla-migration-test` | 5/5 PASS |
| `openclaw-cron-parent-test` | 5/5 PASS |
| `openclaw-legacy-heartbeat-test` | 3/3 PASS |
| `openclaw-heartbeat-copies-test` | 4/4 PASS |
| `litellm-workstation-auth-contracts` | 3/3 unittest + 8/8 pytest + 5/5 unittest PASS |
| `truenas-openrag-startup-test` | 3/3 unittest + 15/15 pytest PASS |

**Total : 51/51 tests exécutés PASS.** `pytest 9.1.1` a
été installé dans `/tmp/nabla-pytest-venv` ; les recettes ciblées
ont passé en utilisant `NABLA_PYTEST_PYTHON`. Cela valide des
contrats locaux, **pas** l'état de LiteLLM TrueNAS ou Workstation
en production.

**Session cron** : le nouveau rapport est
`cron_main_reference=absent_in_reported_complete_catalog`,
`session_sample_count=21`, `session_sample_exhaustive=true`.
La session `agent:cron:main` est absente du catalogue CLI
annoncé complet. Cette preuve est cohérente avec l'échec de
`/new` dans `/chat/cron`, sans démontrer de corruption SQLite.
Ne pas supprimer une base ni réinitialiser le Gateway.

**Seul gate rouge** : `openclaw-heartbeat-copies-check`
renvoie 2 car les trois fichiers existent avec des permissions
insuffisantes :
- `HEARTBEAT.md.before-fix` : `unsafe_writable_by_others`
- `nabla` historique `HEARTBEAT.md` : `readable_by_others`
- archive `openclaw-2026-08-04_0220.tar.gz` :
  `readable_by_others` (taille 993378302 octets).

La sécurité de ces fichiers se corrige par **une opération de
métadonnées**. Cette PR ajoute un garde hors ligne, distinct
de l'inventaire non mutateur, pour appliquer `0600` uniquement
aux trois chemins et uniquement après validation de leurs
propriétaires, types, inodes, unicité et liens symboliques :

```bash
just openclaw-heartbeat-modes-test
just openclaw-heartbeat-modes-check
# Choix opérateur explicite, après avoir examiné le check :
just openclaw-heartbeat-modes-apply
just openclaw-heartbeat-copies-check
```

`--apply` est **opt-in** : il refuse une sauvegarde absente,
un lien symbolique, un hardlink, un fichier qui ne lui appartient
pas ou un nom imprévu. Il vérifie les identifiants des fichiers
ouverts avant `fchmod(0600)` et n'extrait jamais le tar.
Il ne restaure pas les prompts ni le heartbeat runtime.
Le mode 0600 n'empêche pas le propriétaire ou root de lire
les fichiers ; il supprime l'accès des autres utilisateurs par
les permissions classiques. Examiner séparément les ACL
additionnelles si nécessaire.

**Important :** les nouveaux tests du garde de permissions
(`openclaw-heartbeat-modes-test`) n'ont pas encore été exécutés
sur le poste. Ne pas présenter `--apply` comme déjà effectué.

## Réception des permissions et décision de nettoyage — 27/10, suivi PR #289

**Preuves reçues après le lot de 51/51 PASS :**
`openclaw-heartbeat-modes-test` = **6/6 PASS**.
Le `--check` révèle exactement
`workspace_before_fix=needs_mode_0600`,
`nabla_legacy_heartbeat=symlinked_parent` et
`openclaw_august_archive=needs_mode_0600`.
L'`--apply` original a **refusé toute modification**
(`files_mode_updated=0`) conformément au garde all-or-nothing.
Le contrôle des copies reste rouge : 3 permissions trop larges.
**Ne pas présenter `0600` comme déjà appliqué.**

Le garde de fichiers a été ajusté **uniquement** pour
`nabla_legacy_heartbeat`, qui peut traverser un symlink de
checkout : validation du propriétaire du lien (root ou
utilisateur), nom final attendu, chemin canonique invariant,
type régulier, owner, nlink unique et identité inode avant
`fchmod(0600)`. Les chemins de la copie `.before-fix` et
de l'archive n'acceptent toujours aucun parent symlink.
Deux tests supplémentaires couvrent ces contrats ; **ils
n'ont pas encore été exécutés sur Workstation**.

```bash
just openclaw-heartbeat-modes-test
just openclaw-heartbeat-modes-check
# Après inspection des trois sources : mutation ciblée autorisée par l'opérateur.
just openclaw-heartbeat-modes-apply
just openclaw-heartbeat-copies-check
```

L'opérateur accepte désormais la perte de **l'historique des
sessions OpenClaw** pour nettoyer `cron`. Préserver
credentials, profils, modèles, automatisations et réglages.

La CLI officielle supporte `openclaw sessions cleanup`
avec `--agent cron`, `--dry-run` et `--enforce` ;
le plan et l'application peuvent passer par le Gateway
actif sans modifier directement SQLite. Les nouvelles
recettes versionnées suivent cette méthode :
```bash
just openclaw-cron-session-maintenance-test
just openclaw-cron-session-maintenance-check
# Hors job cron actif, après lecture des compteurs et autorisation explicite :
just openclaw-cron-session-maintenance-apply
just openclaw-cron-parent-check
```

Le wrapper n'imprime ni identifiants, ni chemins de magasins,
ni transcripts ; il refuse un résultat qui référence un
autre agent ou plusieurs stores. Le nettoyage appliqué respecte
la rétention déjà configurée. Il **ne garantit pas** la purge de
toutes les 21 sessions et ne recrée jamais
`agent:cron:main`. Pour des suppressions plus directes,
`openclaw sessions delete <key> --agent cron --dry-run`
doit être utilisé uniquement avec des clés vérifiées, et
`--yes` après revue du plan ; jamais `openclaw reset --scope
config+creds+sessions`, qui détruirait aussi configuration et
credentials.

La cause précise du manque de session parent dans l'UI
nécessite une investigation distincte si une nouvelle conversation
`cron` ne peut pas être ouverte depuis l'interface après
la maintenance. Aucune commande destructive n'a été exécutée
sur la Workstation par cette PR.

**Roadmap canonique :**
[OpenClaw Workstation](../openclaw-workstation-roadmap.md)
(P0 LiteLLM, P1 sessions/permissions, P2 GitOps/HEARTBEAT,
P3 cutover TrueNAS). Elle est également liée dans
`docs/roadmap.md`.

## Dernière recette sessions / sauvegardes — reçue du poste

- `just openclaw-heartbeat-modes-test` : **8/8 PASS**.
- `--apply` des modes : **3 fichiers changés, 3 en 0600**.
- `just openclaw-heartbeat-copies-check` : **3 `private`**,
  aucune extraction ou lecture du contenu ; permissions ACCEPTED.
- `just openclaw-cron-session-maintenance-test` : **6/6 PASS**.
- `--dry-run` et `--apply` maintenance cron :
  `beforeCount=21`, `afterCount=21`, `pruned=0`.
  Nettoyage **exécuté avec résultat no-op**, pas une purge.
- `agent:cron:main` reste absent du catalogue exhaustif ;
  pas de réparation de session attestée.
- Nouveau défaut LiteLLM sans clé encore présent ; séparer
  ce problème de la maintenance des sessions.

Le **runbook OpenClaw dédié** et
`docs/openclaw-workstation-roadmap.md` remplacent les gates
historiques non atteints ; ne pas réappliquer `fchmod`
simplement pour faire passer une recette déjà validée.

## P1 — Migration non secrète de `nabla`

Commande d'inventaire :
```bash
just openclaw-nabla-migration-test
just openclaw-nabla-migration-check
```

Le script `audit-openclaw-nabla-migration.py` lit un ensemble
fermé de chemins de l'ancien checkout (par défaut
`~/w/nabla/env/home/dotfiles/.openclaw`), sans imprimer
les contenus ni déchiffrer le dépôt.
Il identifie le marqueur de blob git-crypt et refuse
les symlinks. Statut normal : `review_required_no_content_copied`.

| Source historique | Destination et décision |
|---|---|
| `workspace/AGENTS.md` | Revue privée, puis politique non secrète sous `apps/openclaw/workstation/` |
| `workspace/SOUL.md`, `TOOLS.md` | Revue puis migration de seules règles non sensibles |
| `workspace/IDENTITY.md`, `USER.md` | Données personnelles : ne pas publier dans `nabla-compose` |
| `workspace/HEARTBEAT.md` | Revue hors GitHub ; ne pas réactiver automatiquement le contenu ancien |
| `skills/tech-news-digest/SKILL.md` | Installer la version revue/pinnée ; conserver le prompt officiel comme source de vérité |
| `skills/caldav-calendar/SKILL.md` | Pinner et vérifier permissions ; secrets CalDAV exclus |
| `config/tech-news-digest-*.json` | Auditer URLs, identifiants privés et sujets avant publication éventuelle |
| `openclaw.json`, `.env`, `gateway.systemd.env`, `auth*.json`, `exec-approvals.json`, `*.sqlite` | **Aucun transfert automatique vers Git public** |

Les fichiers publiables doivent être produits comme **nouvelles
versions expurgées**, examinées, sans historique conversationnel
ni jetons. Les secrets restent dans leurs fichiers locaux protégés,
providers SecretRef et coffre existant. Aucune clé dans l'état
Terraform/OpenTofu ni dans GitHub Actions.

### Heartbeat et briefing

`apps/openclaw/workstation/HEARTBEAT.md` est actuellement
volontairement **non génératif** ; 
`MORNING_BRIEFING.md` porte déjà le briefing détaillé et
`openclaw-heartbeat-gitops.py` offre des modes check/apply
avec sauvegarde. L'ancien heartbeat `nabla` est chiffré et
n'a pas pu être revu. Ne jamais remplacer ces deux politiques
par une copie historique sans démontrer l'effet sur la facture
et sans validation d'une exécution isolée bornée.

Les tâches sont séparées :
- heartbeat minimal sans inférence tant que budgets/429
  n'ont pas été attribués ;
- digest `daily-tech-news-digest` isolé avec skill épinglé,
  `09:00 Europe/Paris`, `gpt-4.1-mini`, livraison et
  contrôle de génération distincts ;
- briefing du matin facultatif, isolé, borné et déclenché
  indépendamment.

### GitOps, Terraform/OpenTofu, MCP : décisions

**Git** versionne le non-secret : agent policies, prompts
révisés, catalogues de capacités, modèles autorisés,
horaires et identifiants logiques de jobs, tests et runbooks.
La première politique déclarative est
`apps/openclaw/workstation/cron/daily-tech-news-digest.policy.json`.
Elle référence le skill et le modèle, garde `ITEMS_PER_SECTION=5`
en attendant validation du template local et met
`agent_id=verify_runtime_agent` tant que le champ runtime
n'est pas prouvé. Son état `review_only_no_automatic_reconcile`
n'entraîne **aucune création ni modification** du cron.

```bash
just openclaw-digest-gitops-test
```

Les destinataires Discord/email restent volontairement privés et
sont des références d'environnement, jamais des valeurs à copier
dans le Git public. Éviter la copie brute de `~/.openclaw` :
c'est aussi de la donnée runtime.

**Reconcile local-first** : pour les cron OpenClaw, lire la
définition de tâche (identité/planification/modèle et hash
local de prompt **hors sortie publique**), produire un diff,
et exiger un `--apply` explicite.
Ne jamais effectuer `cron add` aveuglément : risque de
double exécution. `cron run` n'est jamais un diagnostic gratuit.
Un repo Git n'est pas, à lui seul, un reconcileur du scheduler.

**OpenTofu/Terraform** gère les ressources disposant d'un
provider et d'un état contrôlé (GitHub, DNS, réseaux, TrueNAS,
sécurité), **pas** les bases de sessions, les clés ou des
`local-exec` modifiant cron à chaque plan. Éviter de placer
des secrets dans les attributs suivis par le state.

**MCP** : utiliser le registre OpenClaw géré
(`openclaw mcp status --verbose`), préférer des serveurs
pré-approuvés, filtres d'outils par agent, isolation cron,
GitHub read-only pour l'agent de veille et services distants
derrière transport authentifié. `mcporter` est un registre
distinct ; ne pas importer le contenu brut de `.mcp.json`
ou les credentials d'un autre client.

Refs :
- https://docs.openclaw.ai/cli/cron
- https://docs.openclaw.ai/cli/mcp
- https://docs.openclaw.ai/heartbeat
- https://docs.litellm.ai/docs/proxy/health

## P1 bis — `/chat/cron` : unknown parent session

`/chat/cron` représente la session principale `agent:cron:main`
de l'agent `cron`. Les exécutions isolées sont associées à
des sessions de job distinctes ; leur bon fonctionnement
n'implique pas qu'une session principale `cron` existe.

L'erreur `unknown parent session: agent:cron:main`
est compatible avec une entrée principale absente/orpheline
ou une référence de session discordante après migration SQLite.
Elle **ne démontre ni corruption SQLite ni problème LiteLLM**.
Le texte d'erreur seul ne prouve pas la cause exacte.

Lecture seule sur Workstation :
```bash
just openclaw-cron-parent-test
just openclaw-cron-parent-check
```

Le diagnostic lit uniquement les métadonnées de 100 sessions
maximum pour l'agent `cron`. Il n'affiche **aucune** clé ni
transcription.

**Preuve Workstation du 27/10 :** `cron_session_catalog=structured`,
`session_sample_count=21`, `session_sample_exhaustive=true`,
`cron_main_reference=absent_in_bounded_sample`.
La liste complète retournée par la CLI **ne contient donc pas**
`agent:cron:main`. Le diagnostic révisé la classifie
`absent_in_reported_complete_catalog`; il garde
`absent_in_bounded_sample` si le catalogue est paginé.
Cela soutient l'explication de `unknown parent session`,
**sans établir une corruption SQLite ou un bug de LiteLLM**.

Consulter les sessions du digest via l'historique de l'automation,
pas via `/chat/cron`. Pour converser avec l'agent `cron`,
partir d'une **nouvelle conversation créée depuis l'UI**
si la version installée prend en charge cette opération ;
ne pas réutiliser la vieille URL d'une session absente.
Ne pas appeler `/new` sur un lien dont le parent n'est pas
résolu, ni effacer session SQLite/WAL/SHM. Ne pas re-jouer
`doctor --fix` simplement pour résoudre cette URL.

**DONE** : la session principale `cron` est identifiée,
ou le chat est ouvert sur une session valide existante ;
les données historiques sont préservées.

## Définition de fin de la migration vers TrueNAS

- Les routes `main/cron` sont inventoriées et les
  erreurs 429/401 attribuées sur Workstation.
- TrueNAS dispose des modèles cibles effectifs, d'une
  base de clés persistantes et de clés scoped distinctes.
- Les probes et métadonnées des quotas sont validés par
  tunnel chiffré et sans inférence pour le préflight.
- Un cutover explicite cible uniquement les deux providers
  nécessaires, avec rollback non destructif et pas de
  bascule implicite de mémoire vectorielle.
