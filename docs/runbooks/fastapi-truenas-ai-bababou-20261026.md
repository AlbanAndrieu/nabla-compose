# FastAPI TrueNAS — LiteLLM, Ollama et recherche OpenRAG Bababou

**État au 26/10/2026 : code préparé, accès LAN opérateur indisponible,
aucune vérification runtime, aucune ingestion du corpus.**
Ce runbook ne donne aucune permission de déploiement automatique.

## Architecture établie par le code

| Saut | Configuration versionnée | Preuve restante |
| --- | --- | --- |
| FastAPI sample → LiteLLM TrueNAS | \`LITELLM_URL=http://172.17.0.24:4000\`, \`DEFAULT_CHAT_MODEL=fastapi-qwen\`, virtual key \`LITELLM_API_KEY\` dans \`sample/.env.secrets\` | Conteneur chargé, key scoped, modèle listé, requête chat synthétique et tool-calling |
| LiteLLM TrueNAS → proxy workstation | Modèle \`fastapi-qwen\` vers \`LITELLM_WORKSTATION_API_BASE\` avec \`LITELLM_FASTAPI_WORKSTATION_API_KEY\` | Ping/versions/allowlist des deux virtual keys ; **aucun fallback implicite vers modèle payant** |
| Ollama TrueNAS | \`apps/ollama/compose.yml\`, port \`30068\`, endpoint privé \`/api/tags\` | Liste réelle des modèles et disponibilité de la mémoire ; ne pas supposer \`qwen\` présent |
| FastAPI → OpenRAG | FastAPI dispose déjà de \`MCP_CLIENTS\` et \`mcp_call_tool\`; OpenRAG v0.7.1 expose \`/mcp\` avec \`X-API-Key\`, via \`openrag-frontend:3000\` | Clé API OpenRAG privée, route et permissions réelles, liste des outils |
| OpenRAG → Bababou | \`apps/openrag/compose.yml\` monte \`cpool/bababou\` en lecture seule dans \`/mnt/bababou\` | Jeu de documents approuvé, index isolé, filtre de connaissance enregistré, citations et ACL |

La version **v0.7.1** du projet upstream décrit le MCP intégré dans
\`sdks/mcp/README.md\` : \`openrag_search\` accepte \`filter_id\`.
Le MCP contient **aussi** \`openrag_ingest\` et \`openrag_delete_document\`.
Ne jamais proposer tous ces outils à un agent public.

## Diagnostic hors LAN immédiatement disponible

Depuis le checkout de la PR #285 :

\`\`\`bash
python3 scripts/truenas/diagnose-fastapi-ai-chain.py --check
\`\`\`

Ce contrôle ne lit que les fichiers Compose versionnés et ne contacte
aucun service. \`declared\` signifie seulement que le contrat existe.
\`bababou_private_retrieval=not_verified\` est normal.

**Quand le LAN revient**, depuis TrueNAS uniquement :

\`\`\`bash
sudo python3 scripts/truenas/diagnose-fastapi-ai-chain.py --check --runtime
\`\`\`

Le mode runtime utilise \`docker exec fastapi-sample\` et des requêtes
GET **anonymes sur des URL fixes**. Il ne lit ni tokens ni réponses, ni
noms de modèles ni documents. Un HTTP 401 prouve uniquement que le
service a répondu et exige une authentification. Il ne valide ni
les clés LiteLLM ni l'accès à OpenRAG.

## Endpoint privé de recherche (FastAPI PR #378)

Un endpoint opt-in a été ajouté dans
\`fastapi-sample\` sous
\`POST /private/ops/ai/bababou/search\` :

- L'authentification **OWNER JWT et source réseau autorisée** est
  gérée par \`nabla/route_policy.py\` / \`access_control.py\`.
- Le backend exige \`OPENRAG_BABABOU_FILTER_ID\` défini en privé.
- Un seul client \`MCP_CLIENTS\` nommé \`openrag\` est accepté,
  en transport \`streamable-http\`, avec
  \`url=http://openrag-frontend:3000/mcp\` et \`X-API-Key\`.
- Le backend appelle seulement \`openrag_search(query,limit,filter_id)\` ;
  limite \`1..5\`, taille des requêtes bornée, chemins locaux expurgés,
  réponses privées non mises en cache.
- Sans filtre ou clé, le résultat reste HTTP 503.
- L'agent générique \`/run\` ne reçoit plus automatiquement les outils
  OpenRAG dès qu'une clé MCP est configurée ; la bascule explicite
  \`OPENRAG_GENERAL_MCP_TOOLS_ENABLED=true\` **ne doit pas être définie**
  pour un corpus sensible.

### Secrets et identité

Le client OpenRAG nécessite une clé API propre à l'usage privé ; ne
pas utiliser une clé d'administration globale ou la clé LiteLLM.
**Aucune clé OpenRAG n'a été générée ou provisionnée dans cette PR.**
Le fichier privé FastAPI \`sample/.env.secrets\` doit éventuellement
contenir \`MCP_CLIENTS\` (tableau JSON, clé X-API-Key masquée), et
\`OPENRAG_BABABOU_FILTER_ID\` récupéré depuis OpenRAG **après** création
d'un filtre limitant exactement le corpus autorisé.

Ne pas committer un exemple avec un jeton actif, ni transmettre le
fichier complet dans des logs, ni afficher \`docker inspect .Config.Env\`.
Conserver \`OPS_ROUTE_POLICY_STRICT\` et l'autorisation OWNER.
Un HTTP 200 sur \`/mcp\` ne prouve **pas** que la recherche est autorisée
pour le filtre.

### Gates d'acceptation, à faire quand le LAN revient

1. Vérifier que FastAPI a bien chargé \`LITELLM_URL\`, le nom de modèle
   et **la présence**, sans la valeur, de sa clé dédiée.
2. Confirmer la route \`fastapi-qwen\` et le retour d'une complétion
   synthétique + fonction/tool-calling avec le jeton scoped, sans
   envoyer de document Bababou.
3. Tester \`Ollama /api/tags\` et identifier les modèles réellement
   chargés ; décider ensuite si un alias LiteLLM local séparé est utile.
4. Confirmer OpenRAG backend/Docling/Langflow/OpenSearch et les
   fonctions \`tools/list\` MCP après authentification.
5. Créer ou identifier le filtre de connaissance **exact** du
   corpus autorisé ; vérifier qu'une recherche hors corpus retourne zéro
   document. Conserver une preuve de l'identité et des ACL du filtre.
6. Tester en OWNER uniquement la recherche d'un **document synthétique**
   avec citation et page ; vérifier que la requête anonyme et la
   tentative avec mauvais filtre sont refusées.
7. N'indexer un petit sous-ensemble des vrais documents privés
   qu'après approbation explicite de la liste, revue des logs LiteLLM,
   Langfuse, OpenRAG et validation de la suppression du test.

Ne pas redéployer, indexer, exposer un nouveau port, créer un tunnel
Cloudflare, transmettre de PII hors du LAN ni modifier des secrets
tant que les gates d'autorisation ne sont pas vérifiées.
