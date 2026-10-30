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
