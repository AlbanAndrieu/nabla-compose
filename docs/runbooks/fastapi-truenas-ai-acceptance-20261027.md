# FastAPI TrueNAS — déploiement et acceptation IA (27/10/2026)

## Preuves et limites

L'ancien build du SHA FastAPI `0266f20d7ff1278bf7dd36ac15a22618d04b3742` a échoué sur Docker Hub HTTP 429. L'opérateur a ensuite confirmé `sudo docker login` réussi, `/root/.docker/config.json` root:root 0600 et le pull réussi de `python:3.13-slim-trixie` (digest `sha256:b3575dcf816cdacc5292df77a6e3e59b8941631078373a045efa2ac1e9c5c3b2`). Les 35 tests du garde-fou sont PASS pour le SHA Compose précédemment testé, mais **les nouveaux tests IA de cette branche restent à exécuter**.

Pas d'accès d'exécution SSH/TrueNAS depuis la PR GitHub. Le déploiement doit être lancé par l'opérateur dans le checkout canonique ; **ne pas déployer depuis un worktree temporaire**, car l'outil TrueNAS attache le chemin absolu du fichier Compose.

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
