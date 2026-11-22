# H17 — recette de migration du catalogue Backstage V2

> Arbitrage 22/11/2026 : **priorité 1**. Propriétaire des sources : `nabla-compose`. Consommateurs : `fastapi-sample` et `nabla-site-alban`. **CODED/TESTED Git ≠ ACCEPTED runtime**. Aucun changement de DNS, App ou secret dans cette recette.

## 1. Contrats source, avant le runtime

- `apps/sentry/compose.yml`, service `nginx`, porte `x-nabla.runtime: {provider: truenas-app, appId: sentry, containerService: nginx}`. Le conteneur `nginx` est partagé nominalement par plusieurs Apps TrueNAS ; sans `appId`, le rapprochement FastAPI retourne `binding_conflict` même avec un `entityRef` unique.
- Les projections `catalog/generated/entities.json` et `catalog/generated/identity-map.json` sont produites depuis les sources canonisées ; `catalog/services.json`, `catalog/service-topology.json`, Gatus/Homarr/AutoKuma sont encore nécessaires pendant le cutover.
- `composeProfiles` est lu par Sample depuis les entités V2 et doit produire `on_demand`, **pas `DOWN`**, pour un job volontairement arrêté. Les versions publiées de Sample et du Site possèdent déjà les lecteurs V2 ; il faut confirmer leur déploiement réel.

```bash
cd /mnt/cpool/compose/nabla-compose
python3 scripts/generate-service-topology.py --check
python3 scripts/generate-service-consumers.py --check
python3 scripts/generate-catalog-v2-artifacts.py --check
python3 -m pytest -q tests/test_catalog_v2_exports.py tests/test_catalog_v2_pilot.py
python3 scripts/quality/check-roadmap-portfolio.py --check
```

Ces contrôles sont hors-ligne : ils ne vérifient ni l'App Sentry ni l'API des sites.

## 2. Recette côté TrueNAS (lecture seule)

1. Relever les SHAs de `nabla-compose` et de l'App `fastapi-sample` effectivement lancée, la version de TrueNAS et l'heure locale.
2. Lire le dernier `catalogRevision` des artefacts V2 dans Git et la revision renvoyée par l'API FastAPI. La clé diagnostics doit venir du coffre et ne pas figurer dans les arguments shell, logs ou rapport public. Utiliser la procédure canonique : `sudo bash scripts/truenas/read-sample-observer.sh` (voir `--help` avant un nouveau chemin).
3. Vérifier **une seule** liaison de `sentry-edge` à l'App `sentry` et au service Compose `nginx`. Résultat exigé : `reconciliation=in_sync`, `observed.appId=sentry` et aucune entrée `matchingApps` multiple. Si la donnée est absente ou si Sample n'a pas le nouvel artefact, résultat `NOT_VERIFIED`, pas `DOWN`.
4. Observer un service sous profil `composeProfiles` en `on_demand`. Vérifier `entityRef` exact et `catalogRevision` identique pour Sample et le catalogue généré, sinon `MISMATCH`.
5. Vérifier que les objets d'inventaire opérateur correspondent au `operatorRevision` de la même génération, sans charger un objet V1 en repli silencieux.

## 3. Recette côté Site Alban

Lire la route existante `/api/homelab-catalog-v2` depuis un contexte autorisé : elle renvoie l'en-tête `X-Homelab-Catalog-Revision`. Un `401/403` anonyme est un **refus attendu** selon Access, non une panne du catalogue.

Comparer l'en-tête avec `catalogRevision` de Compose et Sample pour les **SHAs effectivement déployés**, pas avec la tête GitHub non publiée. Vérifier la carte propriétaire et l'absence de lecteurs V1 (garde Site #336). La validation de ce seul en-tête ne prouve pas la bonne réconciliation des conteneurs : conserver la preuve du point 2.

## 4. Retrait des exports legacy (gate destructive)

Ne supprimer `services.json`, `service-topology.json`, `homelab-services.json` ou `homelab-exposure-overrides.json` **qu'après** :

- inventaire des lecteurs exécutables (scripts opérateur, synchronisation Homarr/Gatus/AutoKuma, FastAPI, Site) et changement coordonné de chacun ;
- parité et tests négatifs automatisés sur les vues V2, absence de `binding_conflict` pour les workloads obligatoires ;
- sauvegarde des anciens exports, procédure de rétablissement et résultat `ACCEPTED` des trois consommateurs au runtime.

**Réception** : date, SHA Compose/Sample/Site, origine du test LAN et du test de Site, `catalogRevision`, nombre de conflits, `sentry-edge` et rollback. L'absence d'accès LAN depuis un agent distant impose `NOT_VERIFIED`. Aucun merge GitHub seul ne clôture H17.
