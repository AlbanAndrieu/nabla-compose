## CTEM / DefectDojo : réconciliation locale des preuves d'import

La nouvelle commande `scripts/security/reconcile-defectdojo-evidence.py` est **strictement en lecture**. Mode `--check` hors ligne pour la CI ; `--report` est destiné à une consultation future depuis TrueNAS (non exécutée par cette contribution).

Sources inspectées : inbox Trivy Compose, Trivy image FastAPI, Trivy/Nuclei/ZAP Site Alban, ZAP Bababou, archives privées ZAP natif. Aucun scanner, import API, secret ou lien réseau n'est lu par ce script.

Le rapport JSON conserve le type, l'identifiant de run, la fraîcheur des preuves et le statut d'import :
- `STAGED_NO_IMPORT_PROOF` : seulement un fichier récupéré de GitHub, pas une vulnérabilité créée ;
- `PENDING_REVIEW` / `API_ACKNOWLEDGED_UNVERIFIED` : marker FastAPI correct, mais ingestion et déduplication non attestées ;
- `ARCHIVED_PROCESSING_CONFIRMED` : manifeste ZAP, SHA-256 du rapport XML et réponse DefectDojo sauvegardée concordants. **Ce n'est pas une nouvelle vérification live de l'API ni du nombre de findings** ;
- `INCOMPLETE_SCAN`, `INVALID_EVIDENCE`, `INTEGRITY_MISMATCH`, `NOT_OBSERVED` : états non interprétés comme « 0 vulnérabilité » ou « service DOWN ».

Aucun contenu HTTP brut, token, endpoint ou chemin privé n'est affiché. `finding_count` reste `null`. Ne pas publier la sortie d'un archivage privé dans GitHub Actions public. La validation définitive nécessitera ultérieurement un `GET` authentifié du Test/finding DefectDojo avec preuve de déduplication et d'horodatage.

Tests offline : `python3 -m unittest tests.test_defectdojo_evidence_reconciliation -v`.

## H13 — Reçus d'import GitHub Actions (28 novembre 2026)

Le collecteur `poll-defectdojo-gh-artifacts.py` conserve désormais un marqueur
privé `<rapport>.import.json` et une réponse brute de l'API
`<rapport>.import-response.json` pour les sources Compose, Site Alban,
Bababou et FastAPI. Les fichiers restent dans l'inbox TrueNAS `0700` et
doivent appartenir à root avec un mode `0600`. L'importeur borne la réponse
de l'API à 1 Mio et n'en affiche que les métadonnées non sensibles.

**Provenance** : `source`, `kind`, identifiant de run GitHub,
SHA-256 du rapport privé, engagement DefectDojo préexistant et statut
`pending_review` ou `acknowledged`.

**Idempotence** : le marqueur est créé par `O_EXCL` *avant* le POST ;
un timeout, une perte de réponse ou une interruption laisse
`PENDING_REVIEW` et interdit une nouvelle soumission automatique.
Un nouveau run ou un rapport différent ne réutilise jamais l'ancien reçu.
Un rapport déjà téléchargé (`ALREADY_STAGED`) peut désormais être importé
une fois après approbation sans second téléchargement.

**Vérification** : un accusé d'API contenant un `test_id` positif est
`API_ACKNOWLEDGED_UNVERIFIED`, non `CONFIRMED`.
Le traitement Celery, les findings créés et leur déduplication doivent
être prouvés par consultation authentifiée du Test DefectDojo après import.
Les statuts `NOT_OBSERVED`, `PENDING_REVIEW` et `UNVERIFIED` ne deviennent
jamais `0 finding` ni `DOWN`.

Le code et les tests sont hors ligne. **Aucun import ni accès TrueNAS
n'a été réalisé par cette contribution.** Le cron reste désactivé
par défaut et aucune auto-approbation n'est ajoutée.
