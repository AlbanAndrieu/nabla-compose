# TrueNAS : `app.query` bloqué par le verrou du conteneur `wazuh-indexer`

Date : 2026-11-04. Preuves : shell TrueNAS (lecture seule sauf l'action
corrective indiquée), `/var/log/middlewared.log`. Uptime 31 jours.

## Symptômes

- UI **Apps → Installed** : « No Applications Installed » alors que
  ~150 conteneurs tournent.
- `midclt call app.query` : `Call timeout`. Le journal du middleware montre
  `Exception while calling app.query` **toutes les 2 minutes** sur toute la
  fenêtre examinée (00:14 → 00:57 ; 1 611 occurrences dans le journal
  courant, la première le 17/01), terminées par
  `requests.exceptions.ReadTimeout` (60 s) dans
  `docker.api.container.inspect_container`.
- Conséquence : tout `midclt app.*` (déploiements, `app.redeploy`, scripts
  `deploy-*.sh`) échoue ou expire.

## Cause racine

`app.query` inspecte chaque conteneur de chaque projet. Une boucle
`timeout 5 docker inspect` sur `docker ps -aq` isole un seul conteneur
bloqué : `wazuh-indexer` (« Exited (0) 2 days ago »).

- containerd le voyait encore `RUNNING` (`ctr -n moby tasks ls`) ;
- son shim (`containerd-shim-runc-v2 -id 46ce1ac2aaab…`) attendait la fin
  de la JVM : processus `Zsl` dont un thread restait en état `R`,
  **SIGKILL en attente** (`SigPnd/ShdPnd 0x100`), 8 jours de temps CPU
  cumulé ;
- ce thread est coincé dans le noyau depuis l'OOM du 26/10 : il ne
  retourne jamais en espace utilisateur pour recevoir le signal. Le shim
  ne recevait donc jamais la sortie du processus et dockerd gardait le
  verrou du conteneur : chaque `docker inspect` attendait indéfiniment.

## Action corrective (01:00, 4/11)

```bash
sudo kill -9 <PID du shim containerd de wazuh-indexer>
```

Effet immédiat : la tâche containerd disparaît, `docker inspect
wazuh-indexer` répond (`exited`), `app.query` répond en **1 s** :
83 RUNNING, 13 STOPPED, 1 CRASHED (`wazuh`).

Seul le shim de ce conteneur déjà arrêté a été tué : aucun autre
conteneur, ni dockerd, ni containerd n'ont été redémarrés.

## Ce qui reste

- Le thread noyau de l'ancienne JVM consomme toujours ~1 cœur et garde
  son cgroup `/docker/46ce1ac2aaab…` : **seul un redémarrage de l'hôte le
  libère**. À planifier avec le [runbook de reboot](../homelab-reboot-runbook.md).
- Pression I/O élevée (PSI `io full` ~14-21 %) et ARC ZFS au minimum
  (1,9 Gio) : la mémoire disponible (~4 Gio) ne laisse pas de place au
  cache ZFS. Suivi dans la [roadmap P1](../roadmap.md).

## Détection

`scripts/truenas/diagnose-performance.sh` signale désormais :

- les zombies qui gardent des threads vivants (`Z` et `nlwp > 1`) ;
- les conteneurs dont `docker inspect` dépasse 5 s (verrou bloqué) ;
- le conteneur parent de chaque zombie et le pic mémoire cgroup
  (`memory.peak`) de chaque conteneur.

Toutes les sondes `docker inspect` du diagnostic sont bornées par
`timeout`.
