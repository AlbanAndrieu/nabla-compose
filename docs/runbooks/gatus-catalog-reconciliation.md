# Gatus → catalogue canonique : rapprochement sans mutation (2026-10-17)

## Sources et limites

- `catalog/homelab-services.json` : intentions de service historiques ; **pas** un état Docker.
- `apps/gatus/config/config.yml` : sondes déclarées, `nabla_monitor_id` et `nabla_service_id`.
- `/api/v1/endpoints/statuses` : preuves de sonde datées, **pas** preuve suffisante d'arrêt applicatif.
- `x-nabla` / `catalog/service-topology.json` : source déclarative pour la migration v2.
- TrueNAS Docker / Prometheus : preuves runtime indépendantes à corréler manuellement.

## Exécution read-only

Depuis le checkout `nabla-compose` :

```bash
python3 scripts/truenas/reconcile-gatus-catalog.py \
  --output /tmp/gatus-catalog-declared.json

# Snapshot local facultatif. Ne pas afficher ni committer le JSON brut :
# il peut contenir des URLs, chemins et informations sensibles.
umask 077
curl -fsS --max-time 10 http://127.0.0.1:8085/api/v1/endpoints/statuses \
  -o /tmp/gatus-statuses-private.json
python3 scripts/truenas/reconcile-gatus-catalog.py \
  --statuses /tmp/gatus-statuses-private.json \
  --output /tmp/gatus-catalog-runtime-redacted.json
rm -f /tmp/gatus-statuses-private.json
```

Le rapport dérivé n'imprime ni URLs de sondes, ni en-têtes, ni identifiants de connexion. Il indique `probe_failed_unconfirmed` ou `investigate_probe_not_service_down` plutôt que `DOWN`. Un moniteur sans `nabla_service_id` peut représenter une infrastructure légitime : il ne doit pas être créé comme service par déduction.

## Ordre d'investigation et migration

1. **Home Assistant** : Docker healthy mais sonde négative ; comparer HTTP/TCP, code attendu, authentification, résolution réseau et port effectif avant toute correction de cible.
2. **OpenSearch, OpenSearch Security et PostgreSQL** : distinguer état du service, conteneur exporter, job Prometheus, route `/metrics` et statut Gatus. Ne pas dégrader une base healthy parce qu'un exporter est absent.
3. **Scanopy, SonarQube, NetBox, Graylog, Plumber, NPMplus** : vérifier `expectedRunning` et environnement avant de classer l'absence d'un conteneur ; Plumber peut être hébergé sur la workstation.
4. **Mapping v2** : enregistrer identifiant stable, unité, criticité opérationnelle et métier, environnement, cible et type de sonde, auth requise (sans secret), dépendances et `monitoringPolicy`. Garder les relations v1 jusqu'à la parité des consommateurs.
5. **Acceptation** : zéro ID de moniteur dupliqué, chaque service critique attendu dispose d'une preuve runtime et d'une sonde pertinente ; justifier les moniteurs sans service associé, vérifier stabilité Gatus et écarts avant migration.

**Interdits** : ne pas relancer un service sur un simple échec Gatus, ne pas désactiver une sonde pour améliorer artificiellement le score, ne pas publier les URLs privées ni modifier les secrets. Les 85 sondes et le ratio 60/25 sont un snapshot fourni, pas une mesure en temps réel.

## Réconciliation à deux référentiels (PR #257)

Le rapport inclut désormais `mapping_counts`, `mapping_source`, `topology_match` et `unresolved_monitor_ids`. Un composant présent dans `catalog/service-topology.json` est reconnu même s'il est absent du catalogue historique ; aucun service n'est ajouté automatiquement. Les moniteurs sans `nabla_service_id` restent `infrastructure_unmapped` et doivent être examinés, non assimilés à des pannes.

Après synchronisation de la branche :

```bash
python3 scripts/truenas/reconcile-gatus-catalog.py --output /tmp/gatus-catalog-declared.json
jq '{declared_monitors, mapping_counts, classification_counts, unresolved_monitor_ids, duplicate_monitor_ids}' /tmp/gatus-catalog-declared.json
jq '[.monitors[] | select(.mapping_source == "unresolved") | {monitor_id, service_id, probe_type}]' /tmp/gatus-catalog-declared.json
```

Les anciens chiffres de `needs_service_mapping` ne sont plus directement comparables : le rapprochement utilise désormais les composants de la topologie canonique. Ne pas modifier les identités Gatus avant d'avoir examiné la nouvelle liste `unresolved_monitor_ids`.
