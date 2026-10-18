# Diagnostic OpenRAG — ingestion du dataset Babou / Bababou (TrueNAS)

**Statut : procédure de diagnostic, non exécutée sur TrueNAS.**  
**Périmètre :** OpenRAG 0.7.1, Docling partagé, Langflow global, OpenSearch, LiteLLM et source ZFS `cpool`.  
**PR de suivi :** #259. Ne pas fusionner sur la seule base de cette procédure.

## 0. Constat vérifiable dans Git

- `apps/openrag/compose.yml` déclare `openrag-backend` et `openrag-frontend`, les documents applicatifs sous `./openrag-documents:/app/openrag-documents`, et les volumes `./data`, `./config`, `./keys` ainsi que `./flows/backup`.
- Le backend utilise `http://docling:5001`, `http://langflow:7860`, `opensearch:9200` et LiteLLM `http://172.17.0.57:4000/v1` par défaut. Ces variables n'attestent **ni** la disponibilité des services **ni** une ingestion réussie.
- Le Compose **ne déclare aucun montage** du dataset Babou vers `/app/openrag-documents` : il faut d'abord identifier la source, choisir un sous-ensemble autorisé et spécifier un montage **en lecture seule**, sans supprimer les volumes applicatifs existants.
- Le **nom ZFS exact, le mountpoint, la structure et l'état de synchronisation** du répertoire Babou ne sont pas connus. Ne pas les déduire de son nom. L'appellation historique `Bababou` peut différer de `babou`.

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

**Références internes :** [architecture RAG Bababou](rag-bababou-poc-architecture.md), [roadmap](../roadmap.md), `apps/openrag/compose.yml`, `apps/docling/compose.yml`, `apps/langflow/compose.yml`.
