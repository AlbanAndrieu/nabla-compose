# RAG Nabla — Docling partagé, OpenRAG API/MCP, Open WebUI et corpus Bababou

**Statut : architecture cible et POC planifiés — 2026-10-10.**
Ce document ne prouve ni un déploiement nouveau ni l'indexation du corpus.
Conserver les deux interfaces, et ne pas créer une seconde instance Docling.

## Décisions et état réellement déclaré

| Composant | Source déclarative | État / rôle |
| --- | --- | --- |
| Docling Serve CPU | `apps/docling/compose.yml` | **Service commun déclaré** `http://docling:5001`, hôte LAN `172.17.0.24:5001`, `/ready` ; sa santé effective doit être mesurée |
| OpenRAG | `apps/openrag/compose.yml` | Backend `0.7.1` : `DOCLING_SERVE_URL=http://docling:5001`, OpenSearch, Langflow global et LiteLLM workstation `172.17.0.57:4000/v1` |
| Langflow | `apps/langflow/compose.yml` | Service global `langflow:7860`, image compatible OpenRAG ; ne pas créer un Langflow dédié à OpenRAG |
| Open WebUI | `apps/openwebui/compose.yml` | Chat et Knowledge, utilise le LiteLLM TrueNAS `172.17.0.24:4000/v1` ; **Docling non encore configuré** ; `intranet` non déclaré explicitement |
| LiteLLM TrueNAS | `apps/litellm/config.yaml` | Alias `embedding` routé vers LiteLLM workstation, `embedding-local` pour repli explicite et `workstation-qwen` ; vérifier API, identité du modèle et dimensions |

**Cible logique** :

```text
Open WebUI (chat, Knowledge, ACL par utilisateur)
     |             \\
     | LiteLLM      \\ MCP (si disponible sur version effective) / OpenAPI
     v               v
LiteLLM TrueNAS   Adaptateur RAG restreint (lecture/recherche seulement)
     |               |
     v               v
LiteLLM workstation GPU <-- OpenRAG Backend --> Langflow global
                            |          |
                         Docling     OpenSearch
                            ^
                            |
                     Open WebUI extraction
```

Le rôle de LiteLLM est la **passerelle modèle** (chat/embeddings), pas l'orchestrateur de retrieval ni un substitut à OpenRAG. `fastapi-sample` peut utiliser le même adaptateur RAG avec une identité de service distincte et des permissions côté serveur, derrière ses propres contrôles d'accès. Ne jamais donner au service externe l'accès direct à OpenSearch, Langflow, Docling ou au volume source.

## P0 — Mutualiser Docling déjà présent

1. Sur TrueNAS, vérifier `midclt app.query`, `docker inspect docling`, `curl -fsS http://172.17.0.24:5001/ready`. Comparer le digest réel à la version déclarée : un Compose n'est pas un déploiement.
2. Depuis OpenRAG, vérifier la résolution de `docling`, le port 5001, et réaliser un test d'extraction non sensible ; un environnement configuré n'est pas une preuve de conversion.
3. Ajouter à Open WebUI l'accès réseau contrôlé à `intranet` et configurer l'extraction Docling (suivant la version vérifiée : `CONTENT_EXTRACTION_ENGINE=docling`, `DOCLING_SERVER_URL=http://docling:5001`). Contrôler aussi la configuration persistante de l'admin, car `ENABLE_PERSISTENT_CONFIG=false` est déclaré. Valider le moteur/endpoint effectif plutôt que de présumer l'application de variables inconnues.
4. Même service d'extraction, mais **deux jeux d'index et deux politiques d'autorisation** : ne pas mutualiser les collections OpenSearch/Knowledge par simple pointage d'URL.
5. Smoke avec PDF non sensible contenant tableau, image et pages scannées ; vérifier métadonnées/page, échec réseau et timeouts. Aucune activation de traitement distant d'images par défaut.

**Done** : conversion cohérente via les deux clients vers la même instance Docling, journal d'identité/version et aucun document privé dans les logs.

## P1 — Exposer OpenRAG en service de retrieval indépendant

- Vérifier **sur le conteneur OpenRAG 0.7.1 courant** les routes REST et la présence effective du point `/mcp` : la documentation de la branche amont actuelle ne garantit pas cette fonctionnalité dans 0.7.1. Ne pas inventer de route, de schéma OpenAPI ni d'authentification.
- **Option A (préférée pour Open WebUI si support vérifié)** : MCP Streamable HTTP, URL privée, authentification au niveau serveur, allowlist d'outils *search/read* seulement, scopes de corpus ; désactiver ingestion, suppression, réglages et opérations admin pour les consommateurs de recherche.
- **Option B (par défaut pour fastapi-sample)** : adaptateur HTTP/OpenAPI interne minimal proposant `search(query, corpus_id, top_k)`, `answer(query, corpus_id)` si justifié, avec résultats structurés `document_id`, `source_path_redacted`, `page`, `snippet`, `score`, `citation`. Endpoints concrets à adapter au SDK/API OpenRAG épinglé, jamais exposer l'API admin.
- LiteLLM TrueNAS reste le **point d'entrée de l'inférence** ; OpenRAG exécute retrieval/indexation, Docling parse, OpenSearch indexe. Ajouter un modèle proxy seulement après vérification des embeddings et de la latence. Interdire une bascule silencieuse entre embeddings de dimensions différentes.
- Pour `fastapi-sample.fastapicloud.dev` hors LAN, utiliser un **endpoint externe dédié** derrière Cloudflare Access service-token ou équivalent avec politique restrictive ; aucun tunnel public RAG ajouté avant revue d'authentification, limitation de débit, isolation de corpus et filtrage des réponses.
- Journaliser statut, latence, volume et identifiant technique, **pas le prompt intégral, les chunks privés, les identités nominatives ou les clés** par défaut. Tester 401/403, accès inter-corpus, injection de prompt dans les documents, ACL, rotation et révocation.

**Done** : recherche authentifiée et cloisonnée depuis Open WebUI et, séparément, depuis un client de test local pour fastapi-sample ; absence de route privée accessible anonymement.

## P2 — POC corpus Bababou (copie Google Drive sur cpool)

Le répertoire exact sur `/mnt/cpool` **n'est pas établi par ce document**. Ne pas inventer un montage `/mnt/cpool/bababou` ; découvrir le chemin avec l'opérateur et confirmer qu'il s'agit de la copie Google Drive attendue. Ne jamais faire de `find /mnt/cpool` non borné ou de copie globale sans accord.

1. **Inventaire sans lecture du contenu** : découvrir le dataset et le point de montage par `zfs list` / `stat`, compter fichiers et extensions avec un parcours borné au répertoire confirmé ; identifier doublons, pièces sensibles, fichiers Google natifs éventuellement non exportés, symlinks, MIME et tailles.
2. **Sélection POC** : commencer par 10–20 documents expressément validés, PDF (texte/OCR), DOCX et tableaux, sans correspondance privée ou pièce juridique nominative non approuvée. Source strictement en lecture seule, service UID non privilégié ; n'indexer ni toutes les pièces automatiquement ni le chemin brut sur un service exposé.
3. **Isoler** : créer un corpus `bababou-poc` distinct, index OpenSearch et droits dédiés, chemin de staging privé et chiffrement/backup appropriés ; embeddings et LLM locaux ou attestés non conservés côté fournisseur. Revoir `Langfuse` et LiteLLM : les réglages actuels de logs et traces peuvent capturer textes ou prompts ; les désactiver/masquer pour ce corpus avant ingestion.
4. **Comparer** : mêmes documents, mêmes embeddings, même modèle, mêmes 20–30 questions annotées ; exécuter Open WebUI Knowledge et OpenRAG, mesurer recall@5, MRR@10, fidélité, citations avec page, latence p95, durée d'indexation, RAM/CPU/GPU, coût des changements.
5. **Exercer la sécurité** : recherche vide, suppression de document et purge vérifiée des chunks, test d'accès inter-corpus, injection de prompt, détection de secrets et refus d'accès depuis `fastapi-sample` sans identité/scopes. Prévoir purge des index et restaurations.

**Done** : comparaison reproductible, tableau de scores sans extraits privés, décision motivée sur Open WebUI seul ou recherche OpenRAG mutualisée, aucune exposition incontrôlée de documents.

## Gates, dépendances et reports

- **P0** : Docling commun réellement disponible et configuration clients vérifiée ; si Docling n'est pas opérationnel, ne pas faire dépendre les autres services de cet accès.
- **P1** : versions OpenRAG/MCP/Open WebUI/API testées avant création de connecteurs.
- **P2** : autorisation explicite du sous-ensemble Bababou, logs privés, ACL et index séparés.
- **P3** : connexion externe fastapi-sample uniquement une fois l'authentification, le contrôle des permissions et l'observabilité minimisée démontrés.
- Ne pas lancer une ingestion, modifier les données cpool, exposer un endpoint ou faire un redeploy depuis cette documentation.
- Revalidation locale : `python3 scripts/generate-service-topology.py --check`, `python3 scripts/generate-service-consumers.py --check`, `just pre-push`. Garder BetterLeaks, SAST, Playwright et ZAP.
  
Références : `docs/ai-stack-upgrade-consolidation-plan.md`, `docs/secrets-migration-roadmap.md`, documentation Open WebUI Docling et MCP, README OpenRAG (documentations à confronter aux versions déployées).
