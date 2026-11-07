# TrueNAS : reprise de Prometheus, Pyroscope et des exporters

Date : 2026-10-24. Preuves : relevés opérateur sur TrueNAS, inventaire
`/api/v1/targets` de Prometheus. Triage courant :
[observability triage](../runbooks/2026-10-25-observability-triage.md).

## Symptômes

- `prometheus` redémarre en boucle (exit 2, `oom=false`) avec
  `permission denied` sur `/etc/prometheus/rules/nabla-core.rules.yml`.
- `pyroscope` reste `running` mais la readiness expire ; journaux
  `node is not the leader` et
  `non-monotonic log entries: tried to append index 609650 after 609650`.
- Après reprise : `fastapi_sample` en `scrape_down` (HTTP **401**),
  `postgres_exporter` en `scrape_down` (TCP refusé) ; Akvorado, Gatus,
  Redis, CrowdSec et `pfsense_exporter` UP.

## Cause racine et correctifs

- **Prometheus** : un seul fichier de règles en UID 1000, mode 0600,
  illisible pour l'identité `568:568`. Correction ciblée par
  `scripts/truenas/repair-prometheus-rules-access.sh --apply
  --expected-unreadable 1` (GID 568, mode 0640, inode conservé). TSDB
  intacte ; jamais de `chmod -R` ni `chown -R`.
- **Pyroscope** : état Raft du metastore incohérent. Réinitialisation
  explicite par `scripts/truenas/recover-pyroscope-metastore.sh --apply
  RESET_PYROSCOPE_HISTORY` : arrêt du seul conteneur, déplacement des
  états vers `/mnt/cpool/pyroscope/data/.metastore-backup-20261024T210505Z`
  (sauvegarde **conservée**), redémarrage. L'historique de profils est
  perdu. Le script refuse un second reset tant qu'une sauvegarde existe.
- **FastAPI `401`** : `/metrics` est `INTERNAL` et Prometheus n'envoyait
  aucun jeton. Un 401 est une authentification refusée, **pas une panne
  de l'API**. Corrigé par une clé dédiée au scrape (`METRICS_SCRAPE_KEY`,
  `credentials_file` en lecture seule) ; contrat dans le triage.
- **PostgreSQL exporter** : secret absent et conteneur non déployé.
  `env_file` ne fournit pas les interpolations `${...}` du YAML, ce qui
  pouvait démarrer l'exporter sans DSN. Le conteneur lit désormais
  `/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets` en
  `format: raw` (Compose ≥ 2.30.0), `root:root 0600`, avec un rôle dédié
  `pg_monitor` sans `SUPERUSER`/`CREATEDB`/`CREATEROLE`/`BYPASSRLS`.

## Décisions

- **DoT non appliqué.** La migration pfSense → Quad9 en DNS-over-TLS
  (forwarding, `dns.quad9.net`, LAN en DNS classique vers `172.17.0.1`)
  reste une proposition : elle exige sauvegarde et fenêtre de maintenance
  et ne doit pas se faire pendant l'enquête OOM d'Unbound. Côté client,
  `DNSOverTLS=opportunistic` autorise un repli silencieux en clair.
- `pfsense_exporter` (`:9945`) se paramètre par `__param_target` : ne pas
  l'interroger à la main comme un exporter standard ni en rafale.

## Leçons

- Un conteneur `running` ou un `docker start` réussi ne prouve pas la
  readiness ; `unreadable=0` ne prouve pas que Prometheus tourne.
- `scrape_up` sans `pg_up == 1` ne prouve pas la connexion à PostgreSQL.
- `no_active_target` (pas de cible) et `scrape_down` (cible non UP) sont
  deux états distincts.

## Diagnostic (lecture seule)

- `sudo bash scripts/truenas/diagnose-observability-post-repair.sh --check`
- `python3 scripts/prometheus/diagnose-failed-scrapes.py --check`
- `sudo bash scripts/truenas/diagnose-postgres-exporter.sh`
- `python3 scripts/truenas/collect-observability-evidence.py`
  (`just observability-evidence-lan`)

## Suites

- Supprimer la sauvegarde Pyroscope seulement après validation de la
  readiness et de l'intégration Grafana.
- DoT pfSense → Quad9 : décision et fenêtre à planifier séparément.
