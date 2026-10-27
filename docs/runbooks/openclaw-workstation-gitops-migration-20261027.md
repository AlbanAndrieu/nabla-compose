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
