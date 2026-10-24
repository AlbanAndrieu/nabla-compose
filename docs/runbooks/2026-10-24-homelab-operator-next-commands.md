# Diagnostic homelab — entrée opérateur canonique

**Mis à jour : 25 octobre 2026.** L'ancien inventaire de commandes
datées est conservé dans
[archive](../archive/2026-10-24/2026-10-24-homelab-operator-next-commands.md).
Cette page est la **seule entrée** pour les vérifications en lecture seule.
Aucune commande ici ne démarre, redéploie ou efface un service.

## 1. Services observabilité (TrueNAS)

```bash
sudo python3 scripts/truenas/diagnose-service-bundle.py --check --section observability
# Pour le résultat détaillé de chaque vérification :
python3 scripts/prometheus/diagnose-failed-scrapes.py --check
sudo bash scripts/truenas/diagnose-observability-post-repair.sh --check
sudo bash scripts/truenas/diagnose-postgres-exporter.sh
python3 scripts/prometheus/audit-telemetry-coverage.py \
  --prometheus-url http://172.17.0.24:9090
```

La procédure globale peut être lancée par le script
`scripts/truenas/diagnose-service-bundle.py --check --section observability`
après revue du HEAD ; une panne n'interrompt pas les autres vérifications.
Pour les critères de clôture, consulter
[runbook observabilité](2026-10-24-prometheus-pyroscope-dns-dot-recovery.md).

## 2. pfSense / DNS (diagnostic depuis un hôte autorisé)

```bash
bash scripts/pfsense/diagnose-unbound-split-dns.sh --check
bash scripts/pfsense/diagnose-memory-pressure.sh --check
```

L'absence d'argument `--check` n'autorise **aucune** mutation.
Ne pas multiplier les scrapes pfSense, reboots, mises à jour Snort
ou reconstructions pfBlockerNG pendant le diagnostic.
Voir [runbook pfSense](2026-10-24-pfsense-unbound-pfblocker-whatsapp.md).

## 3. Services applicatifs (TrueNAS)

```bash
sudo bash scripts/truenas/finish-migrations-20261024.sh \
  --check --section critical
sudo bash scripts/truenas/diagnose-openrag-startup.sh --check
sudo bash scripts/truenas/diagnose-sentry.sh --check
```

Ces commandes sont indépendantes. Les sorties brutes potentiellement
sensibles restent sur l'hôte ; ne pas les copier dans une PR.
Pour les procédures individuelles, utiliser les
[runbooks référencés](../README.md).

## 4. Contrat de sécurité et qualité

- Toutes les opérations runtime de cette page sont en **lecture seule**.
- Une absence d'observation reste `UNKNOWN/NOT_RUN`, jamais `UP`.
- L'agent ne déclenche aucune CI GitHub et ne modifie pas l'état de la
  quality gate du dépôt. La gate complète est **NOT_RUN** pour cette PR
  conformément à l'instruction opérateur ; les tests ciblés peuvent
  être exécutés localement ultérieurement.
- Conserver les modifications `n8n` et `sentry` du checkout opérateur :
  ne pas faire `git reset --hard` ou `git clean -fd`.
