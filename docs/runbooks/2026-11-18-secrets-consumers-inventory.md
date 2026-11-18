# Consommateurs Doco-CD et `external_secrets` — inventaire (18/11/2026)

Inventaire **statique et sans valeur** (checkout `09d6743b`, mode `offline`)
pour le point P0.7 de [la feuille de route des secrets](../secrets-migration-roadmap.md) :
retirer l'adaptateur `bitwarden-api` exige d'abord la liste complète de ses
consommateurs. Aucun identifiant d'item Vaultwarden n'est recopié ici.

## Chaîne en service

```text
Doco-CD TrueNAS (docker-compose-truenas.yml, SECRET_PROVIDER=webhook)
  -> secret-store.yml (stores bitwarden-login / bitwarden-fields)
  -> bitwarden-api :8087 (apps/vaultwarden/compose.yml)
  -> Vaultwarden
```

## Fichiers consommateurs

| Fichier | Rôle |
| --- | --- |
| `.doco-cd.yaml` | Déclare les trois `external_secrets` : `N8N_API_KEY`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (store `bitwarden-login`). |
| `secret-store.yml` | Définit les stores webhook `bitwarden-login` et `bitwarden-fields`, qui interrogent `bitwarden-api` sur le port 8087. |
| `docker-compose-truenas.yml` | Instance Doco-CD active : `SECRET_PROVIDER: webhook`, monte `secret-store.yml` ; le `poll-config` ne déploie que `vaultwarden` et `garage`. |
| `apps/vaultwarden/compose.yml` | Service `bitwarden-api` lui-même, seul fournisseur des stores ; marqué « ne pas ajouter de consommateur ». |
| `apps/vaultwarden/catalog-info.yaml` | Entité catalogue de l'adaptateur (`vaultwarden-rest-api`). |
| `config/secrets/manifest.json` | Trois secrets d'amorçage `host-protected` de l'app `bitwarden-api` (identifiants `bw` de l'adaptateur). |
| `bootstrap/compose.yaml` | Ancienne définition de secours Doco-CD avec `SECRET_PROVIDER: 1password` et jeton fichier ; jamais lancée par `cron.sh`. |
| `config/secrets/debt-baseline.json` | Gèle les deux références secrètes de `bootstrap/compose.yaml` (jeton 1Password, `SECRET_PROVIDER_CONNECT_TOKEN`). |
| `docker-compose.yml`, `docker-compose-albandrieu.yml` | Doco-CD poste de travail désactivé (profil `doco-cd-legacy-workstation`, décision du 06/11) ; `bitwarden-api` y est commenté. |
| `scripts/cron.sh` | Synchronise le checkout et attribue `vaultwarden garage` à Doco-CD (`NABLA_CRON_DOCO_CD_PROJECTS`) ; ne démarre jamais Doco-CD. |
| `scripts/truenas/check-homelab-services.sh` | Avertit si le conteneur `bitwarden-api` n'est pas `running` (contrat : `tests/test_homelab_services_runtime_check_contract.py`). |
| `config/monitoring/gatus-endpoints.yml` | Sonde Gatus `doco-cd`. |
| `config/truenas/snapshot-tasks.json` | Snapshots du dataset `cpool/dococd`. |
| `apps/homarr/generated/apps.json` | Tuile Homarr générée vers Doco-CD ; aucun secret. |

## Constat

- Aucun des trois `external_secrets` n'est interpolé par les projets que
  Doco-CD déploie réellement : `apps/vaultwarden/compose.yml` et
  `apps/garage/compose.yml` ne référencent ni `N8N_API_KEY`, ni
  `${POSTGRES_USER}`, ni `${POSTGRES_PASSWORD}`.
- `N8N_API_KEY` n'est consommé que par `apps/n8n/compose.yml`
  (`N8N_INTERNAL_API_KEY`), hors périmètre Doco-CD ; le manifeste le déclare
  déjà pour la matérialisation canonique.
- Le `poll-config` déclare ses déploiements en ligne : vérifier dans la
  documentation Doco-CD 0.85.1 si le `.doco-cd.yaml` racine est encore lu.
  Dans les deux cas, aucun consommateur effectif n'apparaît dans le dépôt.

Conclusion statique : les `external_secrets` sont orphelins et l'adaptateur
devient candidat au retrait. Preuve runtime `NOT_RUN` : un appelant hors dépôt
de `172.17.0.24:8087` reste possible.

## Retrait proposé (non exécuté)

1. Poste de travail : lire les journaux d'accès de `bitwarden-api` sur au moins
   un cycle de poll (3 600 s) et confirmer l'absence d'autre appelant.
2. Retirer `external_secrets` de `.doco-cd.yaml`, puis `SECRET_PROVIDER` et le
   montage `secret-store.yml` de `docker-compose-truenas.yml`.
3. Retirer le service `bitwarden-api`, son entité catalogue, ses entrées du
   manifeste, l'avertissement de `check-homelab-services.sh` et les tests
   associés ; régénérer le catalogue.
4. Supprimer la définition 1Password de `bootstrap/compose.yaml` et ses deux
   entrées de `debt-baseline.json`.
