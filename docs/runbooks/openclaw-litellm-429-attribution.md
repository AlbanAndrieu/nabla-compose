# OpenClaw / LiteLLM HTTP 429 — attribution hors ligne

## Constats (16–17 octobre 2026)

- Les HTTP 429 sur `POST /v1/chat/completions` ont été observés le 16 octobre entre 00:09–00:13 et 01:13–01:18 Europe/Paris (22:09–22:13 et 23:13–23:18 UTC le 15).
- Les 20 dernières exécutions fournies du job `heartbeat-main` (`bb9757db-9559-4960-bb23-9b9770929ff1`) échouent en `agent-runner-failure` le 16–17 octobre, avec environ 250–302 s de durée, mais ces exécutions **ne couvrent pas** les rafales du 16 octobre vers 00:09. Ne pas attribuer les 429 au heartbeat sur cette seule base.
- `openclaw-ops.sh --cron` rapporte le digest (`daily-tech-news-digest`), **pas** le heartbeat. Utiliser `--heartbeat` pour ce dernier.
- `--recent-errors` ne cherche que dans une fenêtre glissante de 30 min du journal du jour ; zéro événement n'invalide pas les 429 historiques.
- Les 429 LiteLLM sont des réponses proxy ; leur origine exacte (limite virtuelle RPM/TPM, budget, upstream Anthropic, autres) reste à qualifier via traces structurées.
- Un chevauchement temporel prouve uniquement que le job était actif pendant les refus ; il ne démontre pas que les appels proviennent du job.

## Audit sans requêtes facturables

Depuis le poste (ne pas copier de texte de prompt ou de secrets vers un ticket) :

```bash
openclaw cron runs --id bb9757db-9559-4960-bb23-9b9770929ff1 --limit 100 > /tmp/openclaw-heartbeat-runs.json
docker logs --timestamps --since '2026-10-16T00:00:00+02:00' --until '2026-10-16T01:25:00+02:00' litellm-litellm-1 2>&1 > /tmp/openclaw-litellm-audit.log
python3 scripts/workstation/openclaw-rate-limit-correlation.py --cron-json /tmp/openclaw-heartbeat-runs.json --litellm-log /tmp/openclaw-litellm-audit.log
```

Fichiers temporaires : permissions restrictives recommandées (`umask 077`), purger après enquête. Le programme ne restitue que des compteurs, des horaires et l'étiquette `temporal_overlap_only_not_proof_of_caller`. Les exports source restent potentiellement sensibles et ne doivent pas être publiés.

Pour remonter au véritable appelant : corréler au niveau LiteLLM le `request_id`, le hash de clé virtuelle, le modèle, le motif 429 (budget/RPM/TPM/upstream) avec les `agent_id`, `session_id` et `cron_job_id` OpenClaw, en journalisation structurée **sans prompts ni valeurs de clés**. Une IP Docker NAT comme `172.16.7.1` ne constitue pas une identité d'appelant fiable.

Ne pas augmenter les budgets ni les limites, ne pas redémarrer les agents, ne pas supprimer les sessions, ne pas lancer de smoke facturable pour obtenir cette preuve.

## Diagnostic après cutover cron — 24 octobre 2026

Le cutover du credential `cron` a réellement réussi sur Workstation
(`cron_cutover_applied=true`, `cron_cutover_gateway_secrets_reload=completed`).
Ce changement remplace uniquement la **source de résolution** de sa clé ;
il ne crée pas de clé virtuelle LiteLLM, ne modifie pas les budgets/RPM/TPM
et ne migre pas l'agent `main`. La phrase UI OpenClaw
« API rate limit reached » **ne contient pas assez de preuves** pour
attribuer le 429 à LiteLLM ou au fournisseur upstream.

La capture LiteLLM v1.104.2 fournie montre cinq alias :
`openclaw-embeddings` (0 $ / 1 $), `n8n`, `openclaw-main`
(0,0292 $ / 10 $, dernière activité 20 octobre), `ide` et
`openclaw` (0,3263 $ / 2 $, dernière activité 24 octobre).
Ce sont des observations d'interface à cet instant : aucune clé alias
`openclaw-cron` n'est visible, **ce qui ne prouve pas** que le
credential `cron` est inexistant ou qu'il est valide.
Les budgets visibles ne sont pas épuisés. Les limites RPM/TPM,
user/team/model et provider sont distinctes.

### Lire les preuves sans générer de consommation

```bash
cd ~/w/nabla-compose
just openclaw-429-triage-test
just openclaw-429-triage
```

La recette exécute uniquement :
1. une vérification privée du fichier `openclaw-cron.key` et de
   son éventuelle identité avec l'environnement préchargé ;
2. une comparaison en mémoire des identifiants SHA-256 LiteLLM avec
   ceux **déjà documentés** dans `openclaw-litellm-audit.py`.
   Aucun hash, préfixe, token ou valeur n'est affiché. `not_in_known_set`
   veut dire « pas dans les identifiants connus du script »,
   **pas** « clé inexistante dans LiteLLM » ;
3. lorsque `LITELLM_MASTER_KEY` est exportée, deux lectures
   `GET /key/info` par **identifiant haché uniquement**,
   **exclusivement** sur `localhost:4000` ou
   `127.0.0.1:4000` (et IPv6 loopback). Les réponses et erreurs
   brutes sont masquées. Le diagnostic affiche seulement les
   métriques de budget, RPM, TPM et concurrence documentées.
4. les métadonnées de routage de la configuration OpenClaw existante
   (noms de fournisseurs connus uniquement, sans montrer les clés).

Le script retourne toujours
`http_429_origin=unverified_requires_failed_request_metadata`
tant qu'aucun échec corrélé n'a été examiné. Il **n'envoie aucune requête
de modèle**, ne touche ni aux budgets ni aux secrets du Gateway.

### Identifier la source exacte du 429

Depuis **LiteLLM Admin UI → Logs**, filtrer l'heure du dernier message
OpenClaw, l'alias de clé, le modèle, le code `429` et le statut d'échec.
Conserver localement le détail du `x-litellm-call-id` s'il existe.
Ne pas activer l'enregistrement des prompts (désactivé par défaut).
Ne pas copier les corps de requête/réponse ni les headers d'autorisation.

Interpréter les métadonnées filtrées :

| Signal | Hypothèse de panne |
| --- | --- |
| `error.type=budget_exceeded` | Budget key/user/team/per-model |
| `retry-after`, `rate_limit_type` ou `reset_at` | Limiteur LiteLLM ou cooldown |
| 429 sans ces marqueurs, erreur fournisseur dans le détail | Limite upstream |
| `No deployments available for selected model` | Tous les déploiements du groupe en cooldown |
| `rate_limit_type=concurrent_requests` | Limite de parallélisme |

Un refus **401/403** pointe vers l'authentification ou l'autorisation,
pas vers un quota atteint. La preuve UI actuelle ne permet pas de
trancher entre ces catégories.

### Historique à ne pas confondre avec l'état actuel

Le journal d'octobre a déjà constaté `openclaw-main`
au-delà de **10 $ / 10 $** et des heartbeats en échec avec
chevauchement temporel de 429. La capture actuelle montre une
période budgétaire différente (0,0292 $ / 10 $) : ne pas
réutiliser l'ancienne cause sans une nouvelle trace. La même période
historique comportait des estimations de contextes très longs,
susceptibles d'accentuer les demandes TPM, mais pas de preuve que
la conversation actuelle déclenche le même incident.

Références : <https://docs.litellm.ai/docs/proxy/error_reference>,
<https://docs.litellm.ai/docs/proxy/virtual_keys>,
<https://docs.litellm.ai/docs/proxy/ui_logs>.



## Diagnostic TrueNAS distinct de l'erreur 429 — 24 octobre 2026

### Preuves : HTTP auth failure, pas une réponse 429

La capture de l'opérateur sur **LiteLLM TrueNAS 1.106.2**, trace `889ddeb8-fc31-44ae-8733-63992bec19e5`, affiche `No api key passed in.` ; endpoint `GET /v1/models` ; `user_api_key=null`, aucun modèle/provider, aucun token et coût nul. L'adresse signalée `172.17.0.24` et le champ `user_agent=litellm/1.106.2` sont compatibles avec le contexte TrueNAS, mais **ne prouvent pas l'identité réelle de l'appelant** (proxy, sonde, interface, NAT). Ce log est **une absence de header d'authentification**, pas une limitation de débit et ne suffit pas à établir la cause du message UI OpenClaw `API rate limit reached`.

### Architecture cible déjà décidée

Le runbook historique `2026-10-10-openclaw-workstation-remediation.md` impose un **LiteLLM central TrueNAS** à `172.17.0.24:4000/v1`. Son inventaire antérieur comptait **0 clé virtuelle** alors que Workstation possédait 5 clés. Le cutover récent de la SecretRef cron a déplacé la **même clé virtuelle Workstation** vers `openclaw-cron.key` (le diagnostic identifie son hash comme alias `openclaw`) : il ne crée pas de credential TrueNAS. Il ne migre pas `main` non plus.

La sortie de l'opérateur `openclaw-route-metadata.py` atteste que les providers `litellm-main` et `litellm-cron` ont une URL non-loopback, mais **n'identifie pas encore formellement l'hôte**. Le script a été renforcé avec `route_owner=truenas_litellm|workstation_litellm|workstation_lan_litellm|other_or_unverified` et `key_representation=literal_or_unresolved|env_reference|secretref_object|missing`, sans jamais publier l'URL ni le secret. Refaire ce contrôle après synchronisation.

### Bloqueur modèle : gpt-4.1 et gpt-4.1-mini non déclarés

`apps/litellm/config.yaml` contient `workstation-qwen`, `embedding`, `embedding-local`, des routes Hermes, etc., mais **aucun `model_name` actif exactement `gpt-4.1` ou `gpt-4.1-mini`**. Ces alias sont les modèles OpenClaw `main` et `cron` documentés. La présence de fallbacks textuels vers ces noms ne déclare pas les modèles dans `model_list`. L'état runtime peut diverger du Git : le vérifier avant de modifier les modèles ou provisionner les clés.

### Préflight chiffré en lecture seule

```bash
cd ~/w/nabla-compose
just openclaw-429-triage-test
just openclaw-truenas-model-keys-test
just openclaw-429-triage
just openclaw-truenas-model-keys-check
```

Le dernier check compare uniquement les `model_name` **déclarés dans Git**. Pour lire l'état runtime, créer **manuellement** un forward SSH chiffré `127.0.0.1:14000 -> TrueNAS:127.0.0.1:4000` avec une session authentifiée existante, sans exposer l'admin à HTTP LAN, et exporter `LITELLM_TRUENAS_MASTER_KEY` **privément**, puis :

```bash
just openclaw-truenas-model-keys-tunnel
```

Cette commande ne fait que deux GET de métadonnées : `/v1/models` et `/key/list`. Elle ne sort ni les clés ni leurs hashes, ni les modèles hors allowlist, et ne crée aucun token. Sans tunnel ou authentification elle s'arrête sans hypothèse de vacuité.

### Persistance des clés sur TrueNAS

Le compose TrueNAS `apps/litellm/compose.yml` monte
`/mnt/cpool/secrets/runtime/litellm/.env.secrets` comme
`env_file`, avec `DATABASE_URL` seulement **commentée** dans
la section `environment`. La vraie connexion PostgreSQL peut
venir du fichier de secrets privé : **son état runtime n'est pas
établi à partir de Git**. Avant de générer une seule clé, vérifier
dans le conteneur TrueNAS **la présence de DATABASE_URL, sans
imprimer sa valeur**, et le succès de la connexion PostgreSQL.
Une UI sans clés n'est pas une preuve de l'absence de base ou
de l'impossibilité de les persister. Une mauvaise persistance
produirait une migration non durable au prochain redéploiement.

### Plan de migration réelle — phases indépendantes

1. Confirmer l'hôte réel de `litellm-main`/`litellm-cron` et les alias `gpt-4.1`, `gpt-4.1-mini` exposés **dans le runtime TrueNAS** ; si absents, rétablir d'abord les routes de modèles par configuration déclarative et secrets upstream distincts, sans réutiliser la clé master.
2. Créer via **l'Admin UI TrueNAS** (ou API `/key/generate` sur transport chiffré) deux **nouvelles clés virtuelles** `openclaw-main` et `openclaw-cron`, avec allowlists de modèles, budgets et limites RPM/TPM. Éviter de dupliquer arbitrairement les clés Workstation. L'API LiteLLM garantit des identités propres par proxy.
3. Importer chaque nouvelle valeur dans son fichier `0600` spécifique sur la Workstation, revoir les `SecretRef` main/cron et la route `172.17.0.24:4000/v1`, puis valider `openclaw secrets reload` et une requête de modèle contrôlée seulement si autorisée.
4. Une fois la bascule validée, nettoyer les credentials Workstation historiques et les modèles générés ; préserver les originaux en sauvegarde privée le temps du rollback. Traiter séparément les quatre credentials du magasin auth partagé. Ne jamais transférer un master key dans OpenClaw.

**Pas d'auto-réplique des valeurs de clés**, pas d'augmentation de quota pour masquer une erreur, pas de `GET /v1/models` sans header d'authentification pour « tester » un proxy protégé, et pas de déploiement TrueNAS tant que son active `config.yaml`/DB ne sont pas attestés.



## Retour opérateur : routes Workstation et préflight TrueNAS bloqué (24 octobre 2026)

### Faits nouveaux

Le script mis à jour `openclaw-route-metadata.py` retourne :

- `litellm-main route_owner=workstation_lan_litellm` ;
- `litellm-cron route_owner=workstation_lan_litellm` ;
- `litellm route_owner=workstation_litellm`, sans API key déclarée.

Les deux routes des agents sont **172.17.0.57:4000/v1**.
La migration des valeurs vers des fichiers `SecretRef` n'a donc
pas modifié la destination des requêtes : **aucune bascule vers TrueNAS
n'est prouvée**, et la trace TrueNAS `GET /v1/models` sans clé
ne doit pas être qualifiée de cause du 429 OpenClaw.

Le préflight déclaratif TrueNAS confirme l'absence de `gpt-4.1`
et `gpt-4.1-mini` dans `apps/litellm/config.yaml`. Les
groupes `workstation-qwen` et `embedding` y sont présents.
L'inventaire du **runtime** n'a pas encore été réalisé.

### Corrections de la PR

- `just openclaw-429-triage-test` : **10 tests OK** sur Workstation.
- `just openclaw-truenas-model-keys-test` : 6 contrats OK,
  mais son ancienne recette essayait ensuite `python3 -m pytest`.
  Le Python géré par mise ne possède pas `pytest`.
  Cette recette utilise désormais exclusivement `unittest`, sans
  installation globale et sans altérer les environnements des autres
  worktrees. Trois tests de confidentialité du routage sont disponibles.
- Le préflight `--tunnel` refuse les requêtes d'administration si
  aucun port local n'écoute sur `127.0.0.1:14000`. Un listener
  local n'atteste **pas** l'identité d'un tunnel SSH ; cette identité
  reste à vérifier par l'opérateur.
- `LITELLM_TRUENAS_MASTER_KEY` manquait dans le shell de la
  commande précédente. Un mode `--prompt-admin` accepte une saisie
  unique et **masquée sur terminal interactif** et garde la valeur
  seulement dans la mémoire du processus Python.
  Il n'est pas nécessaire de l'exporter durablement.

### Séquence opérateur — lecture seule

Synchroniser d'abord le HEAD de la PR, puis :

```bash
just openclaw-429-triage-test
just openclaw-truenas-model-keys-test
just openclaw-429-triage
just openclaw-truenas-model-keys-check
```

Avant de demander les inventaires runtime, préparer séparément un
tunnel SSH local existant vers TrueNAS. Exemple depuis la Workstation,
avec le compte SSH réellement autorisé, dans un terminal réservé :

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:14000:127.0.0.1:4000 \
  <ssh-user>@172.17.0.24
```

Ne pas saisir le signe `<` littéralement : substituer le vrai
nom d'utilisateur SSH. Confirmer l'empreinte du serveur lors de la
première connexion ; ne jamais contourner cette vérification.

Puis dans un **deuxième terminal interactif** :

```bash
just openclaw-truenas-model-keys-tunnel-prompt
```

Cette recette vérifie les modèles et le nombre de clés TrueNAS
sans en créer ni envoyer de chat. La clé demandée est la clé
**administrateur LiteLLM TrueNAS**, pas la clé `openclaw-cron`
Workstation ni le mot de passe de l'interface. Le script refuse la
lecture si la console n'est pas interactive.

### Condition de migration

Le chantier TrueNAS reste **NO-GO** tant que les alias requis ne sont
pas confirmés, les clés virtuelles ne sont pas provisionnées avec leurs
permissions propres, et la persistance PostgreSQL n'est pas vérifiée.
Pour la panne courante OpenClaw, diagnostiquer **d'abord** la route
Workstation réellement utilisée et une requête échouée attribuée à
`main` ou `cron`. Les clés `main` et `cron` ne doivent
pas partager automatiquement la même identité virtuelle `openclaw`.



## Retour SSH : port 14000 occupé et master key déjà exportée (24 octobre 2026)

**Preuves opérateur** : la commande `ssh -N -L
127.0.0.1:14000:127.0.0.1:4000 ...` n'affiche rien,
ce qui est **normal** tant que le tunnel SSH reste actif.
Une seconde tentative en `14000` échoue avec
`Address already in use`. Cela peut être la première
session SSH ou un autre programme : **ne pas lancer un troisième
tunnel** sans inspection du listener. `4000` en local
est le LiteLLM Workstation et doit rester réservé.

Dans `~/.ssh/config`, l'alias `truenas` et
`172.17.0.24` utilisent `albandrieu` et le port SSH
**9922** ; préférer `ssh truenas` à une adresse qui supposerait
le port SSH 22.

Le port `14000` n'est **pas un port à ouvrir sur TrueNAS** :
c'est un port local disponible sur Workstation pour transférer
`127.0.0.1:14000` vers `127.0.0.1:4000` côté TrueNAS.

### Vérifier le listener et le tunnel sans secret

```bash
ss -ltnp '( sport = :14000 or sport = :4000 )'
ssh -O check truenas
just openclaw-truenas-tunnel-check
```

- `ss` indique quel programme possède les ports locaux ;
  rechercher `ssh` sur 14000, et LiteLLM Workstation sur 4000.
- `ssh -O check truenas` contrôle un éventuel ControlMaster SSH,
  mais **ne prouve pas, à lui seul, le port forward ni la destination**.
- `just ...-tunnel-check` vérifie un listener local, mais
  affiche `operator_attestation_required` : un port TCP qui répond
  n'est **pas** une preuve cryptographique qu'il s'agit de SSH.

Si aucun tunnel n'est actif et que 14000 est libre, ouvrir la
session dans un autre terminal avec :

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:14000:127.0.0.1:4000 truenas
```

### Master key préchargée

La commande `echo $LITELLM_MASTER_KEY` révèle un secret :
ne pas l'utiliser pour diagnostiquer sa présence. Le script
exigeait jusqu'ici la variable dédiée
`LITELLM_TRUENAS_MASTER_KEY` ou la saisie interactive masquée ;
la seule présence de `LITELLM_MASTER_KEY` n'était pas détectée
par le mode `--prompt-admin`. Ce mode ne lit **jamais** une
variable exportée à ta place. `truenas_admin_auth=missing`
indique seulement que la valeur saisie n'a pas satisfait le
contrat attendu.

Après vérification du tunnel, le nouveau mode permet de choisir
**explicitement** la variable préchargée :

```bash
just openclaw-truenas-model-keys-tunnel-existing-master
```

Cette recette utilise `LITELLM_MASTER_KEY` seulement après
validation par l'opérateur qu'il s'agit de **la master key
LiteLLM TrueNAS**, pas de celle de la Workstation. Sinon
utiliser une variable dédiée `LITELLM_TRUENAS_MASTER_KEY`
et la recette `just openclaw-truenas-model-keys-tunnel-dedicated`,
ou la saisie masquée
`just openclaw-truenas-model-keys-tunnel-prompt`.

Le script ne place jamais la valeur de la clé en argument,
ne l'imprime pas et la transmet uniquement au service
écoutant sur la boucle locale 14000. Vérifier avant cela
que ce listener correspond réellement au tunnel SSH attendu.
Une erreur HTTP 401/403 signifie que la clé ne permet pas
l'administration de cette instance ; ne pas migrer les clés
tant que cette identité n'est pas confirmée.

**Résultats de qualité :** les 10 tests TrueNAS et 3 tests
de routage ont réussi sur la Workstation. Quatre tests
de sélection d'environnement et de présence du port ont
été ajoutés en PR mais **pas encore exécutés sur la Workstation**.
Tous les scripts restent read-only.



## Tunnel LiteLLM TrueNAS automatisé et master key exportée — 25 octobre 2026

### Constats opérateur

- `ss -ltnp` confirme une écoute `ssh` sur
  `127.0.0.1:14000` ; `0.0.0.0:4000` appartient au
  service LiteLLM Workstation. L'erreur de doublon SSH est
  donc évitable sans tuer un processus ni déplacer le port 4000.
- Les **14 tests de préflight TrueNAS** et les **3 tests de route**
  précédents ont réussi sur Workstation.
- `export LITELLM_TRUENAS_MASTER_KEY` **ne charge pas une valeur** :
  si la variable était inexistante, elle est maintenant exportée
  mais vide. Le script `--prompt-admin` demande une valeur
  au clavier ; il ne lit jamais cette variable automatiquement.
- `master_exported=false` concernait **`LITELLM_MASTER_KEY`**,
  une autre variable. La recette `tunnel-existing-master` était
  donc incompatible avec l'environnement déclaré.

### Script idempotent — SSH alias TrueNAS :9922

```bash
cd ~/w/nabla-compose
just openclaw-truenas-tunnel-check
just openclaw-truenas-tunnel-ensure
```

Le helper `ensure-openclaw-truenas-litellm-tunnel.py` :
1. Contrôle un seul listener sur `127.0.0.1:14000`.
2. Vérifie propriétaire, nom du processus `ssh` et argument
   `-L 127.0.0.1:14000:127.0.0.1:4000` via `/proc`
   **sans imprimer le PID ni les arguments**.
3. Réutilise un listener SSH conforme ; refuse de toucher à un
   port occupé par une autre application ou à un transfert non prouvé.
4. Si le port est libre, vérifie `ssh -G truenas` :
   `hostname 172.17.0.24`, `user albandrieu`,
   `port 9922` (configuration fournie par l'opérateur).
5. Ouvre si nécessaire un tunnel `ssh -f -N -S none` avec
   `ExitOnForwardFailure=yes`, `BatchMode=yes`,
   `ForwardAgent=no`, `StrictHostKeyChecking=yes`.
   Il **ne ferme jamais** de session SSH existante.

Le préflight administrateur exige désormais ce transfert SSH
**identifié**, pas seulement un listener TCP générique. La vérification
des clés d'hôte SSH par l'opérateur reste requise.

### Contrôler la variable sans dévoiler la valeur

```bash
python3 -c 'import os; n="LITELLM_TRUENAS_MASTER_KEY"; v=os.environ.get(n); print("truenas_master_state=" + ("not_exported" if v is None else "empty" if not v else "present"))'
```

- `not_exported` : la variable n'est pas visible du processus Python.
- `empty` : `export` seul n'a défini aucune clé.
- `present` : la variable contient une valeur non vide, mais **pas
  nécessairement la bonne clé master TrueNAS**.

Si elle est absente, obtenir la clé master TrueNAS dans son
gestionnaire de secrets autorisé, sans l'imprimer. En terminal
Bash interactif, une saisie privée ponctuelle peut utiliser :

```bash
read -rsp 'LiteLLM TrueNAS master key: ' LITELLM_TRUENAS_MASTER_KEY
printf '\n'
export LITELLM_TRUENAS_MASTER_KEY
```

Lorsque le tunnel est identifié et que la variable dédiée possède
sa vraie valeur :

```bash
just openclaw-truenas-model-keys-tunnel-dedicated
```

Le script distingue désormais
`truenas_admin_env_state=not_exported|empty|present|unexpected_format`
et `truenas_admin_prompt=empty_value`, sans contenu de secret.
Il évite les proxys HTTP externes lors des appels au tunnel local.

**Vérification locale du nouveau lot :**

```bash
just openclaw-truenas-model-keys-test
```

Cette recette inclut 18 tests TrueNAS, 3 tests de routes et 8 contrats
du helper SSH, soit **29 tests déclarés**. Ils restent
**NOT_RUN sur Workstation au HEAD de cette amélioration**.

Ne pas dupliquer les clés virtuelles de LiteLLM Workstation sur
TrueNAS avant inventaire des modèles, de l'authentification et de
la persistance PostgreSQL. Pas de mutation des credentials,
pas de restart Gateway, pas d'import de clé sans autorisation.

