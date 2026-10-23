# DefectDojo — retrouver ou réinitialiser le compte administrateur

**Contexte Nabla / TrueNAS** : `https://defectdojo.int.albandrieu.com/`,
Custom App `defectdojo`, conteneur Django `defectdojo-uwsgi`,
base PostgreSQL partagée. **Ne pas recréer la base ni relancer l'initializer.**

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
