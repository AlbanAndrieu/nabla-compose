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
