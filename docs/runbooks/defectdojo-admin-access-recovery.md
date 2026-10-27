# DefectDojo — retrouver ou réinitialiser le compte administrateur

**Contexte Nabla / TrueNAS** : `https://defectdojo.int.albandrieu.com/`,
Custom App `defectdojo`, conteneur Django `defectdojo-uwsgi`,
base PostgreSQL partagée. **Ne pas recréer la base ni relancer l'initializer.**

## Reprise rapide du compte existant `admin` — 27 octobre 2026

**Décision : réinitialiser le mot de passe Django du compte `admin`, sans
supprimer le compte ni la base PostgreSQL.** Le compte `admin` a été
observé dans Django le 23 octobre ; le nouveau mot de passe placé dans
`.env.secrets` n'a pas modifié son hash. DefectDojo n'a pas été utilisé
manuellement, mais des findings ou intégrations éventuels n'ont pas
été exclus. Supprimer la base impose de refaire les migrations et
n'accélère pas la réparation d'un simple mot de passe.

Depuis **TrueNAS**, une seule intervention sur le compte après le
contrôle de disponibilité :

```bash
# 1. Lecture seule : une réinitialisation est impossible si uWSGI est absent.
sudo docker inspect defectdojo-uwsgi --format '{{.State.Status}}'

# 2. Uniquement si le résultat est « running », dans un terminal privé.
# Django demande le mot de passe de façon interactive, sans argument secret.
sudo docker exec -it defectdojo-uwsgi python manage.py changepassword admin
```

Si uWSGI est absent, en `restarting` ou bloqué après l'initializer,
**ne pas supprimer `admin`, ne pas recréer `defectdojo` et ne pas
redéployer en boucle**. Exécuter uniquement :

```bash
sudo python3 scripts/truenas/diagnose-defectdojo-deploying.py --check --include-log-classes
sudo python3 scripts/truenas/diagnose-defectdojo-postgres-waits.py --check
```

Le mot de passe défini par `changepassword` est opérationnel en base
sans redémarrage. **Mettre à jour ensuite l'entrée Vaultwarden existante
`TrueNAS/nabla/prod/defectdojo`** (`login.username=admin`,
`login.password`), puis vérifier la connexion dans une session privée.
Le dernier contrôle de parité indiquait
`DD_ADMIN_USER=DRIFT` et `DD_ADMIN_PASSWORD=UNVERIFIED` :
le compte `nabla` déclaré par le bootstrap ne doit pas être supposé
exister dans Django. Le helper automatisé
`reconcile-defectdojo-admin-password.py` refuse délibérément cette
dérive ; le changement interactif ci-dessus est donc la voie courte.
Ne jamais afficher les secrets ou recopier le mot de passe dans Git.

**Gate DONE :** uWSGI répond, `changepassword admin` réussit,
connexion authentifiée à l'UI réussie et secret Vaultwarden mis à jour.
La disponibilité runtime et la connexion réelle ne sont
**pas vérifiées par cette modification documentaire**.

## Reprise confirmée le 26 octobre 2026

**Réseau :** les requêtes A vers pfSense `172.17.0.1` et Pi-hole
`172.17.0.24` sont toutes deux `NOERROR -> 172.17.0.24`.
L'interface HTTP `172.17.0.24:31085` répond mais le nom HTTPS privé
est inaccessible depuis la workstation. Ne pas modifier le DNS interne :
isoler le défaut Traefik/TLS avec
`sudo python3 scripts/truenas/diagnose-defectdojo-https-route.py --check`.

**Environnement :** `app_lifecycle.log` à 21:00:02 révèle un
`.env` non sensible absent. L'opérateur a copié
`apps/defectdojo/.env.example` vers le chemin canonique ; la copie peut
avoir conservé son propriétaire utilisateur. Contrôler puis normaliser
**uniquement ce fichier** :

```bash
sudo python3 scripts/truenas/prepare-defectdojo-runtime-env.py --inspect
sudo python3 scripts/truenas/prepare-defectdojo-runtime-env.py --apply
sudo python3 scripts/truenas/prepare-defectdojo-runtime-env.py --inspect
```

Le mode `--apply` accepte le contenu metadata de `.env.example`,
contrôle les clés autorisées et remet `root:root 0600`. Il ne modifie
**jamais** `.env.secrets`, dont l'opérateur a modifié
`DD_ADMIN_USER` et `DD_ADMIN_PASSWORD`. `DD_INITIALIZE=true`
dans `env_file` ne contrôle pas directement l'interpolation
`${DD_INITIALIZE}` du Compose initializer. Ne pas utiliser
l'initializer pour réinitialiser un compte déjà présent en base.

**Admin Django :** l'inventaire du 23 octobre démontrait un compte
`admin` existant. Modifier `DD_ADMIN_PASSWORD` dans un env_file
n'affecte pas le hash PostgreSQL de ce compte. Le nouveau helper
lit le secret canonique privé, sans imprimer le mot de passe :

```bash
sudo python3 scripts/truenas/reconcile-defectdojo-admin-password.py --check
```

- `PASSWORD_MATCH` : la nouvelle valeur est déjà celle du compte Django.
- `PASSWORD_MISMATCH` : synchroniser le **compte existant seulement** :

```bash
sudo python3 scripts/truenas/reconcile-defectdojo-admin-password.py \
  --apply --acknowledge I_APPROVE_EXISTING_DEFECTDOJO_ADMIN_PASSWORD_SYNC
```

Le helper passe le secret à `docker exec -i` **via stdin**,
jamais via les arguments ou les logs. Il n'enregistre qu'un résultat
allowlisté et ne recrée ni utilisateur ni superuser. Il refuse
`DD_ADMIN_USER` différent de `admin`, les doublons,
les secrets dont les permissions ne sont pas `root:root 0600`,
ou un compte Django absent/inactif/non-admin.

**Vaultwarden :** l'entrée `TrueNAS/nabla/prod/defectdojo` n'a pas
été revérifiée après l'édition manuelle. Confirmer
`login.username=admin`, puis synchroniser `login.password`
avec la valeur réellement choisie. Cette étape est distincte :
le helper Django ne modifie pas Vaultwarden. Une future
matérialisation depuis un coffre obsolète peut écraser le secret
canonique et recréer la divergence.

**HTTPS :** depuis le LAN, `diagnose-defectdojo-https-route.py --check`
compare HTTP `:31085` et TLS/SNI `:443`, ainsi que
l'état de `traefik`, les labels et `traefik_network`.
Un échec 404, 502 ou de certificat doit être corrigé côté ingress,
pas par une rotation du compte Django.

## 1. Source d'autorité du secret initial

La source canonique déclarative est `config/secrets/manifest.json` :
entrée Vaultwarden **`nabla/prod/defectdojo`** dans le dossier
**`TrueNAS`** ; le nom de compte correspond à `login.username`
(`DD_ADMIN_USER`) et le mot de passe à `login.password`
(`DD_ADMIN_PASSWORD`).

Les secrets sont matérialisés en privé sous
`/mnt/cpool/secrets/runtime/defectdojo/.env.secrets` et ne doivent jamais
être affichés dans les logs, tickets ou commandes collées au chat.
Le script `scripts/secrets/bootstrap_defectdojo_admin.py` génère
un login `nabla` **uniquement avant l'initialisation** et refuse
volontairement de remplacer un mot de passe existant. **Ne pas l'utiliser
pour la rotation d'un compte Django existant.**

Commencer par tenter le login `nabla` depuis l'entrée Vaultwarden
sur l'URL privée. Ni `DD_INITIALIZE=true` ni la modification du secret
runtime ne garantissent un changement du mot de passe déjà stocké dans
PostgreSQL.

## 2. Vérifier le compte en lecture seule

Exécuter localement sur TrueNAS, depuis une session opérateur autorisée :

```bash
sudo docker inspect defectdojo-uwsgi \
  --format 'state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'

# N'affiche que les noms de compte présents et leur état staff/superuser.
sudo docker exec defectdojo-uwsgi python manage.py shell -c \
  'from django.contrib.auth import get_user_model; U=get_user_model(); print([(u.username,u.is_staff,u.is_superuser) for u in U.objects.filter(username__in=["nabla","admin"])])'
```

Si `nabla` existe, choisir ce compte. Si `admin` seul existe,
ne pas créer de doublon : vérifier pourquoi le bootstrap diverge de Vaultwarden
et conserver le compte réellement présent.

## 3. Réinitialisation contrôlée et interactive

Uniquement si nécessaire, sans mot de passe sur la ligne de commande :

```bash
# À exécuter dans un vrai terminal privé interactif (TTY).
sudo docker exec -it defectdojo-uwsgi python manage.py changepassword nabla
```

Remplacer `nabla` par `admin` **uniquement si l'inventaire en lecture
seule a prouvé que c'est le compte attendu**. Django demande le nouveau
mot de passe sans l'afficher, le hache dans sa base et ne requiert
**aucun restart** Docker. Ne pas lancer cette commande par CI ou dans
un agent qui enregistrerait la saisie.

Ouvrir ensuite Vaultwarden et **mettre à jour le champ mot de passe de
l'entrée existante** `TrueNAS/nabla/prod/defectdojo` (ne pas créer
une nouvelle entrée, ne pas modifier les secrets de chiffrement
`DD_SECRET_KEY` et `DD_CREDENTIAL_AES_256_KEY`).
Tester le login dans une session de navigation privée. Il n'est pas nécessaire
de redéployer DefectDojo pour valider le changement de mot de passe.

## 4. Sécurité et limites

- Ne pas inspecter `docker inspect .Config.Env`, ni imprimer
  `.env.secrets` ou l'historique des mots de passe.
- Ne pas utiliser `createsuperuser` si le compte existe ;
  ne pas réinitialiser PostgreSQL ou les migrations.
- Ne pas remplacer `DD_ADMIN_PASSWORD` seul et supposer que Django a
  automatiquement changé le mot de passe d'un compte existant.
- Garder la route sous DNS interne/Traefik et vérifier l'accès réseau
  avec `sudo bash scripts/truenas/diagnose-defectdojo.sh --check`.

Source éditeur : [DefectDojo — running with Docker Compose](https://github.com/DefectDojo/django-DefectDojo/blob/master/readme-docs/DOCKER.md#option-to-change-the-password).


## 5. Inventaire Django réel — 23 octobre 2026

L'opérateur a exécuté la requête Django lecture seule dans
`defectdojo-uwsgi`. Résultat : **`['admin']`**.
L'identité `nabla` est une intention de bootstrap inscrite dans GitOps et
Vaultwarden, **pas le compte actuellement prouvé dans PostgreSQL**.

Pour cette installation existante, utiliser depuis un terminal privé :

```bash
sudo docker exec -it defectdojo-uwsgi python manage.py changepassword admin
```

Mettre ensuite à jour dans Vaultwarden l'entrée canonique
`TrueNAS/nabla/prod/defectdojo` en vérifiant que le username correspond
**au compte réel `admin`**, sans recréer l'entrée et sans importer de
nouveau superutilisateur. Cette divergence d'identité doit être revue
avant un futur initializer/réconciliation. Ne pas supprimer l'utilisateur
`admin` ni modifier la base pour la masquer.
