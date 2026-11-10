# Politique de rétention des snapshots ZFS (TrueNAS)

Décidée le 3 novembre 2026. Source versionnée :
[`config/truenas/snapshot-tasks.json`](../config/truenas/snapshot-tasks.json),
appliquée par [`reconcile-snapshot-tasks.sh`](../scripts/truenas/reconcile-snapshot-tasks.sh).

## Pourquoi

Au 1er novembre, `cpool` portait environ 12 000 snapshots. Les snapshots de
`bitcoind` retenaient à eux seuls 104 Go de blocs déjà supprimés par le nœud.
Aucune tâche n'était versionnée : impossible de savoir ce qui était protégé, ni
combien cela coûtait.

## Classes

Chaque dataset d'une classe reçoit une tâche TrueNAS par fréquence. Les tâches
sont récursives, ne créent pas de snapshot vide (`allow_empty: false`) et ont
toutes une durée de vie.

| Classe | Fréquences | Datasets (extrait) | Motif |
| --- | --- | --- | --- |
| `critical` | 1×/h gardé 48 h, 1×/j gardé 30 j | `vaultwarden`, `secrets`, `2fauth` | Secrets : RPO court, plus une copie hors site chiffrée (à faire) |
| `databases` | 1×/h gardé 24 h, 1×/j gardé 7 j | `clickhouse`, `mongo`, `neo4j`, `opensearch`, `wazuh`… | Cohérence « crash » ; les dumps applicatifs restent la restauration de référence |
| `backup-targets` | 1×/j gardé 14 j, 1×/sem gardé 8 sem | `backup`, `garage` | Un client NFS/S3 peut effacer son propre dépôt ; seul le snapshot côté TrueNAS le protège |
| `app-state` | 1×/j gardé 30 j, 1×/sem gardé 12 sem | `traefik`, `pihole`, `grafana`, `homarr`, `keycloak`… | Configuration et petit état applicatif |
| `user-data` | 1×/j gardé 30 j, 1×/mois gardé 12 mois | `bababou` | Documents et médias ; ajouter photo/musique/www après l'audit |
| `recreatable` | 1×/mois gardé 3 mois, 1×/an gardé 1 an | `nexus3` | Données reconstructibles depuis l'amont (artefacts proxifiés) : points rares pour ne pas retenir les blobs purgés (10/11). Les anciennes tâches horaires/quotidiennes de `cpool/nexus3` ne sont **pas** supprimées par la réconciliation : `midclt call pool.snapshottask.query '[["dataset","=","cpool/nexus3"]]'` puis `pool.snapshottask.delete <id>` |
| `resync-shortcut` | 1×/mois gardé 1 mois | `bitcoind` | Nœud élagué : un seul point évite plusieurs jours de synchronisation initiale en ne retenant qu'un mois de blocs tournants (des snapshots fréquents en retenaient plus de 100 Go) |

Le prune Restic de la workstation doit rester hebdomadaire : il réécrit des
packs et gonfle les snapshots de `cpool/backup`.

## Datasets sans snapshot

Données reproductibles ou à forte rotation (`bitcoind` est passé en `resync-shortcut` le 10/11) :
`ix-apps/docker` (images et cache de build), modèles (`ollama`, `model`),
séries temporelles et journaux (`prometheus`, `mimir`, `loki`, `tempo`,
`pyroscope`, `influxdb`, `logs`), flux réseau (`akvorado`, `ntopng`,
`suricata`), files et cache (`kafka`, `redis`), `compose` (checkout Git),
`languagetool`, `alloy`. Le cache Netdata sera ajouté quand l'audit aura donné
le nom exact de son dataset.

Le plan signale toute tâche existante qui couvre l'un de ces datasets, y compris
via une tâche récursive sur un parent. La correction se fait à la main
(exclusion ou suppression de la tâche après relecture).

## Procédure

Tout se lance sur TrueNAS, depuis le checkout canonique.

1. Inventaire en lecture seule : `just zfs-retention-audit`, puis le nombre de
   snapshots par dataset :
   `sudo zfs list -H -t snapshot -o name | cut -d@ -f1 | sort | uniq -c | sort -rn | head -30`.
2. Plan : `just zfs-snapshot-tasks-plan`. Relire les lignes `absent` (dataset
   inexistant : corriger la politique), `drift` et `covers`.
3. Création des tâches manquantes : `just zfs-snapshot-tasks-apply`. Rien n'est
   modifié ni supprimé.
4. Tâches qui couvrent un dataset sans snapshot : les corriger dans l'interface
   TrueNAS, puis relancer le plan jusqu'à `covering-no-snapshot=0`.
5. Purge de l'existant, dataset par dataset, jamais globalement : simuler avec
   `sudo zfs destroy -nv <dataset>@<premier>%<dernier>`, faire valider, puis
   exécuter sans `-n`.

## Reste à faire

- Alertes Prometheus sur le nombre de snapshots, le ratio `usedbysnapshots` par
  dataset et l'occupation du pool.
- Copie hors site (étape 4 de la roadmap) avec une restauration de test.
