# Observabilité TrueNAS — diagnostic et reprise contrôlée

**Fiche spécialisée (25 octobre 2026).** Le runbook principal reste [l'acceptation runtime](homelab-runtime-acceptance.md).
Historique intégral et preuves du 24 octobre :
[archive](../archive/2026-10-24/2026-10-24-prometheus-pyroscope-dns-dot-recovery.md).
Les procédures mutantes sont **manuelles**, jamais exécutées par un
diagnostic. Le détail DNS appartient au
[runbook pfSense](2026-10-24-pfsense-unbound-pfblocker-whatsapp.md).

## État de référence prouvé

| Composant | Dernière observation fournie | Interprétation |
| --- | --- | --- |
| Prometheus | Docker running, HTTP `/-/ready` 200 ; 15/15 règles lisibles | Service rétabli |
| Pyroscope | Docker running, HTTP `/metrics` 200 | Réinitialisation terminée, conserver le backup |
| Akvorado inlet/outlet | Deux scrapes 1/1, métriques présentes | Scrapes UP ; flux SQL non attestés |
| Gatus, Redis exporter, CrowdSec, pfSense exporter | Scrapes UP | Vérifier fraîcheur à chaque nouvel incident |
| FastAPI staging `:8091/metrics` | HTTP 401 | Authentification manquante, **pas** une panne HTTP générale |
| PostgreSQL exporter `:9187` | TCP refusé, conteneur et secret absents | Exporter à provisionner, pas PostgreSQL lui-même |
| FastAPI Cloud `/api/health-board` | HTTP 403 depuis le vérificateur | Snapshot non accessible ; Akvorado cloud inconnu |

Ces constats sont datés. Ne pas les présenter comme états live actuels.

## Diagnostic unique, lecture seule

Sur **TrueNAS**, dans le checkout Compose :

```bash
python3 scripts/prometheus/diagnose-failed-scrapes.py --check
sudo bash scripts/truenas/diagnose-observability-post-repair.sh --check
sudo bash scripts/truenas/diagnose-postgres-exporter.sh
```

Lancer le point d'entrée consolidé décrit dans
[commandes opérateur spécialisées](2026-10-25-homelab-operator-diagnostics.md)
pour agréger la classification des états. Ne pas afficher de DSN, clés,
logs bruts, headers Authorization ni chemins privés. Éviter les
scrapes manuels supplémentaires vers pfSense.

### Prometheus / Pyroscope

Si Prometheus redémarre :
`sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check`
permet de compter les règles illisibles. **Ne pas** réexécuter `--apply`
si la sortie est `unreadable=0`. Un `restart_count` ancien ou un log
d'échec historique n'est pas un incident actif.

Pyroscope possède une sauvegarde de l'ancien état :
`/mnt/cpool/pyroscope/data/.metastore-backup-20261024T210505Z`.
Ne pas exécuter un second reset automatique. Vérifier `running` et
HTTP 200 avant toute décision de suppression manuelle de la sauvegarde.
Aucune suppression TSDB Prometheus, WAL ou backup Pyroscope n'est
justifiée par les dernières preuves.

### Exporter PostgreSQL

Le [Compose](../../apps/postgres/compose.yml) utilise un secret
`/mnt/cpool/secrets/runtime/postgres-exporter/.env.secrets`
avec `env_file.format: raw`, `required: true` et listener
`172.17.0.24:9187`.

- **Avant le déploiement** : vérifier Docker Compose ≥ 2.30, créer un
  rôle `pg_monitor` non superuser et un secret `DATA_SOURCE_NAME`
  dédié via le flux Vaultwarden → `install-runtime-secret.sh`.
- **Après déploiement autorisé** : vérifier HTTP `/metrics` et
  `up{job="postgres_exporter"}=1` **et** `pg_up=1`.
- Ne jamais réutiliser les secrets PostgreSQL applicatifs ou
  imprimer le DSN. Absence de secret = blocage du déploiement.

### FastAPI /metrics et cloud

**Preuve opérateur du 26 octobre :** `METRICS_SCRAPE_KEY` a été ajouté
à `/mnt/cpool/secrets/runtime/sample/.env.secrets`. Le diagnostic
distant fonctionne via SSH port `9922` (OpenSSH local), et confirme
`GET /metrics` **HTTP 401 sans credentials**. L'application refuse
l'anonyme ; son conteneur n'a pas encore été attesté avec la nouvelle clé.

Le job Prometheus `fastapi_sample` utilise désormais, **dans la PR #280**,
`authorization.type=Bearer` et
`authorization.credentials_file=/run/secrets/fastapi-sample-metrics.key`.
Un bind mount en lecture seule prépare ce fichier côté conteneur.
**Le déploiement et l'installation du secret restent à faire.**

La [procédure dédiée](fastapi-prometheus-scrape-secret-20261026.md)
décrit la vérification, l'installation explicite du fichier privé
(`root:568`, `0640`), la validation de l'environnement FastAPI, le
redéploiement contrôlé et la preuve `fastapi_sample=scrape_up`.

Avant de modifier Prometheus, exécuter sur TrueNAS :

```bash
sudo python3 scripts/truenas/reconcile-fastapi-metrics-credential.py --check
```

Ce contrôle **n'écrit rien** et ne révèle pas la clé. Un résultat
`credential_ready` atteste la correspondance des **deux fichiers**,
pas la configuration effective des conteneurs. Ne pas mettre le secret
dans Git, ne pas réutiliser `DIAGNOSTICS_ACCESS_KEY`, ne pas rendre
`/metrics` public. Pour FastAPI Cloud, utiliser une clé distincte
uniquement si un scraper Cloud est explicitement prévu.

Un HTTP 403 sur le snapshot FastAPI Cloud est un problème d'autorisation
distinct. Consulter le
[runbook FastAPI 403](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/runbooks/fastapi-cloud-owner-access-403.md).
Ne pas désactiver Cloudflare Access ou les contrôles de source IP.

## DNS-over-TLS : projet, non appliqué

pfSense/Unbound `172.17.0.1` reste l'autorité locale de
`int.albandrieu.com`. Le plan est de chiffrer progressivement les
requêtes **sortantes** d'Unbound vers deux résolveurs Quad9 via
TCP/853 avec validation de certificat. Le DNS client → pfSense
est distinct et peut rester UDP/TCP 53 sur le LAN.
Aucun DoT ne doit être considéré déployé sans preuve réseau côté pfSense.
Sauvegarder avant modification et ne pas surcharger le Netgate 1100.

## Retrait d'incident

Les tests locaux valident le code, pas les services déployés.
Un état docker `running` seul ne prouve ni la disponibilité HTTP,
ni la fonction métier. Documenter séparément : source d'observation,
horodatage, URL/path testé, résultat et décision de rollback.
