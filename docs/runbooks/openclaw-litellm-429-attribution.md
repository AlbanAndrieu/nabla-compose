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



## Correction du 25 octobre — tests et alias SSH TrueNAS

### Résultat de validation reçu sur Workstation

La synchronisation fast-forward est réussie. Le contrôle
`just openclaw-truenas-model-keys-test` a exécuté 18 tests de
préflight TrueNAS, avec **un échec synthétique seulement** :
`test_prompt_admin_requires_terminal_and_never_reads_secret`.
Le test supposait un listener actif, mais n'avait pas simulé
`loopback_listener=True`. Comme le script vérifie le tunnel
**avant** le TTY, il retournait correctement
`truenas_tunnel_local_listener=unavailable`. Le contrat
a été corrigé : son stub simule maintenant un tunnel vérifié
pour isoler le cas `stdin.isatty()=false`.

Le vrai `just openclaw-truenas-tunnel-ensure` a retourné
`truenas_tunnel=absent`, puis
`truenas_ssh_alias=unexpected_target_or_port`.
Le script exigeait `ssh -G truenas` avec
`hostname=172.17.0.24`. Or le bloc SSH fourni :

```sshconfig
Host 172.17.0.24 nabla freenas truenas
    User albandrieu
    Port 9922
    IdentityFile ~/.ssh/id_ed25519
```

ne contient pas de `HostName` explicite : la sortie
de `ssh -G truenas` peut donc contenir
`hostname truenas`. **Ce n'est pas un mauvais port SSH.**

### Correctif

Le helper accepte `hostname=truenas` ou
`hostname=172.17.0.24`, mais impose toujours
`user=albandrieu` et `port=9922`.
**Lorsqu'il crée le tunnel**, l'argument
`-o HostName=172.17.0.24` fixe explicitement
la destination pour empêcher toute résolution de
l'alias vers un autre serveur. Les vérifications
`StrictHostKeyChecking=yes`, `BatchMode=yes`
et `ForwardAgent=no` restent obligatoires.
Un listener inconnu n'est jamais écrasé ni arrêté.

### Prochaine exécution sur Workstation

Synchroniser la branche de la **PR Draft #277** (la
[PR #274](https://github.com/AlbanAndrieu/nabla-compose/pull/274)
a été fusionnée le 24 octobre), en protégeant les
modifications locales des sous-modules.

```bash
cd ~/w/nabla-compose
just openclaw-truenas-model-keys-test
just openclaw-truenas-tunnel-ensure
just openclaw-truenas-tunnel-check
just openclaw-truenas-model-keys-tunnel-dedicated
```

La dernière commande exige la vraie
`LITELLM_TRUENAS_MASTER_KEY` exportée, mais ne
l'imprime jamais. Une variable `present`
ne garantit pas que le serveur l'accepte.
L'inventaire reste **non exécuté** tant qu'il n'y a pas
de `truenas_key_list_http=200` et de modèles runtime.

Aucun changement de modèle ou de clé n'est effectué
par ces quatre recettes. La bonne santé des modèles et
la persistance PostgreSQL restent à prouver.



## TrueNAS LiteLLM : master key de format inattendu — 25 octobre 2026

La Workstation a validé **29/29 contrats** :
18 tests TrueNAS, 3 de routage et 8 de tunnel SSH.
Le tunnel est établi avec
`truenas_tunnel_after_start=verified_ssh`, puis réutilisé
avec `truenas_tunnel_action=reuse`.
L'inventaire authentifié du proxy **n'a pas encore eu lieu** :

```text
truenas_admin_source=dedicated_truenas_environment
truenas_admin_env_state=unexpected_format
truenas_admin_auth=missing
```

Ce refus était déclenché **localement** si la valeur ne
commençait pas par `sk-` ou était trop courte. Il ne représente
ni une réponse HTTP 401/403 du serveur, ni une preuve que
la clé est erronée. La documentation LiteLLM recommande
`sk-` pour les nouvelles master keys ; certaines versions
indiquent que ce préfixe n'est qu'une convention. Ne pas
changer la master key TrueNAS ou `LITELLM_SALT_KEY`
uniquement pour satisfaire le diagnostic : une rotation
incontrôlée risque de rendre les données chiffrées illisibles.

### Diagnostic sans réseau et sans impression de secret

Après synchronisation de la branche de la PR :

```bash
just openclaw-truenas-model-keys-test
just openclaw-truenas-master-env-check
```

Cette recette classe uniquement le contenu **déjà exporté**
de `LITELLM_TRUENAS_MASTER_KEY`. Elle ne contacte aucun
serveur et ne publie ni valeur, ni préfixe, ni longueur exacte.

Les états possibles comprennent :
`not_exported`, `empty`, `too_short`,
`looks_like_reference`, `surrounding_quotes`,
`invalid_characters`, `present` (préfixe `sk-`)
et `nonstandard_prefix` (valeur de longueur suffisante,
composée de caractères imprimables, mais sans préfixe `sk-`).

Si le résultat indique `looks_like_reference`, ne pas
transmettre le contenu tel quel à LiteLLM : résoudre la
référence en privé et exporter **la vraie valeur**, sans
utiliser `echo` ni la placer dans l'historique shell.
`too_short`, `surrounding_quotes` ou
`invalid_characters` exigent la correction de la
source privée avant toute requête authentifiée.

Si `present`, utiliser :

```bash
just openclaw-truenas-model-keys-tunnel-dedicated
```

Si `nonstandard_prefix`, confirmer auprès de la
configuration privée **effective** du conteneur LiteLLM
TrueNAS que cette valeur est bien la master key.
Une option explicite autorise ensuite uniquement deux
**GET de diagnostic** via un tunnel SSH déjà vérifié :

```bash
just openclaw-truenas-model-keys-tunnel-dedicated-nonstandard
```

Sans cette option, le préflight continue de refuser les
clés non standard. Une réponse 401/403 signifie
que le serveur n'accepte pas la clé présentée ;
aucun client ni proxy ne doit être reconfiguré
pour contourner cette autorisation.

Les inventaires `/v1/models` et `/key/list`,
la présence de modèles `gpt-4.1*` et la
persistance des clés virtuelles sur TrueNAS restent
**non attestés** jusqu'à la première réponse admin
réussie. La PR ne crée, ne copie et ne supprime
aucun credential.



## Acceptation Workstation — 25 octobre 2026 — inventaire admin TrueNAS

Retour d'exécution fourni par l'opérateur sur la branche de la PR #280.
Cette section prévaut sur les anciennes mentions « inventaire non exécuté ».

| Contrôle | Preuve | Résultat |
| --- | --- | --- |
| Contrats préflight TrueNAS | unittest | 25/25 PASS |
| Contrats routage OpenClaw | unittest | 3/3 PASS |
| Contrats tunnel SSH | unittest | 8/8 PASS |
| Tunnel local | `verified_ssh`, `reuse` | PASS |
| Master admin dédiée | `nonstandard_prefix`, `provided` | Acceptée pour les deux GET |
| `GET /v1/models` | HTTP 200 | PASS, mais `gpt-4.1` et `gpt-4.1-mini` absents |
| `GET /key/list` | HTTP 200, `count=0` | Aucun élément listé par l'endpoint |
| Migration virtuelle | `migration_applied=false` | NON EFFECTUÉE |

**Interprétation** : le préfixe différent de `sk-` n'est pas un motif
d'échec d'authentification sur cette instance. Les réponses 200 attestent
uniquement les deux lectures autorisées ; elles ne prouvent ni la
disponibilité d'autres routes, ni la connexion PostgreSQL, ni la persistance
après redéploiement. Le `count=0` concerne le résultat de `/key/list`,
pas une inspection directe de la base.

**Décision NO-GO** : ne pas basculer `openclaw-main` ou `openclaw-cron`
vers TrueNAS, ne pas générer de clé, ne pas tourner `LITELLM_MASTER_KEY`
ou `LITELLM_SALT_KEY` tant que :
1. la source effective de configuration et les alias de modèles nécessaires sont identifiés ;
2. `DATABASE_URL` et la connectivité DB sont attestées sans divulgation de valeur ;
3. les clés virtuelles distinctes `main` et `cron` sont provisionnées et testées avec un rollback possible.

La suite de diagnostic est strictement en lecture seule. Les sous-modules
`n8n` et `sentry` signalés modifiés dans le worktree opérateur ne sont
pas touchés par cette procédure. Les tests ont été exécutés sur Workstation ;
le runtime et la DB n'ont pas été modifiés.


## Vérification parallèle des secrets — 25 octobre 2026

L'opérateur a indiqué avoir ajouté six noms de variables dans
`/mnt/cpool/secrets/runtime/openrag/litellm/.env.secrets` :
`LITELLM_OPENCLAW_CRON_API_KEY`, `LITELLM_OPENCLAW_MAIN_API_KEY`,
`LITELLM_REACTIVE_API_KEY`, `LITELLM_IDE_API_KEY`,
`LITELLM_API_KEY`, `LITELLM_N8N_API_KEY`.
**Aucune valeur de clé n'est documentée.**

Attention : `apps/litellm/compose.yml` référence l'autre chemin
`/mnt/cpool/secrets/runtime/litellm/.env.secrets`. La présence de valeurs
dans un fichier ne prouve pas leur injection dans le conteneur
`litellm`, ni la création des clés virtuelles en base.

La ligne `LITELLM_N8N_API_KEY=XXX"` communiquée présente un guillemet
de fermeture isolé. Corriger la source réelle **si** elle a été
copiée sous cette forme ; ne pas recopier les valeurs dans Git ou les logs.

Diagnostic depuis la Workstation, en lecture seule, avec trois contrôles
SSH concurrents (pas de restart, pas de requête LLM, pas de génération de clé) :

```bash
just openclaw-truenas-secret-provenance
```

Cette recette utilise `sudo -n python3` sur TrueNAS et `docker inspect`.
Une absence de sudo non interactif donne `unverified`, pas un PASS fictif.
Le résultat compare les variables du fichier OpenRAG avec l'environnement
du conteneur **uniquement en mémoire** : aucune valeur ou empreinte n'est
imprimée. La lecture est limitée à des indicateurs de présence, à la
syntaxe et à la concordance. `database_url_in_container=present`
ne teste **pas** la connexion PostgreSQL ou la persistance.

L'inventaire authentifié des modèles et du nombre de virtual keys
reste disponible via
`just openclaw-truenas-model-keys-tunnel-dedicated-nonstandard` :
ne jamais considérer six variables présentes comme six clés
provisionnées dans LiteLLM. Conserver le statut NO-GO de la migration
tant que la persistance et les modèles ne sont pas vérifiés.


### Correction du chemin canonique et Langfuse — retour opérateur

Le chemin `/mnt/cpool/secrets/runtime/openrag/litellm/.env.secrets`
avait été communiqué par erreur. **Le fichier réellement modifié** est
`/mnt/cpool/secrets/runtime/litellm/.env.secrets`, déjà utilisé dans
`apps/litellm/compose.yml`. La variable `LANGFUSE_PUBLIC_KEY`
a été ajoutée en plus des six noms mentionnés ci-dessus.

La recette `just openclaw-truenas-secret-provenance` examine désormais
**sept noms** dans le fichier canonique et les compare aux variables
injectées du conteneur `litellm`. Le résultat
`env_file_semantics=loaded_at_container_creation_not_bind_mount` rappelle
qu'un `env_file` Docker Compose n'est pas un bind mount.
Un fichier correct, mais des variables absentes dans le conteneur déjà
lancé, signifient un **drift runtime** (recréation à planifier), pas une
erreur de chemin. `container_recreation_needed=true` indique ce drift
sans déclencher de changement.

Le relevé précédent `DATABASE_URL=present` ne prouve ni l'accès à
PostgreSQL ni la persistance. Ne pas lancer `docker compose up`,
`restart`, `--force-recreate` ni de migration automatique avant de
valider la syntaxe, le contenu des secrets nécessaires et un rollback.

Commande de validation depuis le checkout PR actualisé :

```bash
python3 -m py_compile scripts/workstation/check-truenas-litellm-secret-provenance.py
just openclaw-truenas-secret-provenance
```

La commande sort avec code 2 si la source n'est pas vérifiée ou en cas
de différence entre le fichier et le conteneur. **Un exit 2 signifie
investigation nécessaire, pas incident HTTP.** Aucune valeur de secret
n'est imprimée. Le résultat n'a pas encore été exécuté au nouveau HEAD
sur la Workstation.


## Acceptation runtime — recréation LiteLLM TrueNAS (25 octobre 2026)

Preuve exécutée sur Workstation par l'opérateur :

- `just openclaw-truenas-litellm-recreate-plan` : `compose_config=valid`, plan validé ;
- `just openclaw-truenas-litellm-recreate-apply` : conteneur recréé, `running=true`, `secrets_loaded=yes`, `secrets_missing_count=0` ;
- `just openclaw-truenas-secret-provenance` : `syntax_status=complete`, `runtime_status=complete`, `database_status=complete` ;
- les sept variables contrôlées, y compris `LANGFUSE_PUBLIC_KEY`, sont présentes et concordantes entre le fichier canonique et le conteneur ;
- `container_recreation_needed=false` et `DATABASE_URL=present`.

**Résolu** : drift d'environnement entre
`/mnt/cpool/secrets/runtime/litellm/.env.secrets` et le conteneur.
**Non démontré** : accès PostgreSQL, conservation des clés en DB,
provisionnement/budgets des clés virtuelles, alias `gpt-4.1*`,
bonne santé applicative de tous les endpoints. Un `DATABASE_URL`
présent n'est pas un test de connexion. La migration des agents reste
indépendante de cette correction et n'est pas réputée effectuée.


## Provisionnement virtuel OpenClaw — PR #280 (25 octobre 2026)

L'inventaire authentifié après la recréation affiche encore
`GET /v1/models=200` avec `workstation-qwen` et `qwen`
sur le modèle déclaré (la présence de `qwen` au runtime doit être
confirmée par la recette), et `GET /key/list=200`, `count=0`.
Les alias GPT `gpt-4.1` et `gpt-4.1-mini` restent absents.

Le script `scripts/truenas/provision-openclaw-litellm-keys.py`
utilise les deux valeurs déjà injectées dans le conteneur pour effectuer
`POST /key/generate`, budget `max_budget=2` pour chacune :
`openclaw-main` sur `workstation-qwen,qwen` et
`openclaw-cron` sur `workstation-qwen`.
Il n'imprime jamais les clés, bloque si leur valeur est identique ou
égale à la master key et refuse le provisionnement si `/key/list`
n'est pas vide. Le script ne suppose pas que sept variables
environnement équivalent à sept clés virtuelles.

```bash
just openclaw-truenas-virtual-keys-plan
just openclaw-truenas-virtual-keys-apply
just openclaw-truenas-model-keys-tunnel-dedicated-nonstandard
```

La première commande est non mutante. La deuxième écrit dans la DB
LiteLLM via l'API administrateur de l'instance TrueNAS. L'étape suivante
consiste à vérifier la présence des deux entrées, leur limitation
`max_budget=2`, les modèles autorisés et la persistance en base.
Une réponse API 200 et un compte de deux entrées ne prouvent pas
à eux seuls l'application effective des budgets. L'échec de la seconde
création peut laisser la première créée : le script refuse alors
automatiquement toute relance aveugle, pour une réconciliation manuelle.

Les variables des autres consommateurs (Reactive, IDE, n8n, etc.)
sont chargées mais **ne sont pas provisionnées par ce script**.


## Correction des recettes : exécution sur TrueNAS ou Workstation (25 octobre 2026)

**Cause du retour opérateur** : le checkout utilisé était
`/mnt/cpool/compose/nabla-compose` sur TrueNAS, mais les anciennes
recettes lançaient `ssh truenas` (port 22 par défaut) et exigeaient un
tunnel SSH `127.0.0.1:14000` propre à la Workstation.
La tentative de provisionnement n'a donc effectué **aucune écriture**.

Le chemin canonique est déjà décrit dans le skill
`.agents/skills/docker-compose-orchestration/SKILL.md`. La règle explicite
est ajoutée à `.agents/skills/local-first-quality/SKILL.md`.

Les recettes `openclaw-truenas-virtual-keys-plan`,
`openclaw-truenas-virtual-keys-apply` et
`openclaw-truenas-virtual-keys-status` détectent désormais l'hôte à
partir du chemin réel du dépôt. Sur TrueNAS elles exécutent
`sudo -n python3` en local. Depuis la Workstation, elles délèguent via
l'alias SSH `truenas` configuré avec le port 9922. La recette historique
`openclaw-truenas-model-keys-tunnel-dedicated-nonstandard` utilise le
nouveau statut contextuel ; son nom « tunnel » est conservé pour
compatibilité mais aucun tunnel n'est nécessaire sur TrueNAS.

### Commandes sur TrueNAS

```bash
cd /mnt/cpool/compose/nabla-compose
git pull --ff-only
just openclaw-truenas-virtual-keys-test
just openclaw-truenas-virtual-keys-status
just openclaw-truenas-virtual-keys-plan
just openclaw-truenas-virtual-keys-apply
just openclaw-truenas-virtual-keys-status
```

Les tests sont hors ligne ; `status` et `plan` n'écrivent rien.
`apply` est l'opération explicite qui demande à LiteLLM de créer les
deux clés virtuelles, chacune avec un budget maximal de 2. Le statut et
le plan exigent un inventaire HTTP 200 et les alias autorisés présents.
Le fait que les variables existent dans l'environnement n'indique pas
à lui seul une clé enregistrée en base.

### Commandes depuis la Workstation Ubuntu

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-truenas-virtual-keys-status
just openclaw-truenas-virtual-keys-plan
```

Ne pas utiliser `just openclaw-truenas-tunnel-check` depuis TrueNAS :
cette recette inspecte **un forward SSH initié sur Workstation**.


## Acceptation : création des deux clés TrueNAS et correction des tests (25 octobre 2026)

**Preuve opérateur réelle, depuis Workstation :**

- `just openclaw-truenas-virtual-keys-status` (avant) :
  `execution_target=workstation_ssh`, `models_allowlist=verified`,
  `existing_key_count=0`.
- `just openclaw-truenas-virtual-keys-plan` :
  `provisioning=planned`, `key_count=2`, `max_budget_each=2`.
- `just openclaw-truenas-virtual-keys-apply` :
  `openclaw-main_creation_http=200`,
  `openclaw-cron_creation_http=200`,
  `post_provision_inventory_http=200`, `post_provision_key_count=2`.
- `just openclaw-truenas-virtual-keys-status` (après) :
  `existing_key_count=2`, `provisioning=inspection_only`.

**Création observée : deux clés virtuelles sont maintenant retournées par
l'inventaire de LiteLLM TrueNAS.** Le compte ne prouve pas à lui seul
l'application effective des budgets, l'identité des deux entrées,
la persistance après redémarrage, ni le routage actuel d'OpenClaw.
Ne plus rejouer `apply` sur cet état sans réconciliation.

**Régression L1 distincte** : sur TrueNAS puis Workstation, les sept tests
du dispatch ont réussi ; deux tests du provisioner ont échoué avec
`TypeError: main() takes 0 positional arguments but 1 was given`.
L'implémentation recevait les arguments CLI seulement depuis `sys.argv`,
alors que les tests appelaient `main(["--apply"])` et `main(["--status"])`.
Correction : `main(argv=None)` avec `parser.parse_args(argv)`.
Les tests doivent être relancés sur le nouveau HEAD (aucun PASS inventé).

**Exécution canonique** :

- Workstation Ubuntu (`~/w/nabla-compose`) : tests unitaires et
  `just openclaw-truenas-virtual-keys-status` via SSH ;
- TrueNAS (`/mnt/cpool/compose/nabla-compose`) : opération Docker locale
  seulement lorsqu'un diagnostic ou une mutation runtime le nécessite ;
- aucun besoin de lancer la suite Python deux fois, ni d'utiliser un tunnel
  Workstation quand la commande tourne sur TrueNAS.


## 25 octobre 2026 — 429 persistant après création des clés TrueNAS

Nouvelle preuve Workstation :
`just openclaw-truenas-virtual-keys-test` **9/9 PASS**,
`just openclaw-truenas-virtual-keys-status` :
`execution_target=workstation_ssh`,
`models_allowlist=verified`, `existing_key_count=2`,
`provisioning=inspection_only`.

L'interface OpenClaw montre encore **« API rate limit reached. Please try
again later. »**. **Cela ne signifie pas que le provisioning a échoué.**
Il faut distinguer :
- la route Workstation `172.17.0.57:4000/v1` historiquement utilisée
  par `litellm-main` et `litellm-cron` ;
- les clés nouvellement créées uniquement sur le proxy TrueNAS
  `172.17.0.24:4000/v1` ;
- les modèles `qwen` / `workstation-qwen` autorisés par ces clés, par
  opposition aux anciens `gpt-4.1` / `gpt-4.1-mini` OpenClaw ;
- le budget effectif, la limite RPM/TPM, les éventuels cooldowns
  OpenClaw, et les limites appliquées par le proxy ou le fournisseur
  en amont.

**Audit nouveau, à lancer uniquement sur Workstation** :

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-429-attribution-test
just openclaw-429-attribution
```

Le premier exécute des tests unitaires hors ligne. Le second examine :
1. `openclaw.json` : routes et modèles principaux et `cron`,
   sans afficher les URL complètes ni les valeurs de clé ;
2. `agents/{main,cron}/agent/models.json` : overrides possibles
   qui peuvent maintenir l'ancienne route ;
3. sur TrueNAS, `/key/info` pour les deux clés connues, avec leur
   **hash SHA-256 uniquement dans la requête locale**, afin de classifier
   `spend`, `max_budget`, `rpm_limit`, `tpm_limit` et les scopes ;
4. `openclaw models status --json` : agrégats non identifiants
   d'authentifications inutilisables (cooldown/billing).

Les diagnostics ne lancent aucune génération ni `openclaw models
status --probe`. Si le schema OpenClaw évolue, l'audit doit retourner
`unrecognized_schema`, pas déclarer zéro profil indisponible.

Les verdicts possibles sont indépendants : `budget exhausted` sur la
clé TrueNAS, route OpenClaw Workstation inchangée, modèle non attribué
à la clé TrueNAS, ou cooldown au niveau OpenClaw. **Ne pas réexécuter
`openclaw-truenas-virtual-keys-apply`** : deux entrées existent.
Ne pas augmenter les budgets pour masquer un 429 non attribué.

La vraie bascule vers TrueNAS exige une configuration cohérente des
providers/modèles/SecretRefs et la vérification de l'identité de clé
réellement présentée par chaque agent. Le routage effectif de sessions
existantes et de l'auth SQLite reste non attesté par une simple lecture
de `openclaw.json`.

Documentation officielle :
- https://docs.openclaw.ai/help/faq-models
- https://docs.openclaw.ai/gateway/config-tools/custom-providers
- https://docs.openclaw.ai/concepts/model-failover


## Alignement LiteLLM générique Workstation → TrueNAS (25 octobre 2026)

**Contexte** : le diagnostic de la Workstation a réussi 21/21 contrats,
mais la commande `quota-audit` renvoyait `invalid choice`. Le code
`build_command()` acceptait ce mode et le provisioner le gérait ;
la liste `argparse --mode` du dispatcher ne le contenait pas.
Le choix CLI et le contrat de non-régression ont été corrigés.
L'ancienne chaîne s'arrêtait donc *avant* de lire le budget TrueNAS.

**Périmètre de synchronisation des modèles :**
- les alias Ollama génériques `llama3.2`, `llama3.1`,
  `llama3.8b`, `deepseek-coder-v2`, `qwen`, `gemma3`,
  `rr-json` utilisent le GPU Ollama Workstation
  `172.17.0.57:11434` ;
- `qwen` conserve la capacité d'outils déclarée sur TrueNAS pour
  OpenClaw, et reçoit le coût nul de la route locale ;
- `embedding` reste relayé via LiteLLM Workstation avec sa clé dédiée,
  `embedding-local` reste isolé sur Ollama TrueNAS pour rollback ;
- `fastapi-qwen`, `workstation-qwen`, Hermes, Redis, Langfuse,
  PostgreSQL et les deux clés virtuelles sont conservés ;
- les fournisseurs externes génériques facultatifs sont seulement
  documentés comme routes désactivées jusqu'à confirmation des
  secrets et disponibilités ; aucun secret nouveau n'a été généré ;
- **les routes et identifiants d'entreprise n'entrent pas dans le
  catalogue TrueNAS, y compris sous forme de commentaires** ;
- les fallbacks vers des alias GPT absents du proxy TrueNAS sont
  supprimés ; le routage utilise `least-busy`,
  `allowed_fails=1`, `cooldown_time=30`,
  `enable_pre_call_checks=true` et conserve une seule relance.

Ne pas confondre alignement de la déclaration TrueNAS et bascule
OpenClaw : les providers `litellm-main` et `litellm-cron` dans la
Workstation pointent toujours vers le LiteLLM Workstation. Les
deux clés récemment créées sur TrueNAS **ne corrigeront pas** le 429
tant que la route et le modèle OpenClaw ne sont pas adaptés.
La clé `cron` autorise `workstation-qwen`, et la clé `main`
autorise `workstation-qwen` et `qwen` ; elles n'autorisent
aucun modèle GPT.

### Vérification locale Workstation (sans CI)

```bash
cd ~/w/nabla-compose
git pull --ff-only
just litellm-truenas-generic-alignment-test
just openclaw-429-attribution-test
just openclaw-truenas-virtual-keys-quota
```

La dernière commande interroge les **métadonnées** des clés TrueNAS,
sans génération. Une clé au budget épuisé retourne un code non nul
sans modifier la limite.

### Publication runtime TrueNAS — après validation locale

```bash
cd /mnt/cpool/compose/nabla-compose
git pull --ff-only
sudo -n python3 scripts/truenas/recreate-litellm-env.py
sudo -n python3 scripts/truenas/recreate-litellm-env.py --apply
```

Le plan lit les métadonnées du Compose existant. L'application
recrée uniquement le service `litellm` en reprenant le fichier de
configuration lié au checkout TrueNAS ; elle vérifie à la fin que
les sept variables prévues sont encore injectées. La preuve de
readiness applicative et l'inventaire des modèles nécessitent le
contrôle ultérieur sur la Workstation :

```bash
just openclaw-truenas-virtual-keys-status
just openclaw-truenas-virtual-keys-quota
```

Aucun déploiement ni correction de la configuration privée OpenClaw
n'a été exécuté dans la PR ; les tests demandés doivent être rejoués
au nouveau HEAD. L'absence de budget épuisé ne prouve pas l'absence
d'un rate limit RPM/TPM en amont.


## 25 octobre — inventaire des modèles après recreation TrueNAS

Preuve fournie après le changement `apps/litellm/config.yaml` :
`compose_config=valid`, `container_running=true`,
`secrets_loaded=yes`, `secrets_missing_count=0`.
Sur Workstation, `openclaw-truenas-virtual-keys-status` retournait
`models_inventory=unverified` et sortait avec code 2. Le diagnostic
antérieur de `/key/info` avait pourtant retourné 200 avec
`openclaw-main` et `openclaw-cron`, scope exact, budget 2 chacun
et `spend=0.0` (avant ce dernier redéploiement). **Ne pas inférer
la perte des deux clés** ni une panne d'embeddings à partir du code 2.

Le script `scripts/truenas/provision-openclaw-litellm-keys.py --status`
est étendu pour afficher séparément, sans corps de réponse :
`litellm_liveliness_http`, `models_inventory_http`,
`key_inventory_http`, `models_inventory`, `key_inventory`
et `existing_key_count` si la liste reste lisible.
Un status HTTP 200 dont le schéma JSON est invalide est distingué
d'un HTTP 500. Le statut **continue les lectures** même après échec
du premier endpoint. Aucun secret ni message brut d'erreur n'est
imprimé.

Procédure depuis Workstation :

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-truenas-virtual-keys-test
just openclaw-truenas-virtual-keys-status
just openclaw-truenas-virtual-keys-quota
```

Sur HTTP 5xx, contrôler le healthcheck Docker et la configuration
effective du service **sur TrueNAS** (sans exporter `docker inspect`
avec les variables de secrets), puis les erreurs redigées des logs.
Ne pas relancer `apply` pour créer des clés déjà existantes.
L'alignement de `apps/litellm/config.yaml` a été contrôlé
statiquement ; `docker compose config --quiet` ne garantit pas
que LiteLLM accepte le YAML et ses modèles au démarrage.

La restauration du modèle de briefing se trouve dans
`apps/openclaw/workstation/MORNING_BRIEFING.md`. Elle est indépendante
de ce diagnostic, des clés virtuelles et de la version des embeddings.


## 2026-10-25 — mitigation automatique du 429 sans copier les logs de la UI

Les preuves opérateur, après correction du test et de `memory.search`,
confirment huit contrats PASS, `litellm-main` et `litellm-cron` toujours
sur `172.17.0.57:4000/v1`, modèle par défaut `gpt-4.1` et
`cron` héritant à tort du provider principal. L'embedding est un
chemin indépendant, `127.0.0.1:4000/v1` avec SecretRef
`openclaw-embeddings`. Ne pas le migrer pour réparer un 429 de chat.

Le nouveau diagnostic `scripts/workstation/diagnose-openclaw-429-auto.py`
lit *depuis Workstation*, sans intervention dans l'UI :
- `GET http://127.0.0.1:4000/spend/logs/v2`, page bornée à 100
  entrées et deux heures, avec master key **uniquement sur loopback**,
  si disponible dans l'environnement du shell ;
- `journalctl --user` pour `openclaw-gateway.service` et
  `litellm.service` ;
- `docker logs litellm` local si un conteneur existe.

Tous les flux bruts restent en mémoire et sont supprimés. Le script
affiche seulement des compteurs d'erreurs, d'incidents budget, de débit,
de timeout, d'authentification, et des modèles d'une liste sûre.
Les requêtes rejetées avant facturation peuvent être **absentes**
des spend logs. Zéro ligne **n'est pas une preuve de santé**.
Aucune requête de génération, aucun payload, aucun jeton ni ID
de requête ne sont affichés.

### Correction locale de l'identité cron

`scripts/workstation/repair-openclaw-429.py` est un changement
**explicite et limité**, après contrôle préflight. Il requiert :

1. config `~/.openclaw/openclaw.json` et clé privée
   `~/.local/share/nabla-compose/openclaw-cron.key`, fichiers owner-only ;
2. deux providers `litellm-main` et `litellm-cron` pointant sur
   l'instance LiteLLM Workstation prévue ;
3. concordance exacte de la credential du provider `litellm-cron`
   avec le fichier cron privé et différence de la clé principale ;
4. `GET /v1/models` autorisé par la clé cron sur la seule boucle locale
   et présence de `gpt-4.1` ;
5. un agent `cron` **unique** dans `agents.list`, héritant de
   `litellm-main/gpt-4.1` ou déjà sur `litellm-cron/gpt-4.1`.

À l'application, seul le modèle de l'agent `cron` devient
`litellm-cron/gpt-4.1` sans fallbacks, et
`agents.defaults.maxConcurrent` est borné à **1**. Ce réglage réduit
les appels parallèles mais peut allonger la file d'attente.
La configuration complète précédente est sauvegardée en **0600**
hors Git puis remplacée atomiquement. Avec `--restart-gateway`,
un échec de redémarrage déclenche une tentative de restauration.
Le script refuse les prérequis incertains au lieu de forcer une
rotation ou de réutiliser une clé plus privilégiée.

**Depuis Workstation uniquement** :

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-429-fix-test
just openclaw-429-auto
just openclaw-429-fix-plan
just openclaw-429-fix-apply
python3 scripts/workstation/openclaw-route-metadata.py
```

Exécuter les commandes dans un shell enfant `bash <<'...'`
avec `set -euo pipefail` pour arrêter à la première anomalie.

**Limitations** :
- L'application modifie la **configuration locale OpenClaw**, pas la
  base/clé virtuelle LiteLLM. Aucun budget ni modèle backend ne change.
- Une limite upstream GPT ou une limite RPM/TPM de LiteLLM peut
  produire encore des 429. Ne pas prétendre le contraire : il faudra
  une nouvelle observation automatisée après la modification.
- La configuration **effective des sessions déjà ouvertes** reste à
  vérifier ; des épinglages de modèle/session peuvent prévaloir sur
  la nouvelle valeur par défaut de l'agent.
- Le plan ne s'applique pas si la clé `cron` n'a pas accès à
  `gpt-4.1`. Ne pas élargir automatiquement cette clé.
- La politique de heartbeat et les index embeddings restent inchangés.

Références :
- https://docs.litellm.ai/docs/proxy/cost_tracking
- https://docs.openclaw.ai/gateway/config-agents/models
- https://docs.openclaw.ai/gateway/config-tools/custom-providers


### Dette complémentaire — relances LiteLLM Workstation

Le fichier LiteLLM Workstation fourni par l'opérateur contient
`router_settings.num_retries: 5`. Il existe plusieurs déploiements
amont portant le même alias GPT, avec des limites potentiellement
indépendantes. Cinq relances peuvent amplifier des 429, mais
**le nombre exact de tentatives n'est pas encore attribué**.
La configuration Workstation n'est pas identifiée comme un fichier
de déploiement actif dans ce dépôt ; ne pas remplacer la configuration
pro de Workstation par `apps/litellm/config.yaml`, qui appartient
à TrueNAS. La mitigation OpenClaw ci-dessus conserve les modèles
GPT et réduit la concurrence du client ; une réduction des retries
du routeur Workstation reste un changement distinct, à réaliser
depuis son fichier de configuration réellement monté après audit.


## 2026-10-25 — `openclaw update` npm failed, 429 repair test gate (Workstation)

L'interface OpenClaw annonce `2026.10.7` disponible ; la CLI observée
est toujours `2026.9.5`. La tentative `openclaw update` a rapporté
`global-install-failed` avec `npm exit 1`, et a enregistré :
`~/.npm/_logs/2026-10-25T19_43_24_104Z-debug-0.log`.

**Cause exacte npm non encore prouvée.** Ne pas attribuer sans preuve à
un conflit de plugin, à des permissions, au registre ou au runtime Node.
Le message UI `config edited outside OpenClaw` indique une modification
externe observée ; il ne démontre pas une corruption ou une migration
cassée. Éviter de relancer immédiatement `openclaw update` en boucle.

La commande `just openclaw-429-fix-all` s'est arrêtée à son premier
ensemble de tests : 6/6 collecteur PASS, 8/10 réparation PASS,
2 erreurs d'assertion `blocked_write`. **Aucun fix ni redémarrage
Gateway n'a été exécuté par cette invocation.**

### Cause déterministe de ces deux tests

La signature `apply_config(old, new, path=CONFIG)` capturait
`~/.openclaw/openclaw.json` lors de l'import du module. Les tests
injectaient `mod.CONFIG` vers un répertoire temporaire, sans modifier
ce chemin par défaut. L'écriture tentait alors le fichier d'origine,
et les tests rapportaient `blocked_write`. Correction :
`apply_config(old, new, path=None)` puis `path = CONFIG` à l'appel.
Un test de régression verrouille cette absence de chemin figé.

### Collecte npm locale, expurgée, sans mise à jour

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-update-recovery-local
```

Cette recette ne lance ni `npm install`, ni `openclaw update`, ni
requête de modèle. Elle exécute les tests ciblés, examine seulement
le **fichier npm nommé ci-dessus** avec un contrôle d'appartenance,
de type et de taille, puis classe des erreurs connues :
`permission`, `install_collision`, `runtime_engine`,
`registry_or_integrity`, `network`, `dependency_resolution`,
`build_toolchain` ou `unknown`. Elle annonce les versions de
Node/npm/OpenClaw et qualifie le prefix npm sans afficher les paths,
tokens, lignes de journaux, registres privés ni commandes brutes.

Si `npm_error_category=unknown`, demander davantage de preuves
par **le diagnostic automatisé**, pas en recopiant les logs bruts.
`openclaw update status --json` et `openclaw update --dry-run`
sont les interfaces officielles de suivi ; leurs sorties brutes
peuvent contenir des chemins privés et ne doivent pas être publiées
dans un ticket/chat sans filtrage.

Le contrat de rollback après correction ne change pas le
`memory.search` ni les clés d'embeddings. **Ne pas lancer**
`just openclaw-429-fix-apply` dans la même procédure de mise à jour npm
sans validation des tests, du fichier cible et des credentials.
Les éditeurs OpenClaw natifs (`config patch`, RPC `config.patch`)
sont préférables aux éditions directes pour éviter le warning
`config edited outside OpenClaw` ; une migration vers ce mécanisme
reste distincte de la correction de chemin ci-dessus.

Références officielles :
- https://docs.openclaw.ai/install/update-troubleshooting
- https://docs.openclaw.ai/install/updating
- https://docs.openclaw.ai/cli/config


### 25 octobre, 23:21 Europe/Paris — npm triage tests blocked by group umask

New operator proof on Workstation:
`just openclaw-update-recovery-local` exited during
`just openclaw-update-npm-test`, with 4 tests PASS and two failures:
`test_known_permission_failure_without_printing_path_or_token`
and `test_valid_latest_log_selected_without_network`.
`just openclaw-429-fix-all` was **not run** by the guarded shell.

**Deterministic fixture bug**: `tests/test_openclaw_update_npm_diagnostic.py`
created `.npm/` and `.npm/_logs/` using the operator's `umask`.
On a default group-writable `umask 0002`, temporary fixture
directories received mode `0775`. The production `safe_log()`
intentionally refuses directories writable by group or others,
making both expected-positive fixture reads return `None`.
This was reproduced locally with `umask 0002`.

**Fix committed**: after creating fixture directories, explicitly
`chmod 0700` the `.npm` and `_logs` parents; preserve the
production fail-closed rules, and add two negative contracts refusing
group-writable parents. Offline permission behavior was checked,
but all target repository tests remain **NOT_RUN in the agent runtime**
until confirmed on Workstation.

The recovery recipe keeps the npm log scan informational: if the
specific log has been rotated or is unsafe, report `WARN` and
allow the later independent 429 test/repair path; never claim a
successful OpenClaw update from a missing npm diagnostic.

Workstation command:

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-update-recovery-local
just openclaw-429-fix-all
```

If the exact error class is still `unknown`, use the sanitized
update run status in `openclaw update status --json` privately
rather than posting raw log contents.


## 25 octobre 2026 — dernier incident : moteur Node et agent par défaut

Preuve opérateur sur Workstation :
- `just openclaw-update-recovery-local` : suites npm 8/8,
  collecteur 429 6/6, réparation 11/11, routes 8/8 **PASS**
  (33 tests exécutés, zéro CI) ;
- diagnostic du log du 25/10 19:43 : `runtime_engine`,
  Node `24.18.1`, npm `12.2.0`, OpenClaw `2026.9.5`,
  préfixe global npm dans HOME et apparemment inscriptible ;
- `just openclaw-429-fix-plan` : `blocked_reason=agents_list_missing`.
  Le shell `set -e` a interrompu l'exécution **avant** l'application
  et le redémarrage. Aucun 429 corrigé ni patch Gateway appliqué par
  cette tentative.

**Correction du runtime :** la release 2026.10.7 requiert Node
`>=24.22.1 <25 || >=26.12.1`. Les pinning du dépôt
`.nvmrc` et `mise.toml` ciblent maintenant `24.22.1`. Ce commit
ne change **pas** la version du Node actif sur Workstation, du
Node enregistré dans l'unité systemd, ni l'installation globale
OpenClaw. Le diagnostic npm imprime un verdict de compatibilité.

Réparer le runtime par le gestionnaire réellement utilisé, une seule
fois, puis vérifier la commande `node --version` **dans le même
environnement que celui d'OpenClaw**. Pour un poste géré par mise :
`mise install node@24.22.1`, puis
`mise exec node@24.22.1 -- node --version`.
Pour un poste géré par nvm : `nvm install v24.22.1` puis
`nvm use v24.22.1`. Ne pas lancer `sudo npm install -g`, ne
pas écraser un préfixe étranger et ne pas relancer `openclaw update`
tant que le Node du processus d'installation et le rollback ne sont
pas vérifiés. Vérifier `openclaw update status --json` en privé
avant une nouvelle tentative.

**Correction de l'hypothèse `agents.list` :** l'absence du champ
signifie que l'installation peut n'avoir qu'un agent implicite.
Les jobs cron ne sont pas des agents `cron` par définition.
Le plan respecte trois cas :
- un agent `cron` explicitement présent : continuer le contrôle
  d'autorisation et la séparation de modèle prévue ;
- aucun agent `cron` et `agents.list` absent ou vide : modifier
  **seulement** `agents.defaults.maxConcurrent=1`, sans ajouter de
  faux agent et sans affirmer que les jobs sont maintenant isolés ;
- structure invalide ou doublon : refuser le changement.

Pour le cas « agent implicite », l'application utilise le
**RPC OpenClaw `config.get` + `config.patch`**, un `baseHash`
optimiste, une sauvegarde 0600 hors dépôt, et un contrôle de la
valeur appliquée. Si la réponse RPC est perdue après écriture,
le script tente une restauration ciblée de l'ancienne valeur
via un nouveau `baseHash`. Il **n'effectue aucun fallback**
vers une écriture directe du `openclaw.json` actif.
Le Gateway prend en charge sa propre procédure de reload/restart ;
le script ne force pas de seconde relance dans ce cas.

**Limite résiduelle** : `maxConcurrent=1` limite les exécutions
parallèles, mais un fournisseur upstream peut toujours retourner
un 429. Les jobs cron existants peuvent conserver un
`payload.model` et une identité d'inférence distincte :
les changements de modèle/credential de jobs demandent un inventaire
de leurs paramètres et ne doivent pas être déduits du seul
`openclaw.json`. Les embeddings et index 768D ne changent pas.

Contrôle Workstation au nouveau HEAD (sans CI ni modèle payant) :

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-update-recovery-local
just openclaw-429-fix-all
```

**Preuves du correctif au nouveau HEAD** : à confirmer par l'exécution
locale des tests et du RPC ; aucun accès direct à la Workstation n'est
possible depuis l'agent ici.

Documentation OpenClaw :
- https://docs.openclaw.ai/install/node-compatibility
- https://docs.openclaw.ai/gateway/configuration/config-rpc
- https://docs.openclaw.ai/automation/cron-jobs/payloads


### 25 octobre 2026 — cohérence des versions Workstation et du lockfile mise

L'audit du dépôt a mis au jour une autre dérive de runtime :
`mise.lock` continue à **enregistrer Node 24.18.1**, avec les
checksums propres à cet ancien artefact, alors que `.nvmrc`,
`mise.toml` et `.envrc` visent maintenant `24.22.1`.
Les scripts `diagnose-openclaw.sh` et
`prepare-openclaw-systemd.sh` utilisaient également des chemins
absolus figés sur `24.18.1`. Ils ont été adaptés pour inspecter
l'identité réelle du Gateway ou la cible déclarée ; le script de
préparation ne modifie aucun service.

**Ne jamais réutiliser ni recopier les anciens checksums sous une
nouvelle version.** La commande explicite
`just openclaw-node24-runtime-install` exécute :
`MISE_SAFE=1 mise lock node@24.22.1`, puis
`mise install --locked node@24.22.1`, puis vérifie
`mise exec node@24.22.1 -- node --version`. Cette séquence
régénère les URL/checksums depuis mise au lieu de les inventer.
Elle peut **modifier le `mise.lock` local** ; conserver et revoir
ce diff avant de le publier dans Git. La PR ne prétend pas contenir
les checksums Node 24.22.1 tant qu'ils ne sont pas validés.

L'installation de la nouvelle version de Node **ne déplace pas**
automatiquement le paquet global `openclaw`, ne réécrit pas le
service systemd et ne prouve pas le succès de `openclaw update`.
Le propriétaire actuel du package peut rester l'ancien préfixe
`mise/installs/node/24.18.1`. Ne pas effacer cet ancien préfixe
avant la validation de la nouvelle installation, du démarrage Gateway,
du `memory status` et des canaux.

L'application du fix 429 pour un agent implicite n'exige désormais
**aucune clé cron** : seule la concurrence est réduite. La séparation
d'identité exige un véritable agent `cron` explicitement déclaré
ou une réconciliation prouvée des jobs. Le patch du cas implicite
est natif et garde une sauvegarde owner-only.

Ces chemins sont indépendants : ne pas confondre correction du
`EBADENGINE` et preuve de disparition des 429.


## 2026-10-25 — échec du patch natif : `blocked_gateway_snapshot`

L'opérateur a relancé sur Workstation la séquence de récupération.
Les tests npm (10/10), collecteur 429 (6/6), réparation (20/20) et routes
(8/8) sont PASS, soit **44 tests**. Le diagnostic historique indique
Node 24.18.1 et `runtime_engine` ; la commande
`mise exec node@24.22.1 -- node --version` retourne **v24.22.1**.
Le `mise.lock` local a été régénéré avec des artefacts officiels pour
sept plateformes ; des avertissements de lockfile concernant d'autres
outils globaux restent non bloquants. Ne pas supprimer ni forcer ce
`mise.lock` sans vérifier son diff local.

Le plan OpenClaw a confirmé `repair_scope=concurrency_only`,
`cron_key_access=not_required` et `global_concurrency=1`.
L'application a retourné **`native_config_patch=blocked_gateway_snapshot`**
avant toute mutation, sans redémarrer le Gateway.

**Cause :** notre contrôle comparait le `hash` de `config.get` au
SHA-256 des seuls octets de `~/.openclaw/openclaw.json`. C'est une
erreur de protocole : le `hash` fourni par OpenClaw est **opaque**,
et sa révision peut couvrir les identités et le contenu des fichiers
`$include` en plus du fichier racine. Le hash n'est pas un checksum
local à recalculer. Ne pas utiliser `configRevisionHash` ni
`appliedConfigHash` à la place du champ `hash`.

**Correction versionnée :** le programme transmet la révision
exactement reçue par le Gateway comme `baseHash`, sans conversion
hexadécimale ni comparaison à un SHA-256 local. Il vérifie que le
fichier local n'a pas changé avant et après le RPC `config.get`,
vérifie l'identité du chemin lorsqu'elle est exposée et protège le
patch par le mécanisme CAS du Gateway. Le rollback, si nécessaire,
récupère **une nouvelle révision opaque** avant la tentative de
réparation. Il ne remplace jamais directement le fichier de
configuration pour contourner un refus RPC.

Le mode `plan` du cas `concurrency_only` vérifie désormais aussi la
présence du snapshot Gateway en **lecture seule**. Ses sorties ne
contiennent aucune valeur de secret, aucun hash brut, ni JSON de config.
Des contrats couvrent les révisions opaques non SHA, les changements
concurrents, les chemins erronés, le plan sans écriture et le rollback.

**Exécution Workstation (aucun CI)** :

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-429-fix-test
just openclaw-429-fix-plan
just openclaw-429-fix-apply
python3 scripts/workstation/openclaw-route-metadata.py
just openclaw-429-auto
```

`openclaw-429-fix-apply` est **mutant** (patch natif ciblé et
rechargement géré par le Gateway). Vérifier le résultat avant de
relancer la commande. `maxConcurrent=1` n'est pas un remède universel
à une limite RPM/TPM upstream, ni une séparation d'identité des
jobs cron ; ceux-ci nécessitent un audit distinct.

**L'installation du Node 24.22.1 n'a pas automatiquement mis à jour
l'ancien préfixe npm d'OpenClaw ni le binaire Node du service systemd.**
Conserver l'ancien préfixe jusqu'à preuve de migration réussie. Ne
pas relancer `openclaw update` avant un contrôle du runtime
effectivement utilisé par le service.

Documentation :
https://docs.openclaw.ai/gateway/protocol/rpc-talk-config-and-agents
https://docs.openclaw.ai/gateway/configuration/config-rpc


## 2026-10-26 — récupération opérationnelle et upgrade rootless vers OpenClaw 2026.10.7

Les **dernières** preuves opérateur montrent désormais
`native_config_patch=applied` et `gateway_restart=managed_by_openclaw`.
Le Gateway utilise `maxConcurrent=1` : le diagnostic local de deux
heures trouve **zéro indicateur 429**, et un indicateur de timeout.
Le collecteur n'avait pas la master key Workstation (API
`/spend/logs/v2` non interrogée) : ceci ne prouve ni zéro requête
refusée, ni une guérison complète du fournisseur GPT. Le modèle
`litellm-main/gpt-4.1` et le secret embeddings restent inchangés.

Le blocage d'upgrade reste séparé : `openclaw --version=2026.9.5`,
Node actif `24.18.1`, Node `24.22.1` installé dans le préfixe
`mise` mais non sélectionné partout. Le log npm original avait
montré `runtime_engine`. Les avertissements de `mise.lock`
concernant des outils globaux non verrouillés n'empêchent pas
l'installation ciblée déjà prouvée de Node 24.22.1.

**Source de version et de compatibilité (consultée 2026-10-26) :**
OpenClaw stable 2026.10.7, Node 24.22.1 ou Node 26.12.1 minimum
sur leurs branches respectives. Version épinglée **exactement**
pour ne pas prendre un canal beta par erreur. Documents :
- https://docs.openclaw.ai/install/updating
- https://docs.openclaw.ai/install/update-troubleshooting
- https://docs.openclaw.ai/install/node-compatibility
- https://github.com/openclaw/openclaw/releases/tag/v2026.10.7

### Pourquoi ne pas faire un simple `sudo npm i -g` ?

Le service systemd user et le paquet OpenClaw appartiennent à un
ancien préfixe `mise`. Une commande npm sur le nouveau PATH
pourrait installer ailleurs et laisser le Gateway sur 2026.9.5.
L'updater lui-même demande une vérification de propriétaire de
service/paquet et du runtime. Le script de ce dépôt
`scripts/workstation/upgrade-openclaw-mise.py` effectue une
**migration côte à côte**, sans effacer le précédent paquet.

La migration est volontairement fractionnée :

1. **Test (offline)** — `just openclaw-upgrade-local-test`.
   Tous les appels systemd, npm, HTTP et OpenClaw sont simulés.
2. **Plan (lecture seule)** — `just openclaw-upgrade-local-plan`.
   Vérifie `mise` Node, l'unique service
   `openclaw-gateway.service` du compte courant, son
   `ExecStart` attendu et le statut du paquet versionné.
3. **Stage (mutation isolée)** — `just openclaw-upgrade-local-stage`.
   Exécute npm avec le Node 24.22.1 **par chemin absolu** et le
   préfixe npm du même Node ; installe uniquement le paquet
   `openclaw@2026.10.7` depuis le registre npm officiel.
   Vérifie `package.json` et la sortie de version.
   **Le Gateway ancien continue à tourner** et aucune config,
   identité de clé, mémoire ou service systemd n'est modifié.
4. **Activation (maintenance explicite)** —
   `just openclaw-upgrade-local-activate` :
   arrête la seule unité systemd utilisateur connue ; sauvegarde
   de manière cohérente `~/.openclaw` en tar.gz privé 0600 via
   `backup-openclaw.sh` ; crée uniquement
   `~/.config/systemd/user/openclaw-gateway.service.d/20-nabla-openclaw-upgrade.conf`
   (0600), avec `ExecStart` sous Node 24.22.1 et paquet
   2026.10.7. Le drop-in préserve les autres fichiers
   `EnvironmentFile`, les variables de l'unité et le port 18789.
   `daemon-reload`, `start`, puis sonde locale `/readyz`.
   Le script refuse un drop-in concurrent ou un service inconnu.
5. **Vérification sans modèle payant** —
   `just openclaw-upgrade-local-verify` :
   statut unité, version de paquet, owner Node, `/readyz`,
   `doctor --lint --json` et `memory status` expurgés.
   Vérifier ensuite les canaux et sessions de manière explicite.

**Procédure Workstation** :

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-upgrade-local-test
just openclaw-upgrade-local-plan
just openclaw-upgrade-local-stage
just openclaw-upgrade-local-plan
just openclaw-upgrade-local-activate
just openclaw-upgrade-local-verify
```

Le CLI `openclaw` du shell peut encore désigner l'ancien préfixe
après activation. Pour interroger explicitement la nouvelle version :

```bash
mise exec node@24.22.1 -- openclaw --version
```

ou en chemin absolu via la CLI du nouveau préfixe. Vérifier
`openclaw --version` dans un nouveau shell avant de supprimer
l'ancien paquet, en gardant le service stable d'abord.
La CLI `openclaw update` ne doit plus être lancée avec l'ancien
Node/prefix sur PATH.

### Limites et retour arrière

**Ne jamais effacer les données SQLite ni réindexer la mémoire.**
Une activation 2026.10.7 peut migrer des schémas SQLite et plugins.
L'ancien 2026.9.5 ne saurait pas forcément relire ces données.
Si le nouveau Gateway ne démarre pas, le script **n'effectue aucun
rollback automatique des bases** ; il garde l'ancien package et la
sauvegarde cohérente dans `~/Backups/openclaw`. Examiner le code
d'échec, récupérer les données depuis une sauvegarde compatible
uniquement sous contrôle utilisateur, puis rétablir l'unité.
Un échec pendant la **sauvegarde** (avant activation) relance
l'ancien service automatiquement et ne crée aucun drop-in.

Ne pas exécuter `doctor --fix`, ne pas réinstaller les plugins
à l'aveugle et ne pas lancer un modèle facturable durant le
cutover. Les warnings de migration Slack sont une dette distincte :
`doctor --lint` et les diagnostics des canaux servent à décider
de la correction après upgrade. Les jobs cron sans agent nommé
ne deviennent pas un agent distinct lors de cette migration.

Les actions du script sont strictement limitées à la Workstation ;
aucune route professionnelle n'est copiée vers le TrueNAS et
les clés virtuelles `openclaw-main`, `openclaw-cron`,
`openclaw-embeddings` ne sont pas reprovisionnées.


## 2026-10-26 — OpenClaw CLI 2026.10.7 fonctionne, mais stage déclaré en échec

**Retour Workstation** :
- `just openclaw-upgrade-local-test` : **13/13 PASS** au HEAD précédent ;
- `upgrade_target=2026.10.7`, `node_target=24.22.1`,
  `runtime_compatible=yes`, `gateway_service_owner=verified`,
  `gateway_service_running=yes`, `old_package_detected=no`,
  `staged_package=not_ready` ;
- `--stage` : `install_failed_or_unverified`,
  `npm_error_category=unknown`, code 2 ; **aucun cutover
  systemd** n'a été lancé car le `justfile` utilise fail-fast ;
- `mise exec node@24.22.1 -- openclaw --version` :
  **OpenClaw 2026.10.7 (157d8c2)** ;
- le smoke test existant a renvoyé
  `OK model smoke: litellm-main/gpt-4.1 returned OK`.
  Cette preuve concerne la conversation existante, pas le Gateway
  sous le nouveau Node ; ne pas consommer un deuxième smoke pendant
  les 24 heures de cooldown.

**Défaut du stage corrigé :** le script exigeait
`dist/index.js` et refusait un paquet dont le `bin` npm était
`openclaw.mjs`. L'entrypoint npm déclaré officiellement dans le
`package.json` OpenClaw est `openclaw.mjs`. La vérification
examine désormais le nom `openclaw`, la version du manifeste, le
`bin.openclaw` sûr, l'exécution directe du CLI avec le Node cible,
et l'absence des marqueurs `openclaw-lifecycle-pending` ou
`dist/openclaw-install-guard`. Elle ne considère plus le **seul**
exit code npm comme preuve d'une installation cassée.

Un stage déjà validé retourne `upgrade_stage=already_verified`
**sans relancer npm**. Si npm retourne un code non nul mais le paquet
est complet et vérifié, le stage signale
`npm_install_exit=nonzero_but_package_verified`. Si un paquet
partiel subsiste, il refuse un nouvel écrasement et affiche
uniquement `package_manifest`, `package_cli_entry` et
`lifecycle_marker`, sans journaux, secrets ni chemins privés.

La découverte de l'unité systemd reconnaît maintenant l'ancien
`dist/index.js` et le nouveau `openclaw.mjs`, y compris quand
le Node apparaît deux fois dans les champs `path` et `argv[]`.
Après la bascule, le service **doit** utiliser le Node exact du
préfixe cible, pas `/usr/bin/node`. Les chemins d'embeddings,
la base mémoire, les clés virtuelles et les canaux ne changent pas.

**Nouvelle exécution Workstation :**

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-upgrade-local-test
just openclaw-upgrade-local-plan
just openclaw-upgrade-local-stage
just openclaw-upgrade-local-activate
just openclaw-upgrade-local-verify
```

Les deux premières étapes n'écrivent rien. Le stage est idempotent ;
l'activation est la seule étape qui arrête le Gateway, crée la
sauvegarde cohérente et met en place le drop-in systemd. La
vérification finale impose readiness, Doctor lint et statut sain
des deux index mémoire. **Les nouveaux tests de ce commit restent
à exécuter sur la Workstation**. Si stage refuse un paquet marqué
incomplet, ne pas effacer de fichier dans `node_modules` ni
contourner le marqueur : examiner la sortie catégorisée et préparer
une réparation ciblée.

Sources officielles :
- https://www.npmjs.com/package/openclaw/v/2026.10.7
- https://docs.openclaw.ai/install/installer
- https://docs.openclaw.ai/cli/doctor/lint


## 2026-10-26 — Stage bloqué par un paquet npm incomplet sous Node 24.22.1

Nouvelle preuve Workstation après 19/19 tests de migration PASS :
`upgrade_stage=blocked_partial_or_foreign_package`,
`package_manifest=absent_or_different`,
`package_cli_entry=missing_or_unsafe`,
`lifecycle_marker=absent`,
`npm_reinstallation_attempted=false`.
Le Gateway historique est actif, le propriétaire du service est vérifié,
et aucun cutover n'a eu lieu. Un autre CLI exécuté via
`mise exec node@24.22.1 -- openclaw --version` avait répondu
`2026.10.7` : cela ne prouve **pas** que le répertoire npm du Node
24.22.1 est complet ou qu'il est propriétaire de ce CLI.

**Correction** : le script utilise maintenant un préfixe de staging
isolé `~/.local/share/nabla-compose/openclaw-stage/2026.10.7`
lorsque le dossier global `.../mise/installs/node/24.22.1/lib/node_modules/openclaw`
est déjà présent mais ne passe pas le contrôle de manifeste/bin.
Il n'efface, ne déplace et ne remplace **aucun** fichier de ce dernier.
`npm` reçoit l'option `--prefix` vers ce préfixe isolé,
avec Node 24.22.1 exécuté par chemin absolu.

Le stage vérifie avant le téléchargement les permissions et l'absence
de symlink des parents dédiés, puis le manifeste, le nom du paquet,
`bin.openclaw`, l'absence de marqueurs d'installation interrompue,
et la sortie de la CLI sous le Node cible. Une installation isolée déjà
valide est réutilisée sans relancer npm. Si un stage isolé est également
incomplet, le script s'arrête **sans écrasement** et affiche seulement
la raison contrôlée ; aucune trace brute npm, aucun secret ni prompt.

Lors de `activate`, le drop-in systemd peut référencer le
`openclaw.mjs` du préfixe isolé tout en lançant le binaire Node
**du préfixe mise 24.22.1**. `unit_exec` valide cette combinaison
exacte, et refuse `/usr/bin/node` ou un paquet extérieur au staging
autorisé. La sauvegarde cohérente et les contrôles mémoire restent
obligatoires.

**Commande opérateur Workstation :**

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-upgrade-local-test
just openclaw-upgrade-local-plan
just openclaw-upgrade-local-stage
just openclaw-upgrade-local-activate
just openclaw-upgrade-local-verify
```

Les tests nouvellement ajoutés (dont les contrats de sécurité du
préfixe isolé) sont **en attente de validation Workstation**.
Ne pas contourner un nouveau refus de stage par `rm -rf`,
`npm install -g --force` ou un démarrage depuis des fichiers
partiellement installés. `activate` est une opération de maintenance :
elle arrête temporairement le Gateway, sauvegarde `~/.openclaw`,
installe un drop-in user et vérifie `/readyz`. Aucun reindex ni
changement de clé LiteLLM n'est réalisé. Le smoke `gpt-4.1` a déjà
réussi ; respecter la période de 24 h avant tout autre smoke payant.


## 26 octobre 2026 — `unsafe_prefix` pendant le stage isolé

Dernière preuve Workstation : **26/26 tests PASS**, Gateway historique
toujours actif, `/readyz=200`, Node `24.22.1` compatible.
`just openclaw-upgrade-local-stage` a retourné
`stage_prefix=isolated_prefix`, `upgrade_stage=unsafe_prefix`.
L'activation indépendante a refusé `blocked_preflight` et le contrôle
final a légitimement signalé `functional_contract=partial_or_unverified` ;
**aucune bascule effective de l'unité systemd n'est prouvée**.

Le staging utilisait
`~/.local/share/nabla-compose/openclaw-stage/2026.10.7`.
Le contrôle refuse toute composante du chemin group-writable ou
symlink. La cause précise n'a pas été imprimée à l'époque.
Un des répertoires partagés peut légitimement avoir un mode 0775
(`umask 0002`) ; il ne faut **pas** imposer `chmod 0700` à
`~/.local/share/nabla-compose`, ni à ses autres services.

**Correction dans PR #280** : installer désormais dans
`~/.openclaw-upgrade-stage/2026.10.7`, avec uniquement des
répertoires nouvellement créés en 0700. Les trois composants contrôlés
sont `home`, `stage_base` et `stage_target`.
`stage_security` produit une catégorie constante telle que
`safe`, `symlink_stage_base`,
`group_or_world_writable_stage_target` ou
`wrong_owner_home`, sans exposer le chemin ni modifier les permissions
d'autres applications. Le stage refuse tout propriétaire ou chemin
inattendu et n'exécute pas npm sur un préfixe non sûr.

Le code utilise des `mkdir(mode=0o700)` successifs, et **non**
`Path.mkdir(parents=True)` qui pourrait créer un parent
intermédiaire en 0775 sous `umask 0002`.
Les tests couvrent explicitement les umask, la conservation d'un
répertoire partagé en 0775, les symlinks, les erreurs de propriété
et la vérification d'identité de l'unité systemd.
L'ancien staging sous `.local/share/nabla-compose` reste en place
s'il existe ; aucun nettoyage ou déplacement n'est effectué.

Pour reprendre sur la Workstation, sans CI ni requête de modèle :

```bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-upgrade-local-test
just openclaw-upgrade-local-plan
just openclaw-upgrade-local-stage
```

N'exécuter **l'activation** que si le stage affiche
`upgrade_stage=verified` ou `upgrade_stage=already_verified`.
Cela arrête le Gateway puis sauvegarde son état avant de remplacer le
`ExecStart` de l'unité systemd user.
Ensuite exécuter `just openclaw-upgrade-local-verify`.
Le smoke `litellm-main/gpt-4.1` a déjà réussi : ne pas le rejouer
dans sa période de cooldown 24 h.

Les nouveaux tests et le runtime n'ont pas encore été exécutés
sur la Workstation au HEAD contenant cette correction.


## 2026-10-26 — correction directe du Gateway Node (PR #285)

Rapport de l'opérateur pour \`openclaw update\` :
- \`preflight-node-runtime-incompatible\` : système
  \`/usr/bin/node\` à **24.16.0** ; OpenClaw 2026.10.7 requiert
  Node \`>=24.22.1 <25 || >=26.12.1\` ;
- unité user Gateway encore propriétaire du paquet
  \`~/.local/share/mise/installs/node/24.18.1/lib/node_modules/openclaw\` ;
- nouveau Node \`24.22.1\` installé sous mise ; shell OpenClaw
  \`2026.10.7\` installé dans un **autre préfixe** ;
- erreur de propriété SQLite sur le processus Gateway 3713 lors
  de l'exécution d'autres commandes OpenClaw ; pas une corruption
  démontrée. Ne pas supprimer la base, son WAL ni ses fichiers de lock ;
- avertissements \`pacman\` non bloquants sous Ubuntu ;
  l'inventaire de sauvegarde des plugins codex/discord/matrix/whatsapp
  est inconnu ; risque de réversibilité accepté par l'opérateur,
  qui **ne souhaite pas de sauvegarde de projet supplémentaire**.

**Décision : abandonner le staging npm pour ce correctif.** Conserver
le paquet contrôlé par le Gateway actuel, et remplacer uniquement
l'exécutable Node dans l'unité systemd. Effectuer ensuite l'update
de **ce même paquet** via son \`openclaw.mjs\` exécuté avec Node
24.22.1. La CLI du shell ne décide plus de la racine cible.

Scripts versionnés :
- \`scripts/workstation/repair-openclaw-gateway-node.py\` :
  plan et création contrôlée d'un drop-in systemd user
  \`25-nabla-node-runtime-compat.conf\`, en mode \`0600\`. Préserve
  \`--max-old-space-size=16053\`, le paquet du service, le port
  18789 et toutes les autres unités/définitions. Refuse le service
  actif, les installations inconnues, une version Node inadéquate,
  les symlinks et les chemins group-writable. Ne sauvegarde rien.
- \`scripts/workstation/recover-openclaw-managed-gateway.sh --apply\` :
  vérifie les prérequis ; stoppe proprement **l'unique** unité user
  connue ; exige l'absence d'un propriétaire observable sur le SQLite
  via \`fuser -s\` ; applique le drop-in ; exécute
  \`node@24.22.1 <ancien-openclaw.mjs> update --tag 2026.10.7
  --yes --no-restart\` ; vérifie la version ; refuse de redémarrer
  sur échec ; démarre uniquement après mise à jour réussie ;
  vérifie \`is-active\` et \`http://127.0.0.1:18789/readyz\`
  sans requête LLM.

**Commandes Workstation :**

\`\`\`bash
cd ~/w/nabla-compose
git pull --ff-only
just openclaw-gateway-node-test
just openclaw-gateway-node-plan
just openclaw-gateway-node-update
\`\`\`

La commande \`-update\` est **mutante et peut provoquer un downtime**.
Si un autre script de sauvegarde est encore actif, terminer ou arrêter
proprement ce script avant d'exécuter la reprise ; ne pas lancer deux
opérations OpenClaw simultanément. Le programme ne crée aucune
sauvegarde supplémentaire ; l'updater natif peut conserver ses propres
éléments internes de récupération, qui ne sont pas gérés ici.

**Échec** : le Gateway peut rester **arrêté** si la migration, les
plugins ou le contrôle de version échouent. Ne pas relancer
automatiquement l'ancien paquet sur un état SQLite potentiellement
migré. Investiguer \`openclaw update status --json\` sous le bon
runtime et vérifier \`systemctl --user status\` sans publier les
secrets. Pas de \`rm -rf\`, de \`sudo npm install -g\`, de
\`doctor --fix\` automatisé, ni d'opération de modèle payante.

Les tests unitaires sont synthétiques, exécutables localement sans CI.
Le nouveau parcours n'est **pas** encore validé par un update réel sur
la Workstation au HEAD de cette PR.

Documentation :
- https://docs.openclaw.ai/cli/update
- https://docs.openclaw.ai/cli/update/how-updates-run


## 2026-10-26 — PR #285 : sélectionner l'installation existante (sans npm)

**Preuve fournie par l'opérateur :** après correction du Node systemd,
\`node_runtime_switch=applied\` puis \`openclaw update\` a échoué en
\`global-install-foreign-destination\`, sans installation. Le service
systemd référence toujours
\`mise/installs/node/24.18.1/lib/node_modules/openclaw/openclaw.mjs\`,
mais Node est désormais \`mise/.../24.22.1/bin/node\`. L'updater
voit **déjà** un paquet et un launcher OpenClaw sous
\`mise/.../24.22.1\` et interdit de les écraser : ce refus est normal.
L'updater a quitté avant le redémarrage ; le Gateway est supposé arrêté
jusqu'à vérification. Un ancien smoke de \`litellm-main/gpt-4.1\`
a réussi, inutile de le répéter.

**Décision : arrêter d'invoquer \`openclaw update\` et de créer des
staging npm.** Choisir directement l'installation vérifiée
\`openclaw@2026.10.7\` du Node 24.22.1 comme propriétaire du Gateway.

La nouvelle commande \`just openclaw-gateway-select-installed\` :
1. Vérifie le manifeste \`package.json\` (nom/version/bin), l'entrée
   \`openclaw.mjs\`, le propriétaire et les permissions du paquet,
   et la CLI sous Node 24.22.1.
2. Arrête uniquement \`openclaw-gateway.service\` s'il tourne.
3. Refuse la mutation si \`openclaw.sqlite\`, \`-wal\` ou \`-shm\`
   reste détenu selon \`fuser\`.
4. Modifie atomiquement **le seul drop-in 25 déjà possédé par cette
   réparation**, en remplaçant le chemin JS 24.18.1 par 24.22.1.
   Conserve l'exécutable Node 24.22.1, le port 18789, les flags
   mémoire et les autres unités/variables.
5. Vérifie le \`systemctl --user show ... ExecStart\` après
   \`daemon-reload\`. En cas d'échec, restaure les octets de l'ancienne
   définition en mémoire ; aucun fichier de sauvegarde n'est créé.
6. Vérifie à nouveau la CLI et l'absence de propriétaire SQLite, puis
   démarre le Gateway et contrôle \`/readyz\` (loopback).

**Aucun** \`npm install\`, \`openclaw update\`, \`doctor --fix\`,
nouveau staging, backup de projet, modèle payant, rotation de clés ou
réindexation n'est réalisé. La mise en route 2026.10.7 peut appliquer
des migrations SQLite/plugins **non garanties réversibles**.
L'utilisateur accepte l'absence de nouvelle sauvegarde ; ne pas
réinstaller/revenir à 2026.9.5 automatiquement si la migration échoue.

Commandes dans un nouveau worktree de la branche PR #285 :

\`\`\`bash
just openclaw-gateway-node-test
just openclaw-gateway-node-plan
just openclaw-gateway-select-installed
\`\`\`

Le nom historique \`openclaw-gateway-node-update\` reste un alias
mais **n'exécute désormais aucune mise à jour npm**.
Le runbook antérieur relatif à l'updater a été remplacé par cette
procédure pour le conflit de préfixes.

**Critère de fin :**
\`package_selection=verified\`,
\`repair=existing_gateway_installation_healthy\`,
\`node_runtime=24.22.1\`,
\`openclaw_release=2026.10.7\`,
\`npm_install_attempted=false\`.
Puis vérifier les canaux et les index mémoire par les diagnostics
OpenClaw en lecture seule. La seule disponibilité HTTP ne prouve
pas la fonctionnalité de tous les plugins.

Tests synthétiques ajoutés et scripts inspectés dans la PR ;
**validation réelle du Gateway non encore faite par l'agent**.
