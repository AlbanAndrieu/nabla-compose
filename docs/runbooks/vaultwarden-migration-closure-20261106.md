# Vaultwarden → TrueNAS : clôture contrôlée des secrets (06/11/2026)

## Statut et preuve minimale

Le manifeste de la branche de référence de la PR Compose #326 décrit **43
applications, 117 champs** et **6 exceptions de bootstrap**. C'est un
inventaire Git et **non** un décompte d'imports effectués. Aucun accès
authentifié au coffre ni aux fichiers runtime TrueNAS n'a été utilisé pour
rédiger ce document ; la clôture globale reste `NOT_VERIFIED`.

La migration doit prouver **quatre frontières distinctes** : (1) item unique
dans le bon dossier Vaultwarden, (2) champs réellement présents et valides,
(3) fichier canonique root:root `0600` identique au rendu, (4) conteneur
consommant effectivement le bon secret, puis fonctionnement et rollback.
La preuve du niveau 3 **n'implique pas** le niveau 4.

Le runtime canonique est `/mnt/cpool/secrets/runtime/<app>/.env.secrets`.
Les fichiers historiques et les sauvegardes git-crypt sont préservés jusqu'à
la réception par service. Ne jamais présenter un `--check` de métadonnées
comme un import effectif.

## 1. Audit sans secret ni mutation

Sur un checkout contenant le script de cette PR :

```bash
python3 scripts/secrets/audit-vaultwarden-migration.py --check
python3 -m unittest discover -s tests -p 'test_vaultwarden_migration_receipt.py' -v
```

Le contrôle est **hors ligne** et affiche uniquement les compteurs
déclaratifs. Il doit notamment révéler une modification du nombre d'Apps
après le retrait de `aistor` et `wordpress`. Pour observer le coffre,
exécuter les étapes suivantes **sur TrueNAS**, sans être root et après
avoir déverrouillé la session Bitwarden native.

```bash
cd /mnt/cpool/compose/nabla-compose
# BW_SESSION doit être obtenu dans une session locale privée et jamais collé
# dans une issue, un ticket, une PR ou un transcript.
python3 scripts/secrets/inventory_vaultwarden.py --json
python3 scripts/secrets/audit-vaultwarden-migration.py --verify --app homarr
python3 scripts/secrets/audit-vaultwarden-migration.py --verify
```

Le dernier outil s'appuie sur `inventory_vaultwarden.py` (cache CLI ;
ce n'est pas une preuve de lecture serveur fraîche) et sur
`materialize_runtime.py --verify` (rendu éphémère + comparaison
`sudo -n`, sans installation). Ses sorties ne contiennent ni valeurs,
ni identifiants d'item, ni empreintes de secrets. Les erreurs des
sous-processus sont volontairement masquées.

Interprétation : `FILE_PARITY_VERIFIED` prouve l'égalité du fichier
canonique avec le rendu Vaultwarden sur la session utilisée ;
`PARTIAL_OR_UNVERIFIED` exige une investigation ciblée.
`container_loaded=NOT_VERIFIED` reste vrai dans les deux cas.
**Aucune rotation, installation ou redémarrage n'est automatique.**

## 2. Réparer une application à la fois

1. Sauvegarder de façon indépendante le fichier existant, son propriétaire,
   ses ACL et le rollback. Vérifier les consommateurs (Compose `env_file`,
   secrets montés, variables réellement injectées) et le `appId` TrueNAS.
2. S'il manque un champ Vaultwarden : trouver sa **valeur historique
   approuvée**, préserver l'identité fournisseur partagée, puis faire
   le dry-run `python3 scripts/secrets/import_env_to_bitwarden.py --app APP`.
   N'utiliser `--apply` qu'après contrôle des noms, de l'item unique,
   du bon dossier et des droits d'import. Ne pas écraser un item existant
   sans revue explicite de `--update-existing`.
3. Lorsque la source coffre est prouvée, vérifier
   `python3 scripts/secrets/materialize_runtime.py --app APP --verify`.
   Si une matérialisation est réellement nécessaire, appliquer
   `--install` **pour un seul APP** après sauvegarde et autorisation.
   Le script effectue une installation atomique root:root `0600`.
4. Comparer la **configuration middleware** et les variables/montages
   réellement exposés au conteneur, sans imprimer leur valeur. Faire une
   requête fonctionnelle authentifiée bornée ; redéployer uniquement
   l'App concernée si nécessaire.
5. Confirmer le maintien de l'état après redémarrage et la possibilité
   de revenir au fichier précédent. **Seulement ensuite** examiner la
   suppression ciblée des chemins `/mnt/cpool/<app>/.env*` encore lus.

**Exemple P0 — Homarr** : le runtime observé le 6 novembre contient
`HOMARR_API_TOKEN` alors que `homarr-sync` demande
`HOMARR_API_KEY`. Vérifier le champ exact du coffre et le consommateur
avant de recréer un token ou de relancer `homarr-sync`. Cette incohérence
n'est pas une preuve que le secret coffre est absent.

**Exemples P1** : OpenRAG/OpenSearch (mot de passe partagé, aucun
renouvellement isolé), LiteLLM (clé upstream distincte), Scrutiny
(app historiquement arrêtée), Joplin/Scanopy (services encore planifiés).

## 3. Clôture réelle — gate `ACCEPTED (runtime)`

Une application est **terminée** uniquement après preuve horodatée :
item unique et champs complets, `FILE_PARITY_VERIFIED`, absence de chemin
legacy dans le conteneur actif, santé fonctionnelle authentifiée, restauration
possible, absence de secret en logs/process argv et `BW_SESSION` verrouillé.

La clôture globale exige la même preuve pour chaque App **active** et une
décision documentée pour chaque App **planned/disabled** et chaque exception
bootstrap. Des lignes du manifeste existent encore pour des services
désormais absents de la topologie : les revoir sans détruire d'items
potentiellement utiles à une restauration.

Le script de couverture ne contacte pas les conteneurs, ne valide pas les
rotations et ne modifie jamais Vaultwarden. Son résultat seul ne suffit
donc pas à conclure à une migration globale.

Références :
[guide des secrets](../../config/secrets/README.md) ·
[roadmap principale](../roadmap.md) ·
[incidents historiques](truenas-secret-migration-closure.md).
