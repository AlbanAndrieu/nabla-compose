# Diagnostic OpenRAG — ingestion du dataset Bababou / Bababou (TrueNAS)

**Statut : procédure de diagnostic, non exécutée sur TrueNAS.**  
**Périmètre :** OpenRAG 0.7.1, Docling partagé, Langflow global, OpenSearch, LiteLLM et source ZFS `cpool`.  
**PR de suivi :** #259. Ne pas fusionner sur la seule base de cette procédure.

## Architecture et décisions

| Composant | Source déclarative | Rôle |
| --- | --- | --- |
| Docling Serve CPU | `apps/docling/compose.yml` | **Service commun unique** `http://docling:5001` (LAN `172.17.0.24:5001`, `/ready`) ; ne pas créer de seconde instance |
| OpenRAG | `apps/openrag/compose.yml` | Backend `0.7.1` : Docling commun, OpenSearch, Langflow global, LiteLLM workstation `172.17.0.57:4000/v1` |
| Langflow | `apps/langflow/compose.yml` | Service global `langflow:7860` ; pas de Langflow dédié à OpenRAG |
| Open WebUI | `apps/openwebui/compose.yml` | Chat et Knowledge via LiteLLM TrueNAS `172.17.0.24:4000/v1` |
| LiteLLM TrueNAS | `apps/litellm/config.yaml` | Alias `embedding` (vers la workstation), `embedding-local` en repli explicite, `workstation-qwen` |

```text
Open WebUI (chat, Knowledge, ACL par utilisateur)
     |              \
     | LiteLLM       \ MCP (si présent dans la version déployée) / OpenAPI
     v                v
LiteLLM TrueNAS    Adaptateur RAG restreint (recherche/lecture seulement)
     |                |
     v                v
LiteLLM workstation <-- OpenRAG backend --> Langflow global
                          |        |
                       Docling   OpenSearch
                          ^
                          |
                   Open WebUI extraction
```

- LiteLLM est la **passerelle modèle** (chat/embeddings), pas
  l'orchestrateur de retrieval. OpenRAG exécute retrieval/indexation,
  Docling parse, OpenSearch indexe. Interdire toute bascule silencieuse
  entre embeddings de dimensions différentes.
- Un seul Docling, mais **deux jeux d'index et deux politiques
  d'autorisation** (Open WebUI Knowledge et OpenRAG) : ne pas mutualiser
  les collections par simple pointage d'URL. Côté Open WebUI, l'extraction
  Docling (`CONTENT_EXTRACTION_ENGINE=docling`,
  `DOCLING_SERVER_URL=http://docling:5001`) exige l'accès réseau
  `intranet` ; avec `ENABLE_PERSISTENT_CONFIG=false`, vérifier le moteur
  effectif dans l'admin plutôt que les variables.
- Exposition de la recherche : **option A** (Open WebUI) MCP Streamable
  HTTP privé, authentifié côté serveur, allowlist d'outils *search/read*
  seulement ; **option B** (`fastapi-sample`) adaptateur interne minimal
  `search(query, corpus_id, top_k)` avec résultats structurés
  (`document_id`, `source_path_redacted`, `page`, `snippet`, `score`,
  `citation`). Jamais l'API admin, ni accès direct à OpenSearch,
  Langflow, Docling ou au volume source.
- Hors LAN, uniquement un endpoint dédié derrière Cloudflare Access
  service-token (ou équivalent), après revue d'authentification,
  limitation de débit, isolation de corpus et filtrage des réponses.
- Comparaison Open WebUI Knowledge / OpenRAG : mêmes documents,
  embeddings, modèle et 20–30 questions annotées ; mesurer recall@5,
  MRR@10, fidélité, citations avec page, latence p95, durée
  d'indexation et RAM/CPU/GPU, sans extraits privés dans le tableau.

**Gates :** P0 Docling commun réellement disponible et clients
vérifiés ; P1 versions OpenRAG/MCP/Open WebUI testées avant tout
connecteur ; P2 autorisation explicite du sous-ensemble Bababou, logs
privés, ACL et index séparés ; P3 connexion externe `fastapi-sample`
seulement après preuve de l'authentification, des permissions et d'une
observabilité minimisée.

## 0. Constat vérifiable dans Git

- `apps/openrag/compose.yml` déclare `openrag-backend` et `openrag-frontend`, les documents applicatifs sous `./openrag-documents:/app/openrag-documents`, et les volumes `./data`, `./config`, `./keys` ainsi que `./flows/backup`.
- Le backend utilise `http://docling:5001`, `http://langflow:7860`, `opensearch:9200` et LiteLLM `http://172.17.0.57:4000/v1` par défaut. Ces variables n'attestent **ni** la disponibilité des services **ni** une ingestion réussie.
- Dataset **confirmé par le propriétaire** : `cpool/bababou`, propriétaire `albandrieu:albandrieu`. Son mountpoint ZFS réel et ses ACL effectives restent à vérifier ; `cpool/bababou` n'implique pas nécessairement `/mnt/cpool/bababou`.
- Le Compose monte désormais `${OPENRAG_BABABOU_SOURCE:-/mnt/cpool/bababou}` vers `/mnt/bababou` **en lecture seule**, avec `create_host_path: false`. Cette valeur par défaut doit être comparée au mountpoint ZFS avant déploiement, sinon définir `OPENRAG_BABABOU_SOURCE` dans la configuration Compose non sensible. Le montage de `./openrag-documents` reste inchangé.
- L'accès au dataset par le processus OpenRAG dépend des permissions de traversée et lecture du propriétaire/groupe, des ACL ZFS et de l'UID/GID runtime. Ne pas lancer de `chown -R`, de `chmod -R` ni appliquer `:U` ou `:z` à la source privée. Préférer des ACL de lecture et traversée minimales attribuées à l'identité effective du service.

## 1. Diagnostic source (lecture seule, zéro contenu de document)

Sur TrueNAS, exécuter uniquement après accès autorisé. Ne jamais lancer `find /mnt/cpool` récursivement :

```bash
# Inventaire borné aux métadonnées ZFS.
zfs list -H -o name,mountpoint,canmount,mounted -r cpool |
  grep -Ei '(^|/)(babou|bababou)(/|[[:space:]]|$)' || true

# Fixer SOURCE exclusivement d'après le mountpoint ZFS constaté.
# SOURCE=/mnt/cpool/CHEMIN_REEL
test -n "${SOURCE:-}" && test -d "$SOURCE" || {
  echo "BLOCKED: SOURCE non confirmé"; exit 2;
}
realpath -e -- "$SOURCE"
stat -c 'type=%F uid=%u gid=%g mode=%a mount=%m' -- "$SOURCE"
findmnt -T "$SOURCE" -o TARGET,SOURCE,FSTYPE,OPTIONS
# Métadonnées agrégées, sans noms ni extraits de fichiers.
find "$SOURCE" -xdev -maxdepth 5 -type f -printf '%s\n' |
  awk '{n++;bytes+=$1} END {printf "files=%d bytes=%.0f\n",n,bytes}'
find "$SOURCE" -xdev -maxdepth 5 -type l | wc -l
```

**À confirmer :** dataset et mountpoint canoniques, propriétaire/ACL, accès effectif du UID/GID du conteneur, présence de fichiers accessibles, symlinks, profondeur réelle et fichiers Google natifs non exportés. Le comptage `maxdepth 5` est indicatif et peut sous-estimer les fichiers ; aucune conclusion d'exhaustivité. Vérifier la fraîcheur de l'export Drive sans imprimer de noms privés. Ne pas parcourir les symlinks ni élargir la profondeur par défaut.

## 2. Diagnostic de la chaîne d'ingestion (sans écrire)

| Porte | Contrôle | Critère PASS | Diagnostic en cas d'échec |
| --- | --- | --- | --- |
| D0 — Source | Dataset ZFS, mountpoint réel, ACL et lecture par identité non privilégiée | Source identifiée et lisible sans privilège root | `SOURCE_UNKNOWN`, `ACL_DENIED`, `EMPTY_OR_UNVERIFIED` |
| D1 — Montage | `docker inspect openrag-backend` : mounts et RW ; distinguer volume applicatif et corpus source | Source approuvée exposée **RO** seulement, sans surmonter `/app` | `SOURCE_NOT_MOUNTED`, `SOURCE_WRITABLE` |
| D2 — Backend | `docker inspect` : état, health, réseau ; `/health` | Backend sain et joignable | `BACKEND_UNHEALTHY` |
| D3 — Docling | Résolution `docling`, HTTP `/ready`, conversion **fichier synthétique** | Conversion réussie avec métadonnées et sans fuite | `DOCLING_UNAVAILABLE`, `PARSER_FAILED` |
| D4 — Langflow | `langflow:7860/health_check` depuis le réseau applicatif | Santé et flux/version compatibles | `LANGFLOW_UNAVAILABLE`, `FLOW_MISMATCH` |
| D5 — OpenSearch | Reachability, auth et index/alias autorisés (sans afficher les documents) | Index dédié identifié ; autorisations contrôlées | `SEARCH_UNAVAILABLE`, `INDEX_MISSING`, `INDEX_ACL` |
| D6 — LiteLLM | Endpoint, alias `embedding`, identité et dimensions des vecteurs, budget | Modèle stable, autorisé et compatible avec l'index | `EMBEDDING_AUTH`, `DIMENSION_MISMATCH`, `RATE_LIMIT` |
| D7 — Pipeline | Ingestion d'un **fichier synthétique** puis recherche/citation | Extraction → chunks → embeddings → index → retrieval confirmés | `INGESTION_FAILED`, `RETRIEVAL_EMPTY` |
| D8 — Babou POC | 10–20 fichiers **explicitement approuvés**, corpus `bababou-poc` isolé | Comptages, progression, citations, ACL et purge démontrés | `APPROVAL_MISSING`, `PARTIAL_INGESTION`, `LEAKAGE_RISK` |

Les chemins REST d'ingestion et l'API MCP **doivent être découverts dans la version OpenRAG effectivement déployée** ; ne pas supposer que `/mcp`, `/ingest` ou `/documents` existent.

## 3. Contrôles d'infrastructure ciblés

```bash
# Lecture seule ; adapter les noms après inspection de la réalité TrueNAS.
docker inspect openrag-backend --format '{{json .State.Health}}'
docker inspect openrag-backend --format '{{range .Mounts}}{{println .Destination .RW}}{{end}}'
docker inspect openrag-backend --format '{{.State.Status}}'
# Ne pas publier l'environnement complet de docker inspect (secrets possibles).
curl --fail --silent --show-error --max-time 8 http://172.17.0.24:5001/ready
# Les URL internes ne sont à tester que depuis un conteneur déjà
# connecté à intranet avec un client HTTP disponible, sans privilèges nouveaux.
```

Pour isoler une panne, mesurer successivement : (a) visibilité du dossier dans le conteneur ; (b) parsing/OCR d'un document de test ; (c) disponibilité du flux Langflow ; (d) appel embeddings ; (e) création de chunks/index dans un corpus de test ; (f) recherche par terme attendu. Ne jamais considérer `/health` comme preuve d'ingestion.

**Observabilité privée :** collecter uniquement horodatage, étape, statut HTTP, code d'erreur, nombre de fichiers examinés/admis/rejetés, tailles agrégées, chunks, dimensions, latence, identifiant opaque de job et cardinalité index. Ne pas copier les noms de pièces, chemins complets, OCR, chunks, prompts, clés ou documents dans les issues, traces Langfuse, GitHub Actions ni journaux partagés.

### Docling : readiness, conteneur unhealthy et port 5001

```bash
sudo python3 scripts/truenas/diagnose-docling-readiness.py --check
sudo docker inspect --type container docling --format \
  'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}unavailable{{end}} restarts={{.RestartCount}}'
sudo midclt call app.query '[["id","=","docling"]]' |
  jq '[.[] | {id, state, active_workloads}]'
# Le serveur écoute-t-il dans le conteneur ? (0 = oui)
sudo docker exec docling python -c \
  'import socket; s=socket.socket(); s.settimeout(2); print("loopback_5001="+str(s.connect_ex(("127.0.0.1",5001)))); s.close()'
```

Le diagnostic distingue l'App TrueNAS, le conteneur, la readiness hôte
`172.17.0.24:5001/ready` et la readiness `openrag-backend -> docling:5001`,
sans lire de fichier privé. Il renvoie `INITIALIZING` quand l'App est
`DEPLOYING` avec un conteneur `running`. Docling Serve distingue
`GET /health` (liveness) et `GET /ready` (readiness, 503 pendant le
chargement des modèles) : seules les sondes `/ready` établissent la
disponibilité de l'API.

- `health=unhealthy` avec `connection refused` sur `:5001` n'est pas un
  modèle en cours de chargement : aucun serveur HTTP n'écoute. Avec
  `loopback_5001` non nul, lire **en session privée** quelques lignes
  récentes des logs (échec Python, limite mémoire, image), sans partager
  le log brut. Ne pas allonger `start_period: 120s` ni masquer
  l'`unhealthy` avant d'avoir compris le démarrage.
- **Ne pas relancer `app.update`, `app.redeploy` ou
  `deploy-docling.sh --apply` tant que TrueNAS signale `DEPLOYING`** :
  le script de déploiement refuse déjà de muter une App `DEPLOYING`.

Pour un PDF privé, `check-openrag-private-pdf.sh` confirme un vrai PDF
sur l'hôte, sa visibilité en lecture seule dans `openrag-backend` via
`/mnt/bababou`, la readiness Docling (hôte et réseau OpenRAG) et
`/search/health`, sans extraire, téléverser, indexer ni rechercher son
contenu. Les PDF du corpus restent privés (codes QR, numéros de
réservation) : ne jamais les copier vers un fournisseur externe ni
publier leur nom.

```bash
sudo bash scripts/truenas/check-openrag-private-pdf.sh --check \
  --file '<fichier.pdf>'
```

## 4. Hypothèses prioritaires et triage

1. **Absence de montage du dataset** : le chemin applicatif `./openrag-documents` n'est pas le dataset ZFS ; inspecter les mounts effectifs avant tout changement.
2. **Pipeline extraction bloqué** : Docling déclaré mais service éventuellement indisponible ; tester `/ready` et un document synthétique.
3. **Indexation absente ou partielle** : une UI accessible ne garantit pas l'existence d'index, la fin des jobs ni des embeddings.
4. **Erreur d'inférence** : LiteLLM workstation ou alias `embedding` inaccessible, clé invalide, budget dépassé ou vecteurs de dimensions incompatibles.
5. **Isolement insuffisant** : un corpus privé ne doit pas partager des ACL de recherche avec des consommateurs publics ou un Knowledge Open WebUI non isolé.

## 5. Séquence de résolution et critères de clôture

1. Renseigner le mountpoint **constaté** et produire un relevé anonymisé des vérifications D0–D6.
2. Définir explicitement un sous-ensemble de documents autorisés (sans publier leur contenu), un UID/GID non privilégié et un montage de corpus **read_only: true** dans une modification Compose séparée et vérifiée ; maintenir le répertoire applicatif OpenRAG existant.
3. Valider D7 avec un document de test synthétique. Ne pas lancer l'ingestion Babou avant D0–D7, isolation de l'index, filtrage des traces et autorisation du corpus.
4. Tester D8 de manière bornée ; prouver l'absence d'accès inter-corpus et la purge des index/chunks du POC. Consigner les résultats **sans données personnelles**.
5. Exécuter `python3 scripts/generate-service-topology.py --check`, `python3 scripts/generate-service-consumers.py --check` puis `just pre-push` lors d'un changement de Compose. Aucun PASS runtime n'est revendiqué ici.

**Définition de terminé :** dataset identifié, montage RO/ACL validés, ingestion et recherche vérifiées sur le sous-ensemble approuvé, Docling et LiteLLM opérationnels, comptages cohérents, aucune fuite de données ni exposition WAN.

**Références internes :** [architecture et décisions](#architecture-et-décisions), [roadmap](../roadmap.md), `apps/openrag/compose.yml`, `apps/docling/compose.yml`, `apps/langflow/compose.yml`.

## 6. Roadmap affinée après revue de la PR #259 (2026-10-18)

**Décision de nommage :** le dataset ZFS est `cpool/bababou`, source par défaut `/mnt/cpool/bababou`, et **target obligatoire `/mnt/bababou`**. Le paramètre d'override est `OPENRAG_BABABOU_SOURCE`. Les noms de fichiers documentaires historiques ne changent pas la configuration fonctionnelle.

| Priorité | Action concrète | Preuve d'acceptation | État |
| --- | --- | --- | --- |
| P0 | Confirmer `zfs get mountpoint,mounted,canmount cpool/bababou` ; contrôler chemin, absence de montage manquant | Mountpoint identique à la source Compose ou override explicite ; dataset monté | NON VÉRIFIÉ |
| P0 | Vérifier `docker compose config -q` et le montage `/mnt/bababou` RO sans création de répertoire | `Source` correcte, `Destination=/mnt/bababou`, `RW=false` | COMPOSE MODIFIÉ / NON DÉPLOYÉ |
| P0 | Identifier UID/GID du backend ; vérifier ACL ZFS / POSIX et permissions de traverse sur chaque parent | Lecture effective par le compte runtime non-root ; aucun `chown -R` | NON VÉRIFIÉ |
| P1 | Inspecter l'API et le mécanisme d'import *réel* du backend 0.7.1, sans supposer l'existence d'un scanner filesystem | Contrat d'ingestion / traitement confirmé par version ; pas de lecture brute implicite | À FAIRE |
| P1 | Préparer importateur borné avec allowlist de types, rejet symlinks, limites de taille, profondeur et nombre de documents, et dry-run par défaut | Tests unitaires (récursivité limitée, refus path traversal, dry-run) | À FAIRE |
| P1 | Valider Docling, Langflow, LiteLLM et OpenSearch sur document synthétique | Extraction, embeddings, index, recherche/citations vérifiés | À FAIRE |
| P2 | Créer le corpus `bababou-poc` avec namespace/index séparé, politique de purge, comptes et ACL | Accès inter-corpus refusé ; aucune sortie brute dans traces | À FAIRE |
| P2 | Ingestion de 10–20 fichiers explicitement approuvés ; indexation incrémentale/déduplication et reprise contrôlée | Comptages admis/rejetés/indexés, idempotence, aucune suppression à la source | BLOQUÉ PAR GATES |
| P3 | Évaluer qualité et sécurité de la recherche avant ouverture à d'autres clients | Recall@5, MRR@10, citations, p95, tests prompt injection et ACL | À FAIRE |

**Points d'attention issus de la revue de la PR :**

1. La PR #259 contient aussi le chantier de quality gate et DefectDojo : tester les changements OpenRAG sans présumer que les autres changements de la PR sont acceptés.
2. Le bind source seule ne configure **ni** un watcher de fichiers **ni** un déclenchement d'ingestion. Un importateur devra s'appuyer sur l'API réellement compatible avec la version déployée.
3. L'owner `albandrieu:albandrieu` ne garantit pas la lecture depuis un conteneur ; l'accès dépend du mapping UID/GID et des ACL. Corriger les ACL de façon minimale uniquement après diagnostic.
4. Ne pas lancer de `docker compose up`, changer de configuration TrueNAS, ni lire le contenu des documents depuis la CI.
5. Les documents peuvent contenir des données à caractère personnel et des pièces juridiques. Interdire publication de noms, chemins de fichiers et extraits dans GitHub, CI, observabilité, embeddings hébergés non autorisés ou API publiques.
6. Avant le merge, vérifier le diff global de la PR #259, les éventuels conflits avec master, les contrôles de qualité, et l'absence de régression DefectDojo / quality gate. Aucun de ces statuts n'est réputé vert sans preuve.

**Gate de livraison :** Compose syntaxiquement valide, mountpoint et permissions vérifiés, tests contractuels de découverte/ingestion, autorisation du sous-ensemble, puis preuve runtime. Tant que ces conditions manquent, le changement reste préparatoire.

## 7. FastAPI → LiteLLM, Ollama et recherche privée OpenRAG

| Saut | Configuration versionnée | Preuve à obtenir |
| --- | --- | --- |
| FastAPI sample → LiteLLM TrueNAS | `LITELLM_URL=http://172.17.0.24:4000`, `DEFAULT_CHAT_MODEL=fastapi-qwen`, virtual key `LITELLM_API_KEY` dans `sample/.env.secrets` | Clé scoped, modèle listé, chat synthétique et tool-calling |
| LiteLLM TrueNAS → workstation | `fastapi-qwen` vers `LITELLM_WORKSTATION_API_BASE` avec `LITELLM_FASTAPI_WORKSTATION_API_KEY` | Allowlist des deux virtual keys ; **aucun repli implicite vers un modèle payant** |
| Ollama TrueNAS | `apps/ollama/compose.yml`, port `30068`, `/api/tags` | Modèles réellement installés ; ne pas supposer `qwen` présent |
| FastAPI → OpenRAG | `MCP_CLIENTS`, `mcp_call_tool`, `openrag-frontend:3000/mcp` + `X-API-Key` | Route et authentification sur l'image déployée, liste des outils |
| OpenRAG → Bababou | `cpool/bababou` en lecture seule sur `/mnt/bababou` | Corpus approuvé, index isolé, filtre de connaissance, citations, ACL |

Le MCP OpenRAG v0.7.1 (`sdks/mcp/README.md`) expose `openrag_search`
(avec `filter_id`), mais **aussi** `openrag_ingest` et
`openrag_delete_document` : ne jamais proposer ces outils à un agent
public.

### Diagnostic de la chaîne (sans secret)

```bash
# Contrats Compose seulement, aucun service contacté
python3 scripts/truenas/diagnose-fastapi-ai-chain.py --check
# Depuis la workstation, sondes exécutées dans fastapi-sample via SSH
python3 scripts/truenas/diagnose-fastapi-ai-chain.py \
  --check --runtime --ssh-target albandrieu@172.17.0.24
# Uniquement si `sudo -n docker` est déjà autorisé (socket inchangé)
python3 scripts/truenas/diagnose-fastapi-ai-chain.py \
  --check --runtime --ssh-target albandrieu@172.17.0.24 --ssh-sudo
```

Le mode runtime fait des GET **anonymes sur des URL fixes**, n'envoie
jamais `X-API-Key`, ne suit pas les redirections et ne lit aucun corps
HTTP. `declared` signifie seulement que le contrat existe ;
`bababou_private_retrieval=not_verified` et
`openrag_search=not_tested_requires_auth` sont attendus tant qu'aucune
recherche filtrée authentifiée n'a eu lieu.

| Statut | Lecture |
| --- | --- |
| `docker_socket_denied` / `sudo_noninteractive_denied` | Droits Docker du compte SSH ; ne pas modifier le socket |
| `docker_daemon_unavailable`, `fastapi_container_missing`, `fastapi_container_not_running`, `fastapi_container_python_missing` | Hôte ou conteneur ; vérifier sans relancer |
| `probe_output_invalid` | Contrat JSON de la sonde |
| `http_401` / `http_403` | Service joignable, authentification non validée |
| `http_405` / `http_406` sur `/mcp` | Normal pour un GET anonyme sur un MCP streamable HTTP ; ne prouve ni le service ni l'accès privé |
| `dns_failure`, `tcp_refused`, `connection_timeout`, `http_5xx`, `http_30x` | Transport ou serveur |

### Confidentialité des requêtes OWNER

La recherche privée Bababou n'est **pas** le parcours de l'agent
générique `POST /run`. L'endpoint opt-in
`POST /private/ops/ai/bababou/search` de `fastapi-sample` :

- exige un JWT **OWNER** et une source réseau autorisée
  (`nabla/route_policy.py`, `access_control.py`) ;
- exige `OPENRAG_BABABOU_FILTER_ID` défini en privé, sinon HTTP 503 ;
- n'accepte qu'un client `MCP_CLIENTS` nommé `openrag`
  (`streamable-http`, `url=http://openrag-frontend:3000/mcp`,
  `X-API-Key`) ;
- n'appelle que `openrag_search(query,limit,filter_id)`, limite `1..5`,
  requête bornée, chemins locaux expurgés, réponses non mises en cache.

L'agent `/run` ne reçoit pas les outils OpenRAG ; ne **pas** définir
`OPENRAG_GENERAL_MCP_TOOLS_ENABLED=true` pour un corpus sensible.
`fastapi-qwen` passe par la workstation : réservé aux requêtes
synthétiques. Pour des documents Bababou, valider rétention/traces,
réseau et inférence strictement locale (Ollama TrueNAS) avant usage ;
ne pas injecter les résultats dans une requête à un modèle distant par
défaut. `index_not_verified` ou `retrieval_not_verified` doit rester
visible.

**Secrets :** clé API OpenRAG propre à cet usage (ni clé
d'administration globale, ni clé LiteLLM) ; `sample/.env.secrets`
porte `MCP_CLIENTS` et `OPENRAG_BABABOU_FILTER_ID`, récupéré **après**
création d'un filtre limitant exactement le corpus autorisé. Ne jamais
afficher `docker inspect .Config.Env` ni committer d'exemple avec un
jeton actif ; conserver `OPS_ROUTE_POLICY_STRICT`. Un HTTP 200 sur
`/mcp` ne prouve pas l'autorisation du filtre.

### Gates d'acceptation

1. FastAPI a chargé `LITELLM_URL`, le modèle et **la présence** (sans
   la valeur) de sa clé dédiée.
2. `fastapi-qwen` répond à une complétion synthétique et au
   tool-calling avec le jeton scoped, sans document Bababou.
3. `Ollama /api/tags` liste les modèles réellement chargés ; décider
   ensuite d'un éventuel alias LiteLLM local séparé.
4. OpenRAG backend/Docling/Langflow/OpenSearch sains et `tools/list`
   MCP obtenu après authentification.
5. Filtre de connaissance **exact** du corpus autorisé : une recherche
   hors corpus retourne zéro document ; identité et ACL du filtre
   conservées.
6. En OWNER, recherche d'un **document synthétique** avec citation et
   page ; requête anonyme et mauvais filtre refusés.
7. Indexer un petit sous-ensemble réel seulement après approbation
   explicite de la liste, revue des logs LiteLLM/Langfuse/OpenRAG et
   validation de la suppression du test.

Ne pas redéployer, indexer, exposer de port, créer de tunnel Cloudflare,
transmettre de PII hors du LAN ni modifier de secrets tant que ces gates
ne sont pas vérifiées.
