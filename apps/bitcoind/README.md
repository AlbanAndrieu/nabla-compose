# bitcoind : nœud Bitcoin Core géré par le dépôt

Remplace l'app `bitcoind` du catalogue TrueNAS par une Custom App versionnée
([`compose.yml`](compose.yml), [`bitcoin.conf`](bitcoin.conf)).

## Choix de sécurité

- **Aucun port publié.** Pas de P2P entrant (`listen=0`, pas de redirection
  pfSense) ; le RPC n'écoute que sur `127.0.0.1` dans le conteneur.
- **Pas de secret.** `bitcoin-cli` s'authentifie avec le cookie du datadir ; ni
  `rpcpassword` ni `rpcauth`. Si un client externe a un jour besoin du RPC,
  ajouter un `rpcauth` rendu depuis Vaultwarden et un réseau dédié.
- **Pas de wallet** (`disablewallet=1`) : le dataset ne contient rien à sauvegarder.
- **Conteneur restreint** : utilisateur `568:568`, système de fichiers en lecture
  seule, `cap_drop: ALL`, `no-new-privileges`, `init: true`, `mem_limit: 1536m`,
  `cpus: 1.0`. Le point d'entrée de l'image (root, `gosu`, `chown`) est contourné.
- **Image** `bitcoin/bitcoin:31.1` : construite par
  [willcl-ark/bitcoin-core-docker](https://github.com/willcl-ark/bitcoin-core-docker),
  binaires vérifiés contre les signatures de release. Image non officielle :
  Renovate suit les versions ; épingler le digest lors de la mise à jour suivante.

## Données et snapshots

- Données : `/mnt/cpool/bitcoind/node` (dataset `cpool/bitcoind`, preset Apps).
- Nœud élagué (`prune=25000`, ~25 Go de blocs), resynchronisé depuis le réseau.
- **Aucun snapshot ZFS** : `cpool/bitcoind` figure dans `noSnapshot` de la
  [politique de rétention](../../docs/truenas-zfs-snapshot-policy.md). Un nœud
  élagué réécrit sans cesse ses fichiers de blocs ; les snapshots retenaient
  104 Go le 1/11.

## Migration depuis l'app du catalogue

Sur TrueNAS, depuis le checkout canonique à jour :

1. Constat, sans modification :

   ```bash
   sudo bash scripts/truenas/deploy-bitcoind.sh --check
   ```

   Le script affiche le type de l'app existante (catalogue ou Custom App) et les
   datasets contenant `bitcoin`, avec leur espace et leur nombre de snapshots.

2. Remplacement : supprime l'app du catalogue et ses ix-volumes, crée
   `cpool/bitcoind`, prépare `node/` pour l'utilisateur 568 et crée la Custom App :

   ```bash
   sudo NABLA_BITCOIND_REPLACE_APPROVED=yes \
     bash scripts/truenas/deploy-bitcoind.sh --apply --replace-catalog-app
   ```

3. Nettoyage des anciennes données, après relecture de la sortie du `--check` :
   - ancien dataset en chemin hôte (autre que `cpool/bitcoind/node`) :
     `sudo zfs destroy -nrv <dataset>`, puis sans `-n` ;
   - snapshots restants de `cpool/bitcoind` :
     `sudo zfs destroy -nv cpool/bitcoind@%`, puis sans `-n`.

4. Tâches de snapshot : `just zfs-snapshot-tasks-plan` ne doit plus signaler de
   tâche couvrant `cpool/bitcoind`.

5. Synchronisation initiale : plusieurs heures. Suivi :
   `sudo docker logs --tail 50 -f bitcoind`. Le healthcheck passe à `healthy`
   quand le RPC répond (période de grâce de 30 minutes).

Retour arrière : supprimer la Custom App (`app.delete bitcoind`). Aucune donnée
à restaurer.
