# docker-socket-proxy : frontière d'accès à l'API Docker sur TrueNAS

Remplace l'app `docker-socket-proxy` du catalogue TrueNAS par une Custom App
versionnée ([`compose.yml`](compose.yml)).

## Pourquoi

Le 1/11, le proxy du catalogue s'est détaché du réseau `intranet` lors d'un
redéploiement. `pihole-dns-sync` ne joignait plus l'API Docker : 14 684
redémarrages et sièges de l'API Pi-hole épuisés. Le rattachement manuel
(`ensure-docker-socket-proxy-intranet.sh --apply`) ne survivait pas au
redéploiement suivant. Les réseaux déclarés dans Compose, eux, sont recréés à
chaque déploiement.

## Choix de sécurité

- **Lecture seule** : `POST=0`, pas d'`EXEC`, pas d'endpoint Swarm. `:ro` sur le
  socket ne protège rien à lui seul : seule la liste blanche compte.
- **Réseau dédié `docker-proxy`** (interne, sans sortie) partagé uniquement avec
  les consommateurs : `pihole-dns-sync`, `autoxpose`, `homarr`, `gatus` (sonde TCP)
  et l'audit manuel `watchtower`.
- **Risque résiduel** : `CONTAINERS=1` autorise `GET /containers/{id}/json`, qui
  renvoie les variables d'environnement de tous les conteneurs. Le réseau dédié
  limite cette lecture aux consommateurs ci-dessus au lieu des ~90 services
  d'`intranet`. Étape suivante possible : un proxy filtrant par chemin.
- **Transition** : le proxy reste aussi sur `intranet` (alias inchangé) tant
  que tous les consommateurs n'ont pas été redéployés. Retirer ensuite `intranet`
  de `compose.yml` (suivi dans la roadmap).

## Déploiement sur TrueNAS

Depuis le checkout canonique à jour :

1. Constat : `sudo bash scripts/truenas/deploy-docker-socket-proxy.sh --check`
2. Remplacement de l'app du catalogue (coupure brève de l'API Docker pour les
   consommateurs) :

   ```bash
   sudo NABLA_DOCKER_PROXY_REPLACE_APPROVED=yes \
     bash scripts/truenas/deploy-docker-socket-proxy.sh --apply --replace-catalog-app
   ```

3. Redéployer chaque consommateur pour qu'il rejoigne `docker-proxy`, puis
   `sudo bash scripts/truenas/verify-pihole-dns-sync.sh`.
4. Quand `--check` montre tous les consommateurs sur `docker-proxy` : retirer
   `intranet` du proxy dans `compose.yml` et redéployer.
