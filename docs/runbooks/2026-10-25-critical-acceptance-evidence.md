# Relevé opérateur TrueNAS — gate critical du 25 octobre 2026

**Provenance :** sortie transmise par l'opérateur, commandée sur TrueNAS avec
`sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section critical`.
**Résultat :** `PASS=8 FAIL=8 WARN=0 SKIP=0`. Ce résultat est historique,
pas un état « maintenant ». Révision Git du checkout opérateur : non fournie.

| Domaine | Contrôles PASS | Contrôles FAIL |
| --- | --- | --- |
| Prometheus | `prometheus-rules-access` | `prometheus-targets`, `prometheus-config-access` |
| OpenRAG | `openrag-dependencies`, `openrag-env-migration` | `openrag-startup`, `ai-runtime-recovery`, `openrag-opensearch-legacy-secret`, `openrag-backstage-bundle` |
| Sentry | `sentry-consumers`, `sentry-recovery-preflight` | Aucun dans ce relevé |
| Akvorado | `akvorado-config` | `akvorado-blocked`, `akvorado-fresh-inserts` |
| DefectDojo | `defectdojo-preflight`, `defectdojo-private-ingress` | Aucun dans ce relevé |

**Preuve privée conservée sur TrueNAS :**
`/mnt/cpool/var/nabla/migration-20261024/session-uPAiEbSW`
avec `summary.tsv` et logs privés ; ne pas copier ces fichiers dans Git.

## Suites de diagnostic

1. Isoler `prometheus-targets` et l'accès à la configuration.
2. Vérifier séparément OpenRAG, ses conteneurs et le secret OpenSearch.
3. Exiger des insertions ClickHouse *récentes* pour Akvorado.
4. Garder Sentry et DefectDojo en observation ; PASS aux sondes ne prouve pas
   une acceptation métier ou E2E récente.

Pour une nouvelle collecte, utiliser le
[runbook d'acceptation](homelab-runtime-acceptance.md), pas les commandes
de réparation historisées.
