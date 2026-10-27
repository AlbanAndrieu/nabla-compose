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
Éviter la copie brute de `~/.openclaw` : c'est aussi de la
donnée runtime.

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
openclaw sessions --agent cron --limit 25 --json |
  python3 -c 'import json,sys; d=json.load(sys.stdin); rows=d.get("sessions", d.get("entries", [])); print("cron_store_parsed=true"); print("cron_main_present="+str(any(isinstance(r,dict) and (r.get("key") or r.get("sessionKey"))=="agent:cron:main" for r in rows)).lower())'
```

Si la liste est paginée, une absence dans 25 entrées n'est
**pas** une preuve de suppression ; augmenter la limite
prudemment. Consulter les sessions réelles du job via l'UI
Automations et son historique, pas `/chat/cron` par défaut.
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
