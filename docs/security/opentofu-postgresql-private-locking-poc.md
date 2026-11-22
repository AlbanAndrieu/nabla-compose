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

## Mandat pour un autre agent — recette exécutable

**Statut : P1 / ASSIGNED_TO_AGENT (aucun agent ni exécution lancé ici), NOT_RUN.**
Référence roadmap : [H16 dans le portefeuille](../roadmap-portfolio.md)
et [index actif](../roadmap.md). Une machine accessible dans les outils
du prochain agent est nécessaire. **Ne jamais interpréter une lecture du dépôt
comme une mesure du réseau privé.** L'agent doit vérifier sa capacité effective
et déclarer `BLOCKED_REMOTE_NO_WORKSTATION` s'il ne dispose pas de la workstation.

### Périmètre, protections impératives

- **Un seul environnement jetable et nouveau**, sans connexion aux neuf bases
  existantes ni aux schémas ou comptes PostgreSQL du homelab. Privilégier
  PostgreSQL local sur la workstation (socket Unix, ou port lié à
  `127.0.0.1` exclusivement) ; conteneur isolé seulement si Docker/Podman
  est effectivement disponible et la publication loopback est vérifiée.
- Aucun droit d'écriture sur Garage, HCP, TrueNAS, Talos, pfSense ou Cloudflare ;
  aucun `tofu init -migrate-state`, `force-unlock`, changement de backend
  réel ou `terraform apply` contre un provider cloud.
- Créer une base, un rôle SQL non superutilisateur et un schéma de test
  dédiés ; secrets éphémères dans un stockage protégé **hors Git**.
  Ne pas imprimer `PGPASSWORD`, `PG_CONN_STR` ni le contenu du state.
- **Bloquer le test** si `ss -lntp` ou la configuration du conteneur montre
  un listener PostgreSQL sur `0.0.0.0` ou `::`, si une route WAN/ingress
  est nécessaire, ou si l'identité SQL n'est pas strictement isolée.
  Le tunnel SSH et TLS `verify-full` sont un test L1 séparé et **facultatif** ;
  ne jamais ouvrir le réseau pour réussir ce POC.

### Séquence attendue pour la recette L0

1. Vérifier le poste et les versions par `tofu version`, `psql --version`,
   `ss -lntp` et `pg_isready` (socket/loopback). Exiger OpenTofu >= 1.10 ;
   consigner les versions exactes et le commit examiné, sans secrets.
2. Démarrer PostgreSQL jetable, puis créer le rôle et la base dédiés.
   Vérifier les accès négatifs : rôle non autorisé refusé ; rôle POC sans
   `SUPERUSER`, `CREATEROLE` ni `CREATEDB`. Autoriser uniquement les
   objets nécessaires, y compris la séquence backend dans `public`.
3. Dans un répertoire temporaire neuf, créer ce **seul** module OpenTofu
   (ressource intégrée, sans fournisseur cloud, aucun état existant) :

   ```hcl
   terraform {
     required_version = ">= 1.10.0"
     backend "pg" {}
   }

   resource "terraform_data" "lock_probe" {
     input = "isolated-postgres-lock-poc"
     provisioner "local-exec" {
       command = "sleep 30"
     }
   }
   ```

   Configurer la connexion par les variables `PG*`/libpq **hors processus
   journalisé** et utiliser deux répertoires `TF_DATA_DIR` indépendants
   avec le **même workspace et backend PostgreSQL jetable**.
   Initialiser par `tofu init -input=false` dans les deux clients.
4. Démarrer `tofu apply -auto-approve -lock-timeout=0s` depuis le client A
   ; pendant l'attente du `local-exec`, lancer
   `tofu plan -input=false -lock-timeout=0s` depuis le client B.
   Critère : A possède le verrou et B **échoue** sur l'acquisition (pas
   de second écrivain). Échantillonner `pg_locks` en lecture seule ;
   conserver code de sortie, temps et noms de tests uniquement.
   **Ne pas inventer un PASS si les opérations ne se chevauchent pas.**
5. Après la fin de A, relancer le plan B : le verrou doit être libre et
   le plan **sans changement**. Refaire une exécution avec interruption
   contrôlée du client A, démontrer la libération du verrou à la fermeture
   de la session puis un plan B valide. Ne pas interrompre un serveur SQL
   partagé ; vérifier `pg_locks` et les données après le test.
6. Sauvegarder **uniquement** la base jetable, restaurer dans une seconde
   base jetable et vérifier état/workspace/serial, privilèges et séparation
   des accès. Comparer sans publier la donnée du state. Supprimer les
   ressources éphémères seulement après vérification du rollback local.

### Preuves et décision de sortie

| ID | Exigence de réception | État initial |
| --- | --- | --- |
| PG-L01 | Aucun listener externe, aucune règle NAT/Cloudflare/ingress créée | NOT_RUN |
| PG-L02 | Rôle limité, authentification négative ; `public` maîtrisé | NOT_RUN |
| PG-L03 | Deux clients concurrents : second refusé et code retour non nul | NOT_RUN |
| PG-L04 | Après interruption, advisory lock libéré et state non corrompu | NOT_RUN |
| PG-L05 | Après libération, `plan` sans changement inattendu | NOT_RUN |
| PG-L06 | Backup/restore jetable comparé, données jamais publiées | NOT_RUN |
| PG-L07 | CPU/RAM/latence mesurés ; procédure de destruction/rollback | NOT_RUN |

Livrer un rapport `docs/runbooks/YYYY-MM-DD-postgres-lock-poc-acceptance.md`
en **PR Draft** (branche nouvelle ou PR de travail compatible) : date/heure,
SHA de chaque outil/source, lieu d'observation, résultat
`PASS/FAIL/BLOCKED/NOT_RUN` pour chaque ID, logs **expurgés**,
écarts et recommandation : `KEEP_GARAGE` par défaut,
`RETEST` ou `PROPOSE_MIGRATION` **sans aucune migration automatique**.
Déclarer séparément les vérifications sur poste et les tests L1 TrueNAS,
s'ils ont été explicitement autorisés.

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
