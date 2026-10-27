# FastAPI TrueNAS — déploiement et acceptation IA (27/10/2026)

## Preuves et limites

L'ancien build du SHA FastAPI `0266f20d7ff1278bf7dd36ac15a22618d04b3742` a échoué sur Docker Hub HTTP 429. L'opérateur a ensuite confirmé `sudo docker login` réussi, `/root/.docker/config.json` root:root 0600 et le pull réussi de `python:3.13-slim-trixie` (digest `sha256:b3575dcf816cdacc5292df77a6e3e59b8941631078373a045efa2ac1e9c5c3b2`). Les 35 tests du garde-fou sont PASS pour le SHA Compose précédemment testé, mais **les nouveaux tests IA de cette branche restent à exécuter**.

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

## Redéployer un seul SHA FastAPI — uniquement depuis le checkout canonique

Après validation du statut Git et des réseaux, mettre à jour la branche Compose (ne pas écraser les changements locaux), puis :

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
