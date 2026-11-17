# POC — verrouillage OpenTofu via PostgreSQL privé

**Date : 17 novembre 2026. Phase : P1 / DESIGN, NOT_RUN, NOT_DEPLOYED.**
Ce document est une étude, pas une autorisation de migration ou une recette validée.
La décision active reste **Garage pour les états locaux**, **HCP Terraform Free
pour le pilote Entra**, dans une organisation dédiée.

## Portée exacte

Le backend OpenTofu `pg` sauvegarde le **tfstate dans PostgreSQL** (colonne
`data` de type texte) et utilise des **advisory locks PostgreSQL**, portés
par la session. Il ne fournit PAS un verrou externe indépendant que l'on
pourrait ajouter à un backend S3 Garage sans changer le stockage de l'état.
On ne migre donc aucun état existant pour réaliser ce POC.

La compatibilité de `use_lockfile` avec la version effectivement déployée
de Garage pourrait aussi être évaluée en environnement jetable : OpenTofu
S3 requiert une écriture conditionnelle `If-None-Match: *`. Ne jamais activer
ce mode sur le state de production sans preuve de concurrence entre deux
exécutants et de récupération des verrous.

## Déploiement sans exposition PostgreSQL

**L0 — preuve locale isolée (priorité)** : une instance PostgreSQL jetable sur
la workstation, accessible uniquement via socket Unix ou `127.0.0.1`.
Aucun port exposé sur `0.0.0.0`, aucun reverse proxy, aucune ouverture WAN.
Une base `opentofu_state_poc` et un compte technique non superutilisateur
sont créés explicitement après revue.

**L1 — intégration TrueNAS optionnelle** : conserver PostgreSQL en réseau
interne/loopback du NAS. Pour la workstation, ouvrir un tunnel SSH
**uniquement si le port loopback de l'hôte est vérifié** ; un conteneur Docker
en bridge n'est pas automatiquement accessible sur `127.0.0.1` de TrueNAS.
La commande suivante est une illustration, **pas une procédure à lancer
tant que le listener n'est pas vérifié** :

```bash
ssh -o ExitOnForwardFailure=yes -N \
  -L 127.0.0.1:55432:127.0.0.1:5432 <truenas-ssh-target>
```

Interdits : `5432`/WAN, NAT pfSense, publication Docker
`0.0.0.0:5432`, ingress Talos, tunnel Cloudflare public, runner GitHub
hébergé ayant accès au service. Aucun accès privilégié ou secret injecté
dans une PR.

## OpenTofu, authentification et PKI

Exemple minimal dans **un répertoire de laboratoire jetable distinct** :

```hcl
terraform {
  backend "pg" {}
}
```

La base doit exister avant `tofu init`. Fournir la connexion par variables
libpq ou `PG_CONN_STR`, **hors source versionnée**, jamais par mot de passe
dans `backend.tf`, `-backend-config` ou argv. Les variables acceptées incluent
`PG_SCHEMA_NAME`, `PG_SKIP_SCHEMA_CREATION`, `PG_TABLE_NAME`.

Avec un tunnel SSH, utiliser `PGHOSTADDR=127.0.0.1`, `PGPORT=55432`,
`PGHOST=<nom-présent-dans-le-certificat>`, `PGSSLMODE=verify-full` et
`PGSSLROOTCERT=<chemin-local-vers-CA>` lorsque PostgreSQL est configuré
pour TLS côté serveur. Vérifier le certificat effectivement présenté et
la négociation TLS ; SSH seul ne remplace pas l'identification PostgreSQL.
Sur socket Unix du POC purement local, le TLS n'est pas nécessaire :
permissions du socket, `pg_hba.conf` et authentification locale sont à
valider. Ne pas afficher les secrets dans les journaux.

Utiliser un schéma dédié et un rôle limité (pas de `SUPERUSER`,
`CREATEDB`, `CREATEROLE`). Attention : le backend `pg` utilise également
**une séquence dans le schéma `public`** pour les identifiants et verrous,
même si le state est dans un schéma personnalisé. Vérifier et limiter les
privilèges sur cette séquence au lieu de retirer à l'aveugle tous les droits
nécessaires. Pour `PG_SKIP_SCHEMA_CREATION=true`, créer d'abord le schéma
et les objets prérequis avec une migration administrative révisée.

Le state reste sensible au repos : ACL PostgreSQL, dataset ZFS chiffré,
backup `pg_dump` protégé, copie indépendante et restauration testée.
Ne pas stocker dans cette base le state qui déploie/restaure **la base
elle-même**, afin d'éviter une dépendance circulaire.

## Recette d'acceptation (à exécuter seulement dans un POC autorisé)

| Test | Preuve requise | État |
| --- | --- | --- |
| Réseau | `ss`, `pg_hba.conf`, ports Docker, pfSense, DNS/Cloudflare : aucun chemin WAN | NOT_RUN |
| Auth | rôle minimal, refus d'une identité non autorisée, TLS `verify-full` via SSH si utilisé | NOT_RUN |
| Concurrence | deux processus / clients indépendants sur le même workspace : un seul détenteur du verrou | NOT_RUN |
| Coupure | interruption du client, libération de l'advisory lock, absence de corruption | NOT_RUN |
| État | même serial, `tofu state list` cohérent, `tofu plan` sans changements imprévus | NOT_RUN |
| Sauvegarde | export chiffré puis restauration isolée vérifiée | NOT_RUN |
| Ressources | coût CPU/mémoire, disponibilité et procédure de reprise documentés | NOT_RUN |

Les verrous sont automatiquement relâchés lorsque la session PostgreSQL
est terminée ; `tofu force-unlock` n'est pas pris en charge. Employer des
clients OpenTofu >= 1.10 pour ce POC et ne pas mélanger d'anciennes
versions dans une même base, car le verrouillage de création des workspaces
a évolué dans 1.10.

## Critères avant un éventuel changement de backend

- Chiffrer et restaurer une sauvegarde des états existants, en environnement
  isolé, avant toute commande `init -migrate-state`.
- Garantir un seul écrivain pendant la migration, comparer le nombre de
  ressources et obtenir un `plan` sans changement inattendu.
- Garder Garage comme backend du bootstrap PostgreSQL et comme recours
  jusqu'à réception effective des verrous, droits et sauvegardes.
- **Ne pas publier PostgreSQL pour la CI** ; les runners GitHub restent
  isolés du LAN, et le state Entra reste sur HCP.

## Références

- [OpenTofu backend pg](https://opentofu.org/docs/language/settings/backends/pg/)
- [OpenTofu state locking](https://opentofu.org/docs/language/state/locking/)
- [OpenTofu backend s3](https://opentofu.org/docs/language/settings/backends/s3/)
- [PostgreSQL libpq TLS](https://www.postgresql.org/docs/current/libpq-ssl.html)
