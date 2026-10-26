# TrueNAS — pression mémoire, CPU et I/O, conteneurs, ZFS (26 octobre 2026)

## Constat

TrueNAS répond de nouveau après **l'arrêt de Netdata**.
C'est une corrélation, **pas une preuve** que Netdata était l'unique
cause du gel. Le diagnostic mesure la pression hôte indépendamment
des consommations des conteneurs. Ne pas redémarrer Netdata pour la
première collecte.

## 1. Baseline hôte — même si Docker ne répond pas

```bash
cd /mnt/cpool/compose/nabla-compose
python3 scripts/truenas/diagnose-truenas-pressure.py \
  --check --observe-seconds 15 --skip-docker
```

Lecture seule de `/proc/meminfo` (notamment MemAvailable), PSI
`/proc/pressure/{cpu,memory,io}`, `/proc/vmstat` (deltas OOM,
swap in/out, major faults, direct reclaim) et
`/proc/spl/kstat/zfs/arcstats`. **ARC élevé** n'est pas, seul,
une preuve de manque de mémoire : le cache peut se réduire.

## 2. Classer les services Docker

Lorsque TrueNAS répond :

```bash
cd /mnt/cpool/compose/nabla-compose
sudo python3 scripts/truenas/diagnose-truenas-pressure.py \
  --check --observe-seconds 20 --docker-timeout 8 --top 20 \
  --report-dir /mnt/cpool/var/nabla/truenas-pressure
```

Le Python système ne nécessite aucune dépendance tierce.
Un seul `docker stats --no-stream` avec timeout de 8 secondes ;
en cas d'échec, la pression hôte reste visible et Docker est
`UNVERIFIED`. Rapport JSON privé créé en mode 0600 dans
un dossier 0700, sans environnements, commandes ni logs.

Le top mémoire et CPU donne des candidats à investiguer :
`high_cpu_snapshot`, `near_container_memory_limit`,
`large_working_set_not_host_pressure_proof`.
Le pourcentage de mémoire Docker est relatif à la limite du
**conteneur**, non à la RAM totale TrueNAS ; un CPU% peut
dépasser 100 % sur plusieurs cœurs. Les conteneurs arrêtés,
notamment Netdata, sont absents de la collecte : aucune
rétro-attribution de sa consommation avant arrêt n'est possible.

## 3. Ressources non-Docker : VMs Talos, ZFS, processus

```bash
sudo bash scripts/truenas/diagnose-resource-usage.sh --host
ps -eo pid,comm,rss,%cpu --sort=-rss | head -n 25
timeout 15 zpool iostat -v 1 2
```

Ces commandes sont non mutantes. `zpool iostat` renseigne
l'activité I/O, pas la latence de chaque App. Les VMs
`qemu-system-*` ne sont pas comptées comme conteneurs Docker.

Pour corréler des OOM historiques :

```bash
sudo journalctl -k -b --since "4 hours ago" --no-pager \
  -g "oom-kill|Out of memory|Killed process|blocked for more than" \
  -n 50
```

## 4. Interprétation

| État | Interprétation |
| --- | --- |
| `CRITICAL_PRESSURE` | OOM nouveau ou manque RAM combiné à PSI full |
| `PRESSURE_SIGNAL` | PSI CPU/mémoire/I/O, swap ou reclaim actif ; triage requis |
| `NO_STRONG_CURRENT_SIGNAL` | Aucun fort signal pendant l'échantillonnage, pas une preuve historique |
| `UNVERIFIED` | PSI ou preuve système insuffisants |

Codes de sortie : 0 = aucun signal fort, 1 = pression, 2 = non vérifié.
Une alerte ressource ne signifie pas automatiquement App DOWN.
Si TrueNAS recommence à geler, utiliser **`--skip-docker` en premier**.

## 5. Tests

```bash
python3 -m pytest -q tests/test_truenas_pressure.py
```

**15 tests hermétiques PASS** dans l'environnement d'agent.
Aucune preuve runtime TrueNAS collectée depuis l'agent. Ne pas
modifier les limites ARC, Docker ou les services sur la seule
base de ce relevé.
