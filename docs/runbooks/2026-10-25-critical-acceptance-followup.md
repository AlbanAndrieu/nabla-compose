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

## Troisième collecte ciblée — observations complémentaires (25/10)

Deux exécutions successives du triage ciblé ont donné **PASS=1 FAIL=6
UNVERIFIED=0** (sessions privées `focused-5EzLbk` et `focused-mx0EmU`).
Le contrôle `openrag-backstage-bundle` est désormais PASS ; les six
autres gates restent en échec **avant les corrections opérateur
suivantes**.

**Prometheus (post-triage) :** l'opérateur a exécuté
`repair-prometheus-config-access.sh --apply` avec succès. Le fichier
`prometheus.yml` a été conservé avec uid 1000, groupe 568, mode
**0644 → 0640**, et l'accès effectif uid/gid 568 a été validé.
Cela répare la **confidentialité/lecture du fichier**, pas les scrapes.
`promtool` valide 15 fichiers de règles ; Prometheus lui-même
`running`, **21 cibles UP et 7 DOWN**.

| Cible DOWN | Catégorie observée | Hypothèse à valider |
| --- | --- | --- |
| `docling` | connection_refused | composant absent ou métriques non publiées |
| `fastapi_sample` | authorization | politique ou token de scrape dédié |
| `haproxy` | connection_refused | listener métriques non ouvert |
| `litellm_hermes` | authorization | auth exporter distincte |
| `opensearch` | connection_refused | exporter/port observé non joignable |
| `opensearch-security` | connection_refused | exporter de sécurité non joignable |
| `postgres_exporter` | connection_refused | exporter absent ou port fermé, **pas une preuve de panne PostgreSQL** |

**OpenRAG :** le middleware confirme `RUNNING` et les conteneurs
backend/frontend `running+healthy`. Langflow répond 200 et le corpus
ZFS est monté sans lecture des données. Le préflight échoue **sur les
noms de clés manquantes** `LITELLM_IDE_API_KEY` et
`OPENRAG_ENCRYPTION_KEY`, non sur le démarrage Docker.
Le diagnostic global LiteLLM indique en plus
`LITELLM_IDE_API_KEY` et `LANGFUSE_SECRET_KEY` manquantes.
`docling` est indisponible pour l'ingestion.

**État des secrets : non finalisé.** `bootstrap-repository-env-files.sh
--check openrag` valide des copies canoniques cohérentes, mais annonce
**un ancien chemin encore présent, finalisation en attente**.
`reconcile-openrag-opensearch-secret.sh --check` échoue sur le
propriétaire ou mode d'un candidat OpenSearch. Après mise à jour de
#280, le contrôle précise la classe de ce candidat **sans lire sa valeur**.
Ne lancer ni `--finalize openrag` ni rotation tant que la présence des
clés requises, l'égalité de mot de passe et le Compose runtime ne sont
pas vérifiés.

**Akvorado :** pendant la fenêtre échantillonnée : **+5 flux reçus,
+4 erreurs `metadata missing`, +2 messages Kafka, 0 lot ClickHouse**.
Les compteurs historiques ont `metadata_provider_errors=105858`
et `snmp_poller_errors=2277`, mais leur delta est respectivement
**+8 et 0**. Le problème actif est la **résolution de métadonnées**
avant insertion ; le PASS ponctuel de `akvorado-blocked` ne suffit
pas à conclure que la panne est résolue. La configuration Git contient
un provider statique pour `ifIndex=11`. Vérifier que la version
réellement chargée par l'App utilise ce provider et que les nouveaux
flux portent cet index, **sans supposer qu'un checksum de fichier
atteste son chargement en mémoire**.

### Vérifications immédiates ciblées

```bash
# Une seule réparation Prometheus a été effectuée : vérifier le résultat.
sudo bash scripts/truenas/repair-prometheus-config-access.sh --check
sudo bash scripts/truenas/diagnose-prometheus-targets.sh --check

# Vérifier les métadonnées et chemins, sans afficher de valeur.
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check openrag
sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check

# Distinguer configuration déclarée/chargée et nouveaux flux.
sudo bash scripts/truenas/diagnose-akvorado-config.sh --check
sudo python3 scripts/truenas/diagnose-akvorado-flow.py \
  --strict --fail-on-blocked --observe-seconds 60
```

### Couleurs et icônes du triage

Le script `triage-critical-failures.sh` utilise désormais
`scripts/lib/diagnostic-ui.sh` (déjà employée par
`finish-migrations-20261024.sh`). Les couleurs sont activées sur
terminal TTY et désactivées dans les sorties redirigées ; `NO_COLOR`
est respectée même avec `--color=always`. Les icônes Unicode sont
automatiques si l'environnement le permet, sinon optionnelles.
**Les fichiers TSV et les logs privés restent sans séquences ANSI.**

```bash
sudo bash scripts/truenas/triage-critical-failures.sh --check
sudo bash scripts/truenas/triage-critical-failures.sh --check --color=always --icons=always
sudo bash scripts/truenas/triage-critical-failures.sh --check --no-color --no-icons
```

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
