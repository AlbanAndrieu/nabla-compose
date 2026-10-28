# FastAPI TrueNAS — déploiement et acceptation IA (27/10/2026)

## Preuves et limites

L'ancien build du SHA FastAPI `0266f20d7ff1278bf7dd36ac15a22618d04b3742` a échoué sur Docker Hub HTTP 429. L'opérateur a ensuite confirmé `sudo docker login` réussi, `/root/.docker/config.json` root:root 0600 et le pull réussi de `python:3.13-slim-trixie` (digest `sha256:b3575dcf816cdacc5292df77a6e3e59b8941631078373a045efa2ac1e9c5c3b2`). Les 35 tests du garde-fou ont été validés précédemment ; les **11 tests d'acceptation IA sont désormais PASS** d'après la dernière recette opérateur. Les nouveaux tests d'alignement des secrets dans cette PR n'ont pas encore été exécutés sur TrueNAS.

Pas d'accès d'exécution SSH/TrueNAS depuis la PR GitHub. Le déploiement doit être lancé par l'opérateur dans le checkout canonique ; **ne pas déployer depuis un worktree temporaire**, car l'outil TrueNAS attache le chemin absolu du fichier Compose.

## Retour TrueNAS : FastAPI 1.25.0 en service — seule l'authentification IA reste bloquée

**Preuve opérateur :** build terminé ; réseau observateur v2 et allowlist OK ; `app.update` et `app.redeploy` réussis ; `fastapi-sample` running, HTTP `/health=200`, santé applicative **4/4**, version **1.25.0** ; digest de l'image exécutée identique à celui de l'image sélectionnée. `build_revision=null` : **l'empreinte Git de l'image n'est pas attestée**, malgré le checkout de `0266f20d7ff1278bf7dd36ac15a22618d04b3742` au build. Le gitlink parent reste sur `441d0a7e` : ne pas faire de `git reset --hard` du sous-module et ne pas enregistrer automatiquement ce changement.

Les intégrations sont indépendantes :

| Intégration | Observation depuis FastAPI | Conclusion |
| --- | --- | --- |
| Prometheus/Gatus | `gatus_up=1`, 85 échantillons synthétiques | Contrat observateur accessible, **pas** 85 succès de sondes |
| pfSense RBAC | 7/7 | Contrôle privilégié OK |
| Ollama TrueNAS | HTTP 200 | API joignable ; génération non testée |
| OpenRAG backend/frontend | HTTP 200 / 200 | API joignables ; recherche/ACL non testées |
| OpenRAG MCP | HTTP 406 | Endpoint joignable ; négociation de contenu et autorisation MCP non validées |
| LiteLLM TrueNAS | **HTTP 401** via la clé FastAPI `LITELLM_API_KEY` | Accès au modèle `fastapi-qwen` non authentifié ; aucune inférence |

**Ne redéployer ni FastAPI ni les autres services à ce stade.** Le déploiement FastAPI lui-même est achevé. L'investigation P0 se limite à LiteLLM et aux clés virtuelles. Ne pas confondre un 401 avec une panne réseau : une réponse HTTP 401 provient d'un serveur qui a répondu.

### Diagnostic LiteLLM ciblé — aucune donnée secrète affichée

Le proxy est déclaré sur `http://172.17.0.24:4000` et le modèle attendu est `fastapi-qwen`. La version du diagnostic sur la PR #289 distingue maintenant `litellm_proxy_liveness` (un GET public de santé) et `litellm_key_format` (simple classe `sk_prefix`/`unexpected_format`/`missing`), sans afficher la clé ni son hash. Les tests initiaux du script IA avaient 9 méthodes, **4 FAIL et 1 ERROR**, dus à un type JSON non validé et une assertion trop large du mot `secret`. Correctifs publiés en `[skip ci]` ; nouveaux tests incluant le 401 et liveness **encore à exécuter en local**.

~~~bash
cd /mnt/cpool/compose/nabla-compose
git fetch origin fix/nexus-wan-haproxy-acl-evidence-20261027
git merge --ff-only origin/fix/nexus-wan-haproxy-acl-evidence-20261027
python3 -m unittest discover -s tests -p 'test_fastapi_ai_connectivity_acceptance.py' -v
sudo python3 scripts/truenas/accept-fastapi-ai-connectivity.py --check
~~~

La sortie doit rester du JSON à valeurs bornées, sans `LITELLM_API_KEY` et sans sortie de logs. `litellm=http_401` avec `litellm_proxy_liveness=http_200` et `litellm_key_format=sk_prefix` signifie que la requête authentifiée a été rejetée malgré un proxy vivant et une clé de forme attendue ; **cela n'établit pas si la clé est révoquée, expirée, inconnue en base, bloquée par budget ou refusée pour une autre raison**.

### Preuve du 27/10/2026 : deux secrets distincts à corriger

La dernière recette de l'opérateur confirme **11/11 tests PASS** (contrats FastAPI IA). L'audit `--check` indique :
- FastAPI → LiteLLM TrueNAS : `litellm_proxy_liveness=http_200`, `litellm_key=present`, `litellm_key_format=sk_prefix`, mais `/v1/models=http_401`. **Ce 401 concerne la clé consommateur FastAPI** ; l'URL et le proxy sont joignables, mais l'authentification/autorisation n'est pas prouvée.
- LiteLLM TrueNAS → workstation : `truenas_verified`, conteneur exact `litellm` running, `LITELLM_FASTAPI_WORKSTATION_API_KEY=absent`, `LITELLM_IDE_API_KEY=present`, workstation liveliness `http_200`. **Le relais dédié est impossible avec la configuration actuelle** ; il ne faut pas substituer la clé IDE.

Deux nouvelles sondes *strictement lecture seule* sont livrées dans #289 :
- `check-fastapi-litellm-runtime-keys.py` : exécuté avec `sudo`, inspecte les permissions root:root/0600 et la présence des deux champs dans les fichiers canoniques, puis compare **en mémoire uniquement** leur valeur aux variables configurées dans les deux conteneurs. Aucune valeur, taille, empreinte, réponse Docker brute ou variable d'environnement n'est publiée. Ses codes `file_key_absent`, `container_key_absent`, `different`, `match` distinguent la matérialisation du runtime. **`match` ne prouve PAS l'enregistrement de la clé en LiteLLM.** Les fichiers secrets multi-lignes / interpolés restent `not_comparable`, sans supposer un échec.
- `check-fastapi-litellm-sample-source.py` : exécuté **sans sudo** avec un `BW_SESSION` déverrouillé, cherche uniquement l'item Vaultwarden `nabla/prod/sample-litellm`, champ masqué `LITELLM_API_KEY`, sans imprimer la valeur. La vérification upstream existe déjà pour `nabla/prod/litellm`, champ `LITELLM_FASTAPI_WORKSTATION_API_KEY`.

~~~bash
cd /mnt/cpool/compose/nabla-compose
git fetch origin fix/nexus-wan-haproxy-acl-evidence-20261027
git merge --ff-only origin/fix/nexus-wan-haproxy-acl-evidence-20261027

python3 -m unittest discover -s tests -p 'test_fastapi_litellm_*py' -v
sudo python3 scripts/truenas/check-fastapi-litellm-runtime-keys.py --check

# À lancer uniquement avec une session Vaultwarden déjà déverrouillée,
# dans la session de l'opérateur non root.
just litellm-fastapi-sample-source-check
just litellm-fastapi-upstream-source-check
~~~

**Interprétation :**
- `file_key_absent` et `container_key_absent` pour la clé upstream : elle n'est pas dans le fichier canonique ni dans le conteneur ; rechercher d'abord la source Vaultwarden ou le provisionnement manquant.
- `file_key_present` mais `container_key_absent` ou `different` : le secret fichier et le runtime sont désynchronisés. Une mise à jour du conteneur **LiteLLM uniquement** peut devenir nécessaire après validation du fichier et des dépendances, mais pas pendant ce diagnostic.
- `LITELLM_API_KEY:match` pour FastAPI avec `/v1/models=401` : la valeur runtime correspond au fichier, mais la clé reste refusée par LiteLLM. Vérifier alias `fastapi-sample-staging`, expiration, revocation, modèle autorisé et budget dans la **base active** du proxy TrueNAS.
- `field_present_nonempty_hidden` côté Vaultwarden : le champ source existe, sans preuve que le proxy l'accepte ; `field_absent` ou `field_empty` identifie la source manquante.

**Attention :** `sample-litellm` est un item **séparé** dans le manifeste, tandis que FastAPI consomme `/mnt/cpool/secrets/runtime/sample/.env.secrets` contenant aussi d'autres credentials. Ne pas exécuter aveuglément `materialize_runtime.py --app sample-litellm --install` en pensant fusionner le champ dans le fichier de Sample : le matérialiseur écrit dans `/mnt/cpool/secrets/runtime/sample-litellm/.env.secrets`, **pas** dans le fichier consommé par FastAPI. Ne jamais écraser le fichier Sample entier avec ce seul champ. Planifier une fusion minimale et vérifiée seulement après contrôle de la source.

Aucune rotation, génération de clé, actualisation de conteneur, appel de modèle, copie de secret ou action Bitwarden mutante n'est lancée par ces sondes. Les **nouveaux tests de contrat** restent à exécuter sur TrueNAS.

### Vérifier l'enregistrement de la clé virtuelle, puis l'upstream

1. Dans l'administration de **LiteLLM TrueNAS**, rechercher la clé virtuelle dédiée `fastapi-sample-staging` (ou l'alias effectivement provisionné), en **lecture seule**. Vérifier : état actif/expiration, autorisation **uniquement** `fastapi-qwen`, `max_budget=8` **USD à vie** (`budget_duration=null`), RPM 5, TPM 15000, `max_parallel_requests=1`. L'alias de modèle dans `config.yaml` ne prouve pas la clé en base.
2. Vérifier dans Vaultwarden l'item `nabla/prod/sample-litellm`, champ masqué `LITELLM_API_KEY`, et son import dans **le fichier canonique Sample existant** `/mnt/cpool/secrets/runtime/sample/.env.secrets`, sans imprimer les valeurs. Vérifier les permissions du fichier et son état de matérialisation ; une clé présente en mémoire ne garantit pas qu'elle correspond à celle en base.
3. Ensuite seulement, vérifier la chaîne d'upstream **LiteLLM TrueNAS → LiteLLM workstation** via le diagnostic déjà présent :

   ~~~bash
   sudo python3 scripts/truenas/diagnose-workstation-litellm-upstream-auth.py --check
   ~~~

   Le runbook `docs/runbooks/fastapi-sample-litellm.md` documente une preuve antérieure de `LITELLM_FASTAPI_WORKSTATION_API_KEY=absent` dans le conteneur LiteLLM TrueNAS : **reconfirmer** ce fait. L'absence empêcherait le relais vers `qwen`, même après résolution du 401 FastAPI. Si le secret est absent, investiguer d'abord sa source Vaultwarden avec `just litellm-fastapi-upstream-source-check` dans une session non-root déverrouillée. Aucun secret ne doit être ajouté à la main ou remplacé par une clé IDE/master.

4. Si l'alias ou la clé applicative n'existe pas, **ne pas générer automatiquement une seconde clé**. Inspecter les clés orphelines et les éventuelles entrées de la base, puis suivre le provisionneur `scripts/workstation/provision-fastapi-litellm-keys.py` avec un plan contrôlé, stockage Vaultwarden et budget vérifié. N'utiliser `--apply` qu'après attestation de l'identité et des droits d'administration, sans loguer la clé.

La documentation LiteLLM décrit `GET /key/info` comme un endpoint administratif qui requiert une clé master, et signale que l'authentification des clés dépend de la base PostgreSQL. Ne pas placer une clé dans un paramètre d'URL ou dans l'historique shell et ne jamais utiliser la clé master comme clé applicative FastAPI.

Sources : https://docs.litellm.ai/docs/proxy/virtual_keys et https://docs.litellm.ai/docs/proxy/prod .

## Préflight lecture seule

```bash
cd /mnt/cpool/compose/nabla-compose
git status --short
sudo docker network inspect intranet traefik_network >/dev/null && echo 'shared_networks=ok'
sudo docker ps -a --filter 'name=^/fastapi-sample$' --format 'name={{.Names}} state={{.State}}'
sudo midclt call app.query '[["id","=","sample"]]' | jq -c '[.[]|{id,state}]'
sudo docker image inspect python:3.13-slim-trixie --format 'python_base_cached=yes'
```

Après `docker system prune`, ne pas présumer la présence d'anciens conteneurs arrêtés et réseaux. **Ne pas recréer** `intranet` ou `traefik_network` avec une plage d'adresses arbitraire ; ne pas lancer `docker system prune` ou `compose down`.

## Tests sans CI et sans LLM

```bash
git fetch origin fix/nexus-wan-haproxy-acl-evidence-20261027
WT="$(mktemp -d /tmp/nabla-fastapi-ai-check.XXXXXX)"
rmdir "$WT"
git -c submodule.recurse=false worktree add --detach "$WT" origin/fix/nexus-wan-haproxy-acl-evidence-20261027
test_status=0
(
  set -e
  cd "$WT"
  bash -n scripts/truenas/update-fastapi-sample.sh
  python3 -m py_compile scripts/truenas/accept-fastapi-ai-connectivity.py
  python3 -m unittest discover -s tests -p 'test_fastapi_build_failure_*py' -q
  python3 -m unittest discover -s tests -p 'test_fastapi_ai_connectivity_acceptance.py' -q
) || test_status=$?
git worktree remove "$WT"
test "$test_status" -eq 0
```

## Recette historique de l'upgrade (déjà exécutée : NE PAS relancer)

**Archive de procédure seulement.** L'upgrade du SHA ci-dessous est déjà terminé 6/6. Garder ces commandes pour une future intervention contrôlée, pas pour corriger le seul HTTP 401 LiteLLM. Aucun rebuild ni redéploiement de FastAPI ou de LiteLLM n'est requis pour les diagnostics lecture seule.

Pour un déploiement futur uniquement, vérifier le statut Git et les réseaux avant de synchroniser la branche Compose :

```bash
cd /mnt/cpool/compose/nabla-compose
git fetch origin fix/nexus-wan-haproxy-acl-evidence-20261027
git switch fix/nexus-wan-haproxy-acl-evidence-20261027
git merge --ff-only origin/fix/nexus-wan-haproxy-acl-evidence-20261027

FASTAPI_SAMPLE_REF=0266f20d7ff1278bf7dd36ac15a22618d04b3742 \
FASTAPI_SAMPLE_DEPLOY_MODE=build \
FASTAPI_SAMPLE_REFRESH_BASE_IMAGES=false \
  bash scripts/truenas/update-fastapi-sample.sh
```

Le script construit l'image avant de remplacer le conteneur `sample` et vérifie la santé, la version et le digest local. L'échec du build est traité sans divulguer le journal. Les étapes 4–6 peuvent modifier le conteneur et les réseaux de Sample ; un échec après remplacement n'est pas un rollback garanti.

## LiteLLM, Ollama et OpenRAG — vérification après déploiement

```bash
sudo python3 scripts/truenas/accept-fastapi-ai-connectivity.py --check
```

La sonde, exécutée **dans le conteneur FastAPI**, effectue uniquement des GET sans prompts ni données privées. Elle retourne des codes fixes, pas de clés, d'URL secrète ou de réponses de modèle.

- **LiteLLM** : `litellm=http_200` et `litellm_model=visible` attestent que la clé applicative `LITELLM_API_KEY` peut consulter `fastapi-qwen` sur `http://172.17.0.24:4000/v1/models`. Cela ne valide pas encore le budget ou la complétion. Une déclaration `fastapi-qwen` existe dans la configuration Git, pas nécessairement dans le routeur actif.
- **Ollama TrueNAS** : `ollama=http_200` et `ollama_models_available=true` depuis `:30068/api/tags` attestent une API et au moins un modèle listé ; aucune génération n'est testée.
- **OpenRAG** : `openrag_backend=http_200` et `openrag_frontend=http_200` attestent uniquement les endpoints HTTP. `openrag_mcp` est une preuve de transport non authentifiée ; `404/405/401` n'est pas une session MCP réussie. **L'intégration MCP FastAPI → OpenRAG reste `not_wired_pending_private_acl`**, et la recherche Bababou n'est pas testée.

Le chemin d'inférence prévu est FastAPI → LiteLLM TrueNAS (`fastapi-qwen`) → LiteLLM workstation (`qwen`). Deux clés virtuelles distinctes et restreintes sont nécessaires ; voir `docs/runbooks/fastapi-sample-litellm.md`. Une requête de confirmation explicite, synthétique et plafonnée à quatre tokens est disponible **après la vérification du modèle** :

```bash
sudo python3 scripts/truenas/accept-fastapi-ai-connectivity.py --check --inference-smoke
```

Cette option consomme potentiellement des tokens. Aucun prompt privé, document RAG ou secret n'est envoyé. **Ne pas activer automatiquement** `--inference-smoke` dans l'upgrade.

## Validation de l'UI après le déploiement réel

Depuis la racine **fastapi-sample**, et pas `nabla-compose` :

```bash
cd /mnt/cpool/compose/nabla-compose/fastapi-sample
node scripts/diagnose-production-api-ui-freeze.mjs truenas
node scripts/diagnose-production-api-ui-freeze.mjs truenas --safe
```

Ne pas confondre HTTP 200 avec un navigateur interactif. Ne pas conclure qu'OpenRAG est intégré avant les ACL/MCP, les droits d'accès et les tests de recherche approuvés.


## Correction du placement des clés — retour opérateur du 28 octobre

L'opérateur indique avoir ajouté `LITELLM_FASTAPI_WORKSTATION_API_KEY` à
`/mnt/cpool/secrets/runtime/sample/.env.secrets`. **Ce n'est pas le bon
consommateur**. Le proxy LiteLLM TrueNAS lit exclusivement
`/mnt/cpool/secrets/runtime/litellm/.env.secrets` pour cette clé upstream,
tandis que Sample doit seulement posséder sa propre `LITELLM_API_KEY`.
Le fait d'avoir ajouté la clé dans le fichier Sample ne démontre aucune
injection dans le conteneur LiteLLM ; l'audit antérieur a confirmé
`container_key_absent` et `file_key_absent` côté LiteLLM.

Ordre de résolution sécurisé : vérification source Vaultwarden exacte
`nabla/prod/litellm` ; validation des secrets fichier sans impression ;
injection ciblée de la clé dans le fichier LiteLLM canonique après revue ;
suppression du champ upstream inutile de Sample **sans effacer les autres
valeurs**, et changement du conteneur LiteLLM seulement après
preuve de source, identité et plan de rollback. Une correction du fichier
n'actualise pas l'environnement d'un conteneur existant.

**OPENAI_API_KEY n'est pas nécessaire pour la liaison
FastAPI → LiteLLM TrueNAS → LiteLLM workstation.** Le code
`nabla/deepagents/llm_factory.py` privilégie `LITELLM_URL` avec
`LITELLM_API_KEY` ; il ne lit le token OpenAI direct qu'en l'absence de
route LiteLLM et Azure. Ne pas inventer `OPENAI_API_KEY=XXX` ou placer
une clé OpenAI réelle dans le fichier Sample pour réparer le 401.
Si le besoin futur est un fournisseur OpenAI payant, provisionner
explicitement une clé **projet dédiée** via OpenAI Platform avec contrôle
de budget et stockage Vaultwarden. Les clés des fournisseurs OpenAI
utilisées par le proxy LiteLLM sont gérées dans l'item
`nabla/prod/litellm`, pas dans la collection Sample.

**UI:** en parallèle, la PR FastAPI #381 a 7/7 tests Node PASS
et le préflight indique `playwright_python_missing` sans requêtes
réseau. Ne pas confondre le problème du lanceur Chromium avec le HTTP 401
LiteLLM ou avec la lenteur du catalogue `/api/ui/services`.
