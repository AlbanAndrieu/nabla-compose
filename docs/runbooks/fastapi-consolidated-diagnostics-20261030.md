# Diagnostic consolidé FastAPI — UI, Prometheus, LiteLLM et OpenRAG

**30 octobre 2026 · PR #295 · lecture seule.** Ce script agrège les
diagnostics existants. Il ne déploie rien, ne change aucune ACL, ne modifie
pas les clés, ne déclenche pas de CI, et ne demande aucune inférence LLM
ni recherche privée. Aucune sortie brute de Docker, Prometheus, de clé
ou de journal ne passe dans le rapport.

## Commande unique sur TrueNAS

Depuis le dépôt canonique nabla-compose :

~~~bash
cd /mnt/cpool/compose/nabla-compose

# L1 : tests isolés sans réseau ni GitHub Actions
just fastapi-stack-diagnostics-test

# Contrôles TrueNAS en lecture seule (accès root préexistant)
sudo python3 scripts/truenas/diagnose-fastapi-stack.py --check

# Variante compacte machine-readable, expurgée
sudo python3 scripts/truenas/diagnose-fastapi-stack.py --check --json
~~~

La recette courte just fastapi-stack-diagnostics exécute le même script
sans sudo. Les contrôles Docker et les sources root peuvent être
UNVERIFIED dans ce mode. Le script n'effectue jamais de sudo implicite.
L'identité TrueNAS est vérifiée par la commande middleware locale
midclt call system.info ; hors TrueNAS les sondes Docker/IA sont NOT_RUN.

## Sélection d'un domaine

~~~bash
python3 scripts/truenas/diagnose-fastapi-stack.py --check --scope ui
python3 scripts/truenas/diagnose-fastapi-stack.py --check --scope prometheus
sudo python3 scripts/truenas/diagnose-fastapi-stack.py --check --scope ai
~~~

- UI : trois GET fixes sur TrueNAS/staging/Cloud. HTTP 403 reste DENIED.
  HTTP 200 du catalogue ne signifie pas que Chromium a rendu les cartes.
- Prometheus : **une seule lecture** de l'API targets active, les
  11 jobs connus et un compteur global. Réutilise le classifieur local.
  N'affiche aucun lastError, scrapeUrl, label privé ou credential.
- IA : état des apps, dépendances OpenRAG, présence des clés LiteLLM
  dans fichier et conteneur, route upstream Workstation, modèle
  fastapi-qwen, interfaces OpenRAG et état du MCP. Aucun appel modèle.
- Le script des métriques FastAPI est recherché dans le sous-dépôt
  ./fastapi-sample ou un dépôt frère. S'il est ailleurs, préciser
  --fastapi-root /chemin/absolu/fastapi-sample. Ne pas invoquer
  diagnose-fastapi-metrics-auth.py depuis nabla-compose directement :
  ce fichier appartient au dépôt FastAPI. Sans copie locale = NOT_RUN.

## Options explicites, facultatives

~~~bash
# Vérifier promtool/configuration, sans prendre les exporters DOWN
# pour une erreur syntaxique de Prometheus
sudo python3 scripts/truenas/diagnose-fastapi-stack.py \
  --check --scope prometheus --deep-prometheus

# Navigateur, seulement sur machine avec Python Playwright/Chromium déjà installés
python3 scripts/truenas/diagnose-fastapi-stack.py \
  --check --scope ui --browser --fastapi-root /chemin/fastapi-sample
~~~

Le mode browser compare safe/full sur TrueNAS et Cloud. Sans Playwright,
le préflight est NOT_RUN et aucune navigation n'est faite. Préférer
l'exécution Chromium sur une workstation autorisée plutôt que d'installer
des paquets sur TrueNAS.

## Lire le verdict

| État | Sens |
| --- | --- |
| PASS | La sonde précise a réussi ; pas une acceptation globale |
| FAIL | Échec établi : TCP, clé runtime absente, app effectivement bloquée |
| DENIED | Politique HTTP 401/403, pas une panne réseau |
| UNVERIFIED | Cause, cible ou preuve insuffisante |
| NOT_RUN | Sonde non exécutée, outil ou source inaccessible |

Code de retour 1 si au moins un FAIL ; 2 si résultat incomplet sans FAIL ;
0 si les précontrôles sélectionnés réussissent. Le rapport conserve
toujours Cloud UI manual acceptance=NOT_RUN et
OpenRAG private retrieval acceptance=NOT_RUN. Aucun code ne déclenche
un déploiement.

## Lecture des preuves du 30 octobre

- Prometheus est HEALTHY, mais 6 targets échouent. fastapi_sample a été
  DOWN/TCP puis UP lors de deux scrapes : refaire **une seule** capture
  cohérente plutôt que conclure à une panne persistante.
- LiteLLM TrueNAS est prêt ; le relais vers la workstation ne dispose
  pas de LITELLM_FASTAPI_WORKSTATION_API_KEY dans l'environnement
  du conteneur. Ne pas substituer LITELLM_IDE_API_KEY ou master key.
- OpenRAG backend/frontend HEALTHY et /mcp HTTP 406 ne prouvent
  ni une session MCP authentifiée ni une recherche privée Bababou.
- Cloud et staging HTTP 403 = contrôle d'accès à qualifier depuis
  ce point d'observation. Playwright absent = NOT_RUN navigateur.

Voir aussi la [roadmap](../roadmap.md),
le [runbook FastAPI IA](fastapi-truenas-ai-bababou-20261026.md),
la [recette LiteLLM](fastapi-truenas-ai-acceptance-20261027.md)
et le [scrape Prometheus](fastapi-prometheus-scrape-secret-20261026.md).

## Lire seulement les blocages (mode bref)

Après les premiers diagnostics complets, éviter de recopier toutes les lignes
PASS. La commande suivante **ne relance aucune sonde supplémentaire** :

~~~bash
cd /mnt/cpool/compose/nabla-compose-pr295-acceptance
sudo python3 scripts/truenas/diagnose-fastapi-stack.py --check --brief
~~~

Le mode bref supprime les contrôles PASS de l'affichage et ne duplique pas
l'absence de la clé upstream LiteLLM sous deux noms différents.
Le rapport JSON \`--json\` et les compteurs de résumé conservent **tous**
les enregistrements. Un refus Cloud 403, le scrape LiteLLM Hermes 401
et la recherche OpenRAG non testée restent visibles.

Le contrôle \`fastapi_metrics_auth=NOT_RUN\` signifie ici que le script
complémentaire **appartient au dépôt FastAPI**, et non que le scrape
\`fastapi_sample\` est DOWN. Pour l'activer en lecture seule, localiser
le checkout FastAPI contenant effectivement
\`scripts/truenas/diagnose-fastapi-metrics-auth.py\`, puis utiliser
\`--fastapi-root /chemin/valide/fastapi-sample\`. Ne pas deviner un
chemin de sous-module et ne pas déplacer des secrets.

### Suite de diagnostic sans mutation de clés

Le \`container_key_absent\` de
\`LITELLM_FASTAPI_WORKSTATION_API_KEY\` est **confirmé dans le runtime**.
Le \`file_key_ambiguous\` est volontairement conservateur : une valeur
entre guillemets ou interpolée ne peut pas être comparée directement
avec Docker. Ce statut **ne prouve pas** l'absence du secret source.
La clé \`LITELLM_API_KEY\` de FastAPI est présente côté conteneur, mais
le \`/v1/models=401\` reste un refus indépendant.

Dans le checkout Compose, avec une session Vaultwarden déjà déverrouillée,
en **compte opérateur non root** :

~~~bash
just litellm-fastapi-sample-source-check
just litellm-fastapi-upstream-source-check
~~~

La source et le runtime peuvent être décalés. Ne pas substituer
\`LITELLM_IDE_API_KEY\`, la clé master, ni recréer des clés ou conteneurs
avant attribution de la source et contrôle de l'enregistrement virtuel.

## Session Vaultwarden : contrôle sans sudo

Depuis le worktree Compose, utiliser le shell opérateur non-root :

~~~bash
cd /mnt/cpool/compose/nabla-compose-pr295-acceptance
just fastapi-stack-vaultwarden-check
~~~

Le lanceur lit bw status sans diffuser serverUrl, e-mail ni BW_SESSION.
Une session CLI déverrouillée ne garantit pas l'accès aux items.
Si l'état est bw_login_required, lancer bw login en interactif.
Si l'état est bw_unlock_required ou bw_session_export_missing,
lancer dans le MEME shell, sans recopier le résultat :

~~~bash
export BW_SESSION="$(bw unlock --raw)"
~~~

Le contrôle appelle les deux vérificateurs Vaultwarden déjà versionnés.
Les états vaultwarden_verify_failed, vaultwarden_folder_failed et
vaultwarden_item_lookup_failed désignent respectivement la vérification
du serveur/session/sync, du dossier et de l'item exact. Aucune réponse
brute Vaultwarden ne doit être affichée. Ne pas utiliser sudo ici :
root n'a pas la même session CLI.

## Chemins Compose et FastAPI distincts

Le lanceur diagnose-fastapi-stack.py est dans nabla-compose et non
dans fastapi-sample. Depuis un terminal ouvert dans fastapi-sample,
utiliser son chemin ABSOLU :

~~~bash
sudo python3 /mnt/cpool/compose/nabla-compose-pr295-acceptance/scripts/truenas/diagnose-fastapi-stack.py \
  --check --scope prometheus \
  --fastapi-root /mnt/cpool/compose/nabla-compose/fastapi-sample \
  --brief
~~~

Le lanceur détecte aussi ce chemin FastAPI canonique automatiquement.
Ce chemin a été attesté par l'opérateur. Le NOT_RUN antérieur pour
fastapi_metrics_auth désigne une découverte de fichier manquée, pas
un scrape Prometheus en panne.

## OPENRAG_API_KEY : ne pas confondre secret et authentification

Le code actuellement versionné n'établit aucun consommateur
OPENRAG_API_KEY. L'accès privé FastAPI repose sur MCP_CLIENTS, le filtre
OPENRAG_BABABOU_FILTER_ID et une future identité autorisée.
HTTP 406 sur GET /mcp ne prouve ni un contrôle X-API-Key ni une
session MCP authentifiée. Un token peut être généré en terminal privé
avec openssl rand -hex 32, mais il ne doit être considéré comme
actif qu'après provisionnement et validation du serveur et du client.
Le script ne génère ni ne transmet de secret. Ne jamais remplacer
OPENRAG_ENCRYPTION_KEY ou LANGFLOW_KEY par ce token.

## LiteLLM upstream : séparer les consommateurs

LITELLM_FASTAPI_WORKSTATION_API_KEY présente dans le fichier
/mnt/cpool/secrets/runtime/sample/.env.secrets n'est pas nécessairement
présente dans le conteneur litellm. Son fichier source canonique est
/mnt/cpool/secrets/runtime/litellm/.env.secrets. Vérifier d'abord
la source Vaultwarden et le mapping Compose. docker restart ne
recharge pas les variables d'environnement d'un conteneur existant :
une recréation contrôlée peut être nécessaire après vérification.
