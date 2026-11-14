# Audit des diagnostics — duplication fonctionnelle et preuves uniques

**Revue du 14 novembre 2026** à partir des scripts suivis de `nabla-compose` et des endpoints de `fastapi-sample`. *Candidat au refactoring*, sans test LAN. La présence du même endpoint dans deux scripts ne prouve pas que les scripts sont interchangeables.

| Source Compose | Chevauchement avec FastAPI/Gatus/Prometheus | Preuve que les observateurs ne remplacent pas | Action H11 |
| --- | --- | --- | --- |
| `scripts/quality/service-observer-evidence.py` | FastAPI TrueNAS `status`/`health`, Cloud `/sickz` | Compare explicitement les deux points de vue et refuse une provenance extérieure non attestée | **Garder un adaptateur mince**, sans nouvelle base de santé |
| `scripts/truenas/verify-service-observability.py` | Refait HTTP direct + GET Gatus + requête Prometheus par service | Vérifie le câblage d'un **nouveau déploiement** (sonde et métrique attendues) | **Garder uniquement comme test d'acceptation ponctuel** ; supprimer tout polling périodique, raccorder au catalogue V2 |
| `scripts/truenas/diagnose-service-readiness.py` | Teste Gatus/LiteLLM/OpenRAG/Sentry/Prometheus + état Docker | Diagnostic quand API/Gatus non joignables; preuve état conteneur vs HTTP | **Réduire les checks HTTP redondants** ; conserver le mode secours hors observateurs |
| `scripts/truenas/diagnose-fastapi-integrations.py` | TCP PostgreSQL/Redis/Prometheus + état FastAPI | Vérification post-reboot **quand FastAPI est DOWN**, sans dépendre de ses endpoints | **Garder**, réduire au préflight hors-api ; ne pas répliquer le health board |
| `scripts/truenas/diagnose-fastapi-stack.py` | Agrège UI FastAPI, Prometheus, readiness, IA/RAG | Diagnostics de clés, accès, Docker, navigateur et chaîne RAG qu'une sonde HTTP ne vérifie pas | **Refactorer** par scénario, utiliser les sorties structurées des sondes existantes ; éviter seconde normalisation |
| `scripts/truenas/diagnose-fastapi-sample.sh` | Interroge API, Gatus, Prometheus sur plusieurs cycles | SHA déployé, DNS, Docker, cycle de mise à jour | **Garder comme recette d'acceptation** ; durée/cycles limités et déclenchement manuel |
| `scripts/prometheus/diagnose-failed-scrapes.py` | Réinterroge `/api/v1/targets` et classe les erreurs | Distinction « exporter DOWN », erreur TLS/auth, application saine | **Garder comme triage sur échec**, sans répétition du scan de toutes les cibles |
| `scripts/truenas/diagnose-prometheus-targets.sh` | Scrape l'état des targets Prometheus | `promtool`, config, identité et crash du conteneur, checks host | **Conserver les préflights de configuration**, déléguer l'observation de targets au script de triage |
| `scripts/truenas/reconcile-gatus-catalog.py` | Relit configuration Gatus et parfois export de résultats | **Différentiel statique** entre catalogue et sondes déclarées, identifiants et doublons | **Conserver** comme contract test offline ; ne pas en faire une seconde source runtime |
| `scripts/truenas/check-homelab-services.sh` | Relance des sondes réseau via `--deep` et `midclt app.query` | Capacité de reprise autonome après reboot, app.query même sans FastAPI | **Garder en mode rescue** ; pas de scan global par défaut |
| `scripts/observability/verify-stack.sh` | HTTP GET Grafana, Loki, Mimir, Tempo, Prometheus et exporters | Vérification de **configuration/datasources Grafana** et OTLP pour tests pré-cutover | **Garder comme smoke intégration on-demand**, ne pas l'exécuter à chaque agent startup |

## Antipatterns mesurables (pas une suppression au nombre de lignes)

- **Fan-out de sondes** : chaque script relance HTTP/curl/Gatus/Prometheus en parallèle, sans respecter la cadence/cache de l'observateur.
- **Doubles modèles de verdict** : scripts Bash/Python, FastAPI DTO, Gatus et Prometheus inventent ou renomment des états incompatibles.
- **Couplage autorisation/diagnostic** : une commande `--check` peut requérir Docker root ou accès pfSense admin, alors que la question n'exige qu'un état SERVICE.
- **Répertoires basés sur le lieu d'exécution** : `scripts/workstation/` mélange OpenClaw, CrowdSec/pfSense, FastAPI/LiteLLM et opérations OS. Classer d'abord par *propriétaire du domaine*.
- **Le volume des tests n'est pas de la dette automatiquement** : extraire des fixtures seulement après preuve de couverture négative inchangée.

## Bilan cible, à mesurer après migration

- Réduction du nombre d'exécutables de diagnostic ayant une logique HTTP/Gatus/Prometheus **dupliquée**, et non réduction arbitraire des assertions.
- Aucun compte admin pour interroger les informations PUBLIC/SERVICE.
- Par défaut, agent distant : `NOT_RUN` runtime ; workstation : sondes FastAPI internes puis preuve Cloud et approfondissement uniquement en cas d'incident.
- Garder les diagnostics **break-glass** capables de fonctionner si FastAPI, Redis, Prometheus ou Gatus tombent ; empêcher leur exécution régulière.
- Comparer avant/après : taille du code *non généré*, nombre de commandes/identités nécessitant root, nombre d'appels HTTP par diagnostic, temps et faux verdicts.
