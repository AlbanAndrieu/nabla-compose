# Préflight du déplacement de `apps/openclaw/compose.yml` (read-only)

Le dossier `apps/openclaw` sera à terme le **submodule directement**
`AlbanAndrieu/nabla-openclaw`. Le premier lot de migration est effectué :
14 fichiers Workstation déplacés sous `ops/openclaw-workstation/`
avec références Python et tests adaptés. **Quatre fichiers sandbox**
restent dans `apps/openclaw/`.

**Audit des consommateurs en code (PR #300, avant toute mutation) :**
le [registre de dépendances](../migrations/openclaw-sandbox-consumers-go-no-go-20261030.md)
identifie, au-delà de la configuration TrueNAS,
`build.sh` qui invoque `docker compose -f apps/openclaw/compose.yml`,
ainsi que `catalog/services.json`,
`catalog/service-topology.json`,
l'annotation Backstage `apps/openclaw/catalog-info.yaml`
et les artefacts générés du catalogue. Ce sont des **références
encore actives dans Git** à migrer de manière cohérente.
Le sandbox monte des chemins privés de Workstation et ne doit
pas être considéré comme un Gateway TrueNAS.

**État de décision : NO-GO pour le déplacement des quatre fichiers
et le gitlink direct `apps/openclaw`**, tant que les consommateurs
ci-dessus, l'inventaire global des Apps TrueNAS et le rollback
n'ont pas été réceptionnés. Le script de préflight reste
strictement en lecture seule et retourne **2 par conception**,
même lorsqu'aucune référence App n'est observée. Ne pas interpréter
ce code comme un `DOWN` ni désactiver cette protection.

**Attention :** le fichier Compose du sandbox peut être référencé par
une application TrueNAS via `custom_compose_config.include`.
Le nouveau script lit seulement `app.config` pour les deux noms
`openclaw` et `openclaw-sandbox` et expurge toute configuration.
La commande sans option inspecte ces deux noms pour un premier contrôle.
La variante **`--all-apps`** obtient l'inventaire complet par
`midclt call app.query`, puis inspecte chaque configuration
`app.config` à partir de son identifiant strictement validé.
Elle ne publie ni noms d'apps, ni configuration ni secrets.
Elle peut identifier une référence indirecte à l'ancien chemin dans
**n'importe quelle application installée**, pas seulement OpenClaw.
Une réponse illisible ou une liste incomplète bloque la conclusion.

L'absence de référence dans les configurations TrueNAS est une
**preuve limitée aux configurations des Apps** : un script externe,
un fichier Compose autonome ou une tâche d'orchestration peut encore
référencer le chemin historique. Le code retour reste toujours `2` :
**aucun déplacement automatique**.

Sur **TrueNAS** (après pull de la branche #295) :

```bash
cd /mnt/cpool/compose/nabla-compose
python3 -m unittest discover -s tests -p 'test_openclaw_sandbox_binding.py' -v
python3 -m unittest discover -s tests -p 'test_openclaw_sandbox_global_binding.py' -v

# Couverture globale des applications TrueNAS (recommandé) :
python3 scripts/truenas/check-openclaw-sandbox-binding.py --all-apps

# Seulement si le compte exige des droits préexistants :
python3 scripts/truenas/check-openclaw-sandbox-binding.py --all-apps --noninteractive-sudo
```

`blocked_legacy_include_in_use` : une application a confirmé
l'ancien chemin ; **STOP**. `unverified_app_inventory` ou
`unverified_incomplete_app_scan` : couverture insuffisante ;
**STOP**. `manual_review_no_app_reference_observed` :
aucune référence détectée dans la totalité des configurations
d'applications interrogées, **mais il reste à vérifier les autres
consommateurs et la procédure de retour arrière**. Dans tous les cas,
aucune autorisation automatique de déplacement. Ne pas publier les sorties
brutes de `midclt call app.config`, qui peuvent contenir des secrets.

Après validation indépendante des apps et consommateurs :
1. Mettre à jour la référence TrueNAS de `include` **dans une
   opération distincte**, avec sauvegarde et rollback.
2. Déplacer les 4 fichiers sandbox vers `apps/openclaw-sandbox/`,
   en conservant le service et le catalogue opérationnel.
3. Vérifier le runtime et l'absence de référence à l'ancien chemin.
4. Seulement alors ajouter le submodule `apps/openclaw`, avec
   pin d'un SHA testé de `nabla-openclaw`. Aucun déploiement de
   Gateway/heartbeat pendant le changement de chemin Git.

L'API TrueNAS 26 `app.config` est une lecture de configuration
requérant `APPS_READ`, pas une commande de modification.

## Référence Git du dépôt cible

[nabla-openclaw PR #1](https://github.com/AlbanAndrieu/nabla-openclaw/pull/1)
a été fusionnée le **30 octobre 2026 à 08:12 UTC** dans
`master`, commit **`dd30474330dbe2ddcb21d8eb9da9aec119b27c46`**.
Ce SHA désigne le premier contrat GitOps validé en tests locaux
(3 tests), **pas un manifeste Gateway TrueNAS opérationnel**.
Le futur gitlink `apps/openclaw` devra épingler une révision
réellement testée au moment de son ajout et ne pas suivre
`master` automatiquement.

## Correctif de décodage `midclt` du 30 octobre

Sur TrueNAS, `midclt call system.version` peut afficher la version
**sans guillemets JSON**, par exemple `TrueNAS-26.0.0-BETA.3`.
L'ancienne fonction `query()` effectuait exclusivement
`json.loads(stdout)`, rejetait cette sortie brute puis renvoyait
`blocked_wrong_host_or_access` **avant même de lancer `app.query`**.
Ce verdict ne constituait donc pas une preuve de mauvais hôte ou
de permission manquante.

Le correctif accepte, **pour `system.version` uniquement**, un
identifiant TrueNAS brut validé par expression régulière bornée.
Les listes et objets des autres méthodes conservent le parsing JSON
strict. Le correctif ne nécessite **aucun sudo** et n'assouplit pas
la vérification des identifiants d'applications. Des tests simulent
désormais les sorties d'octets réelles du CLI (version brute, JSON
quoté, sortie corrompue, commande refusée et parcours complet).

```bash
cd /mnt/cpool/compose/nabla-compose
git pull --ff-only
python3 -m unittest discover -s tests \
  -p 'test_openclaw_sandbox_global_binding.py' -v
python3 scripts/truenas/check-openclaw-sandbox-binding.py --all-apps
```

Le second contrôle retourne toujours `2` par conception : lire
`sandbox_relocation`, `app_inventory_count` et
`app_configs_unverified`, **pas** le seul code retour.
Si `unverified_app_inventory` persiste, l'étape suivante est
de diagnostiquer séparément les droits `APPS_READ` du compte
`midclt` ; ne pas utiliser `sudo` automatiquement et ne jamais
coller de configurations brutes sur GitHub.
