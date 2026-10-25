# TrueNAS — deuxième contrôle critique du 25 octobre 2026

**Source :** résultat fourni par l'opérateur, depuis TrueNAS.
Commande : `sudo bash scripts/truenas/finish-migrations-20261024.sh --check --section critical`.
**Statut :** `PASS=9 FAIL=7 WARN=0 SKIP=0` (contre `8/8` au relevé précédent).
Ce sont des observations datées ; **ne pas déduire la disponibilité actuelle**.

| Domaine | PASS | FAIL |
| --- | --- | --- |
| Prometheus | `prometheus-rules-access` | `prometheus-targets`, `prometheus-config-access` |
| OpenRAG | `openrag-dependencies`, `openrag-env-migration` | `openrag-startup`, `ai-runtime-recovery`, `openrag-opensearch-legacy-secret`, `openrag-backstage-bundle` |
| Sentry | `sentry-consumers`, `sentry-recovery-preflight` | Aucun dans ce relevé |
| Akvorado | `akvorado-config`, **`akvorado-blocked`** | `akvorado-fresh-inserts` |
| DefectDojo | `defectdojo-preflight`, `defectdojo-private-ingress` | Aucun dans ce relevé |

La progression est **`akvorado-blocked` : FAIL → PASS**.
Le contrôle `akvorado-fresh-inserts` exige une augmentation du compteur
de lots ClickHouse pendant 20 s. Son échec **ne prouve pas une
corruption ClickHouse** ; ne pas redémarrer Kafka ou ClickHouse.

**Preuve privée** (ne pas copier dans Git) :
`/mnt/cpool/var/nabla/migration-20261024/session-hgLyW87n`.

## Collecte ciblée sans mutation

Une fois les nouveaux scripts **déployés dans un checkout revu**
(par exemple après fusion de la PR #280), exécuter sur TrueNAS :

```bash
sudo bash scripts/truenas/triage-critical-failures.sh --check
```

Le script relance **uniquement les sept gates en échec**, consigne
leurs journaux privés (`0700` pour le répertoire, `0600` pour
les fichiers) et affiche uniquement `PASS`, `FAIL` ou
`UNVERIFIED`. Un échec ne masque pas le suivant. Aucune opération
`app.start`, `app.redeploy`, `--apply` ou rotation de secret.

**Avant fusion de #280**, sur `master` TrueNAS, exécuter au besoin
ces commandes **indépendamment** :

```bash
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check
sudo bash scripts/truenas/repair-prometheus-config-access.sh --check
sudo bash scripts/truenas/diagnose-openrag-startup.sh --check
sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
python3 scripts/check-service-migration-bundle.py --app openrag
sudo python3 scripts/truenas/diagnose-akvorado-flow.py --strict --require-inserts --observe-seconds 60
```

**Attention :** l'ancien `diagnose-ai-secret-recovery.py` n'a pas
`--scope openrag` et peut signaler aussi Scrutiny/LiteLLM. La PR #280
ajoute cette option ; ne pas la passer au script sur `master` avant
sa mise à jour.

## Préconditions de remédiation

### Prometheus

1. Confirmer le bind-mount `/etc/prometheus` et l'UID/GID 568.
2. Lire le log privé du contrôle `prometheus-config-access`.
3. **Uniquement si** le rapport prouve un défaut de groupe ou de mode
   sur le fichier attendu, appliquer la réparation bornée :

```bash
sudo bash scripts/truenas/repair-prometheus-config-access.sh --apply
```

Cette opération agit sur **un seul fichier** (`prometheus.yml`) et
refuse un mount ou UID différent ; elle n'effectue ni redéploiement ni
modification du WAL/TSDB. Si une ACL ZFS ou le montage diverge, arrêter
et corriger la cause par un changement distinct et revu.
Rejouer `--check` avant de redémarrer quoi que ce soit.

### OpenRAG

1. Vérifier que les fichiers Vaultwarden canoniques sont matérialisés
   et que les secrets `OPENSEARCH_PASSWORD`, `LANGFLOW_KEY`,
   `LITELLM_IDE_API_KEY`, `OPENRAG_ENCRYPTION_KEY` sont présents
   **sans afficher leurs valeurs**.
2. Vérifier `bootstrap-repository-env-files.sh --check openrag`
   et `reconcile-openrag-opensearch-secret.sh --check`.
3. Dans la PR, `apps/openrag/compose.yml` utilise désormais
   `/mnt/cpool/secrets/runtime/openrag/.env.secrets`. Le bundle
   Backstage attendait déjà ce chemin. Cette correction **ne
   déploie pas** la nouvelle définition sur TrueNAS.
4. Vérifier le Compose réellement stocké par TrueNAS. Ne pas
   supposer que modifier le dépôt a réconcilié une Custom App.
5. Après sauvegarde et validation des identifiants existants,
   approuver **un seul** démarrage/réconciliateur OpenRAG ; tester
   backend/frontend `running+healthy` puis le transport authentifié.
6. Ne pas exécuter l'ancien `reconcile-openrag-opensearch-secret.sh
   --apply` : cette action est volontairement interdite.
7. N'effectuer aucune ingestion du corpus Bababou avant la readiness
   Docling et un smoke sur document synthétique.

### Akvorado

1. Rejouer le diagnostic sur une fenêtre de **60 s** pendant l'envoi
   attendu de flux pfSense.
2. Comparer les deltas `received_flows`, `metadata_missing`,
   `kafka_messages` et `clickhouse_batches` dans le rapport.
3. Si les nouveaux lots restent à zéro, vérifier la source NetFlow,
   le metadata provider et les nouveaux messages Kafka.
4. Un lot positif est seulement une indication ; confirmer de
   **nouvelles lignes datées** dans ClickHouse avant acceptation E2E.

[Retour à la roadmap](../roadmap.md) ·
[Opérateur de migration](truenas-migration-operator.md) ·
[Premier relevé](2026-10-25-critical-acceptance-evidence.md).
